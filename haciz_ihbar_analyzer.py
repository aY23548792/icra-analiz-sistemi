#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HACİZ İHBAR ANALYZER v11.1 - ROBUST EDITION
"""

import os
import re
import zipfile
import sys

# pdfplumber importunu güvenli yap
try:
    import pdfplumber
    PDFPLUMBER_OK = True
except ImportError:
    PDFPLUMBER_OK = False

try:
    from icra_analiz_v2 import IcraUtils
except ImportError:
    # Fallback
    class IcraUtils:
        @staticmethod
        def clean_text(t): return t.lower() if t else ""
        @staticmethod
        def tutar_parse(t): return 0.0

# === ENUMS ===
class IhbarTuru(Enum):
    IHBAR_89_1 = "89/1 - Birinci İhbar"
    IHBAR_89_2 = "89/2 - İkinci İhbar"
    IHBAR_89_3 = "89/3 - Üçüncü İhbar"
    BILINMIYOR = "Tespit Edilemedi"

class MuhatapTuru(Enum):
    BANKA = "🏦 Banka"
    TUZEL_KISI = "🏢 Tüzel Kişi"
    GERCEK_KISI = "👤 Gerçek Kişi"
    BILINMIYOR = "❓ Bilinmiyor"

class CevapDurumu(Enum):
    BLOKE_VAR = "💰 BLOKE VAR"
    HESAP_VAR_BAKIYE_YOK = "📋 Hesap Var - Bakiye Yok"
    HESAP_YOK = "❌ Hesap Bulunamadı"
    ALACAK_VAR = "💵 Alacak Var"
    ALACAK_YOK = "❌ Alacak Yok"
    ODEME_YAPILDI = "✅ Ödeme Yapıldı"
    ITIRAZ = "⚖️ İtiraz Edildi"
    PARSE_HATASI = "❓ Parse Edilemedi"

# === DATA CLASSES ===
@dataclass
class HacizIhbarCevabi:
    muhatap_adi: str
    muhatap_turu: MuhatapTuru
    ihbar_turu: IhbarTuru
    cevap_durumu: CevapDurumu
    bloke_tutari: float = 0.0
    alacak_tutari: float = 0.0
    aciklama: str = ""
    kaynak_dosya: str = ""
    sonraki_adim: str = ""

@dataclass
class HacizIhbarAnalizSonucu:
    toplam_muhatap: int = 0
    banka_sayisi: int = 0
    tuzel_kisi_sayisi: int = 0
    gercek_kisi_sayisi: int = 0
    toplam_bloke: float = 0.0
    toplam_alacak: float = 0.0
    cevaplar: List[HacizIhbarCevabi] = field(default_factory=list)
    eksik_ihbarlar: List[dict] = field(default_factory=list)
    ozet_rapor: str = ""

    @property
    def banka_sayisi(self):
        """Benzersiz banka sayısı"""
        return len(set(c.muhatap for c in self.cevaplar))

    @property
    def ozet_rapor(self):
        """Basit rapor çıktısı"""
        lines = [f"Toplam Dosya: {self.toplam_dosya}", f"Toplam Bloke: {self.toplam_bloke:,.2f} TL", "-"*20]
        for c in self.cevaplar:
            lines.append(f"{c.muhatap}: {c.durum.value} - {c.tutar:,.2f} TL ({c.sonraki_adim})")
        return "\n".join(lines)

class HacizIhbarAnalyzer:
    """
    Context-Aware Banka Cevap Analizi
    ---------------------------------
    Strateji:
    1. Önce NEGATİF durumları kontrol et (hesap yok, bakiye yok)
    2. Sonra POZİTİF durumları ara (bloke var)
    3. Context-aware: Sadece "bloke" kelimesine YAKIN tutarları al
    """
    
    # Banka isimleri (küçük harf pattern)
    BANKALAR = {
        'Ziraat Bankası': [r'ziraat', r't\.?c\.?\s*ziraat'],
        'Halkbank': [r'halk\s*bank'],
        'VakıfBank': [r'vakıf', r'vakif'],
        'İş Bankası': [r'i[şs]\s*bank', r'türkiye\s*i[şs]'],
        'Garanti BBVA': [r'garanti', r'bbva'],
        'Yapı Kredi': [r'yap[ıi]\s*kredi'],
        'Akbank': [r'akbank'],
        'QNB Finansbank': [r'qnb', r'finansbank'],
        'Denizbank': [r'deniz\s*bank'],
        'TEB': [r'\bteb\b', r'türk\s*ekonomi'],
        'ING Bank': [r'\bing\b'],
        'HSBC': [r'hsbc'],
        'Kuveyt Türk': [r'kuveyt'],
        'Albaraka': [r'albaraka'],
        'Şekerbank': [r'şeker', r'seker'],
        'PTT': [r'\bptt\b'],
    }
    
    # Context-Aware Bloke Regex
    # Sadece "bloke" kelimesinin YAKININDA olan tutarları yakalar
    BLOKE_BEFORE = re.compile(
        r'(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?)\s*(?:TL|₺)?.{0,40}?bloke',
        re.IGNORECASE | re.DOTALL
    )
    BLOKE_AFTER = re.compile(
        r'bloke.{0,40}?(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?)\s*(?:TL|₺)?',
        re.IGNORECASE | re.DOTALL
    )
    
    # Alacak Regex (3. şahıslar için)
    ALACAK_REGEX = re.compile(
        r'(?:alacak|hak|hakediş).{0,40}?(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?)\s*(?:TL|₺)?',
        re.IGNORECASE | re.DOTALL
    )
    
    # Negatif durumlar
    HESAP_YOK_PATTERNS = [
        r'hesab[ıi]\s*(?:bulun|mevcut|yok)',
        r'kayıt(?:lı)?\s*(?:hesab)?\s*(?:bulun|yok)',
        r'müşteri\s*kayd[ıi]\s*(?:bulun|yok)',
        r'herhangi\s*bir\s*hesap\s*(?:bulun|yok)',
        r'herhangi\s*bir\s*hesap[ıi]?\s*(?:bulun|yok)',
        r'adına\s*hesap\s*(?:bulun|yok)',
        r'adına\s*herhangi\s*bir\s*hesap',
        r'hesap\s*bulunmam',
        r'hesap\s*yoktur',
        r'hesap\s*mevcut\s*değil',
    ]
    
    BAKIYE_YOK_PATTERNS = [
        r'bakiye(?:si)?\s*(?:bulun|yok|yetersiz)',
        r'bakiye\s*:?\s*0[,.]?00',
        r'müsait\s*bakiye\s*(?:bulun|yok)',
        r'bloke\s*edilebilir\s*(?:tutar|bakiye)?\s*(?:bulun|yok)',
    ]

    def __init__(self):
        self.temp_dirs = []

    def batch_analiz(self, dosya_yollari: List[str]) -> HacizIhbarAnalizSonucu:
        cevaplar = []
        for yol in dosya_yollari:
            try:
                metin = self._dosya_oku(yol)
                if metin:
                    cevaplar.append(self.analyze_response(metin))
            except Exception as e:
                print(f"Hata {yol}: {e}", file=sys.stderr)

        toplam = sum(c.tutar for c in cevaplar if c.durum == CevapDurumu.BLOKE_VAR)
        return HacizIhbarAnalizSonucu(len(cevaplar), toplam, cevaplar)

    def analyze_response(self, text: str) -> HacizIhbarCevabi:
        clean = IcraUtils.clean_text(text)
        
        # 1. Muhatap Belirle
        muhatap = "Bilinmeyen"
        for b in self.BANKALAR:
            if IcraUtils.clean_text(b) in clean:
                muhatap = b
                break
        
        durum = CevapDurumu.BELIRSIZ
        tutar = 0.0
        sonraki = "İncele"

        # 2. KEP Kontrolü
        if "kep iletisi" in clean and len(text) < 500:
            return HacizIhbarCevabi(muhatap, CevapDurumu.KEP, 0.0, "Bekle", text[:100])

        # 3. Negatif Kontrol (Öncelikli)
        if any(re.search(p, clean) for p in self.MENFI_REGEX):
            return HacizIhbarCevabi(muhatap, CevapDurumu.MENFI, 0.0, "89/1 Başkasına", text[:100])

        # 4. Bloke Arama (Genişletilmiş ve Güçlü Regex)
        # Önce net "bloke: 123 TL" kalıplarını arıyoruz
        # Regex: (Tutar) ... (Bloke) veya (Bloke) ... (Tutar)
        
        bloke_bulundu = False
        
        # Pattern A: "33.534,33 TL ... bloke"
        match_a = re.search(r'(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?)\s*TL.*?bloke', text, re.I | re.DOTALL)
        if match_a:
            tutar = IcraUtils.tutar_parse(match_a.group(1))
            bloke_bulundu = True

        # Pattern B: "bloke ... 33.534,33 TL"
        if not bloke_bulundu:
            match_b = re.search(r'bloke.*?(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?)\s*TL', text, re.I | re.DOTALL)
            if match_b:
                tutar = IcraUtils.tutar_parse(match_b.group(1))
                bloke_bulundu = True
        
        if bloke_bulundu and tutar > 0:
            durum = CevapDurumu.BLOKE_VAR
            sonraki = "Mahsup İste"
        elif any(re.search(p, clean) for p in self.BAKIYE_YOK_REGEX):
             durum = CevapDurumu.HESAP_VAR_BAKIYE_YOK
             sonraki = "89/2 Gönder"
        elif "haciz" in clean or "bloke" in clean:
             # Kelime var ama tutar okunamadı
             durum = CevapDurumu.BLOKE_VAR
             sonraki = "Manuel Kontrol (Tutar Okunamadı)"
        
        return HacizIhbarCevabi(muhatap, durum, tutar, sonraki, text[:200])

    def _dosya_oku(self, yol):
        try:
            # UDF ise XML parse et
            if yol.endswith('.udf'):
                with zipfile.ZipFile(yol) as z:
                    # Check for content.xml or other xmls
                    xml_files = [n for n in z.namelist() if n.endswith('.xml')]
                    if 'content.xml' in xml_files:
                        target = 'content.xml'
                    elif xml_files:
                        target = xml_files[0]
                    else:
                        return ""

                    raw = z.read(target).decode('utf-8', 'ignore')
                    # Basit XML temizliği
                    return re.sub(r'<[^>]+>', ' ', raw)
            
            # PDF ise pdfplumber
            if yol.endswith('.pdf'):
                if not PDFPLUMBER_OK:
                    return "PDF okuyucu (pdfplumber) yüklü değil."

                with pdfplumber.open(yol) as pdf:
                    return "\n".join([p.extract_text() or "" for p in pdf.pages])
            
            # Text/XML (Other)
            if os.path.isfile(yol):
                 with open(yol, 'r', encoding='utf-8', errors='ignore') as f:
                    return f.read()

            return ""
        except Exception as e:
            print(f"Dosya okuma hatası ({yol}): {e}", file=sys.stderr)
            return ""
