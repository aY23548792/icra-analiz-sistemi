#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HACİZ İHBAR ANALYZER v12.0 - Context-Aware Edition
==================================================
Banka ve 3. şahıs cevaplarını analiz eder.
"Ghost Bloke" sorununu çözer: Sadece gerçek bloke tutarlarını yakalar.

SINGLE SOURCE OF TRUTH: Bloke hesaplaması SADECE burada yapılır.

Author: Arda & Claude
"""

import os
import re
import zipfile
import tempfile
import shutil
import logging
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Tuple, Optional
from enum import Enum

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# PDF desteği
try:
    import pdfplumber
    PDF_OK = True
except ImportError:
    PDF_OK = False
    logger.warning("pdfplumber yüklü değil")

# Shared core import
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

# === MAIN ANALYZER ===
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
        """Birden fazla dosyayı analiz et"""
        sonuc = HacizIhbarAnalizSonucu()
        islenen = []
        
        work_dir = tempfile.mkdtemp()
        self.temp_dirs.append(work_dir)
        
        try:
            files_to_process = []
            
            for yol in dosya_yollari:
                if yol.endswith('.zip'):
                    try:
                        with zipfile.ZipFile(yol, 'r') as zf:
                            zf.extractall(work_dir)
                            for root, _, files in os.walk(work_dir):
                                for f in files:
                                    files_to_process.append(os.path.join(root, f))
                    except Exception as e:
                        logger.error(f"ZIP hatası: {e}")
                else:
                    files_to_process.append(yol)
            
            for fp in files_to_process:
                fname = os.path.basename(fp)
                if fname.startswith('.'):
                    continue
                if not fname.lower().endswith(('.pdf', '.txt', '.udf', '.xml')):
                    continue
                
                text = self._dosya_oku(fp)
                if not text or len(text) < 50:
                    continue
                
                islenen.append(fname)
                cevap = self._analiz_et(text, fname, fp)
                sonuc.cevaplar.append(cevap)
            
            # Aggregation
            self._aggregate(sonuc, islenen)
            
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)
        
        return sonuc

    def _dosya_oku(self, yol: str) -> str:
        """PDF, UDF veya text dosyasını oku"""
        ext = os.path.splitext(yol)[1].lower()
        
        try:
            if ext == '.pdf' and PDF_OK:
                with pdfplumber.open(yol) as pdf:
                    return "\n".join([p.extract_text() or "" for p in pdf.pages])
            
            elif ext == '.udf':
                with zipfile.ZipFile(yol, 'r') as zf:
                    if 'content.xml' in zf.namelist():
                        raw = zf.read('content.xml').decode('utf-8', errors='ignore')
                        # XML tag'lerini temizle
                        clean = re.sub(r'<[^>]+>', ' ', raw)
                        return clean
            
            else:
                with open(yol, 'r', encoding='utf-8', errors='ignore') as f:
                    return f.read()
        
        except Exception as e:
            logger.error(f"Dosya okuma hatası ({yol}): {e}")
        
        return ""

    def _analiz_et(self, text: str, filename: str, filepath: str) -> HacizIhbarCevabi:
        """Tek bir cevabı analiz et"""
        
        # 1. Muhatap tespit
        muhatap_turu, muhatap_adi = self._muhatap_tespit(text, filename)
        
        # 2. İhbar türü tespit
        ihbar_turu = self._ihbar_turu_tespit(text)
        
        # 3. Durum ve tutar tespit (Context-Aware)
        durum, tutar, aciklama = self._durum_tespit(text, muhatap_turu)
        
        # 4. Sonraki adım belirle
        sonraki = self._sonraki_adim(durum, ihbar_turu)
        
        cevap = HacizIhbarCevabi(
            muhatap_adi=muhatap_adi,
            muhatap_turu=muhatap_turu,
            ihbar_turu=ihbar_turu,
            cevap_durumu=durum,
            aciklama=aciklama,
            kaynak_dosya=filepath,
            sonraki_adim=sonraki
        )
        
        if durum == CevapDurumu.BLOKE_VAR:
            cevap.bloke_tutari = tutar
        elif durum == CevapDurumu.ALACAK_VAR:
            cevap.alacak_tutari = tutar
        
        return cevap

    def _muhatap_tespit(self, text: str, filename: str) -> Tuple[MuhatapTuru, str]:
        """Muhatabı belirle (banka mı, şirket mi?)"""
        combined = IcraUtils.clean_text(text + " " + filename)
        
        # Banka kontrolü
        for banka, patterns in self.BANKALAR.items():
            for p in patterns:
                if re.search(p, combined):
                    return MuhatapTuru.BANKA, banka
        
        # Şirket kontrolü
        if re.search(r'a\.?\s*ş\.?|ltd\.?\s*şti|ticaret|sanayi', combined):
            return MuhatapTuru.TUZEL_KISI, "Şirket"
        
        return MuhatapTuru.GERCEK_KISI, "Kişi/Diğer"

    def _ihbar_turu_tespit(self, text: str) -> IhbarTuru:
        """89/1, 89/2, 89/3 tespit"""
        if '89/1' in text or 'birinci' in text.lower():
            return IhbarTuru.IHBAR_89_1
        if '89/2' in text or 'ikinci' in text.lower():
            return IhbarTuru.IHBAR_89_2
        if '89/3' in text or 'üçüncü' in text.lower():
            return IhbarTuru.IHBAR_89_3
        return IhbarTuru.BILINMIYOR

    def _durum_tespit(self, text: str, muhatap_turu: MuhatapTuru) -> Tuple[CevapDurumu, float, str]:
        """
        CORE LOGIC: Context-Aware Durum Tespiti
        ---------------------------------------
        Öncelik sırası:
        1. Negatif durumlar (hesap yok, bakiye yok)
        2. Pozitif durumlar (bloke var)
        """
        text_clean = IcraUtils.clean_text(text)
        
        # === 1. NEGATİF KONTROLLER (ÖNCELİKLİ) ===
        for p in self.HESAP_YOK_PATTERNS:
            if re.search(p, text_clean):
                return CevapDurumu.HESAP_YOK, 0.0, "Hesap bulunamadı"
        
        for p in self.BAKIYE_YOK_PATTERNS:
            if re.search(p, text_clean):
                return CevapDurumu.HESAP_VAR_BAKIYE_YOK, 0.0, "Bakiye yetersiz"
        
        # === 2. POZİTİF KONTROLLER ===
        
        if muhatap_turu == MuhatapTuru.BANKA:
            # Context-Aware Bloke Arama
            # Pattern 1: Tutar ... bloke
            match = self.BLOKE_BEFORE.search(text)
            if match:
                tutar = IcraUtils.tutar_parse(match.group(1))
                if tutar > 0:
                    return CevapDurumu.BLOKE_VAR, tutar, f"Bloke: {tutar:,.2f} TL"
            
            # Pattern 2: bloke ... Tutar
            match = self.BLOKE_AFTER.search(text)
            if match:
                tutar = IcraUtils.tutar_parse(match.group(1))
                if tutar > 0:
                    return CevapDurumu.BLOKE_VAR, tutar, f"Bloke: {tutar:,.2f} TL"
            
            # Fallback: "bloke" kelimesi var ama tutar okunamadı
            if 'bloke' in text_clean:
                return CevapDurumu.BLOKE_VAR, 0.0, "Bloke var (tutar okunamadı)"
        
        else:
            # 3. Şahıs için alacak kontrolü
            if 'ödeme yapıl' in text_clean:
                return CevapDurumu.ODEME_YAPILDI, 0.0, "Ödeme yapılmış"
            
            match = self.ALACAK_REGEX.search(text)
            if match:
                tutar = IcraUtils.tutar_parse(match.group(1))
                if tutar > 0:
                    return CevapDurumu.ALACAK_VAR, tutar, f"Alacak: {tutar:,.2f} TL"
        
        return CevapDurumu.PARSE_HATASI, 0.0, "Durum tespit edilemedi"

    def _sonraki_adim(self, durum: CevapDurumu, ihbar: IhbarTuru) -> str:
        """Sonraki aksiyonu belirle"""
        if durum == CevapDurumu.BLOKE_VAR:
            return "Mahsup/Tahsil İste"
        if durum == CevapDurumu.HESAP_YOK:
            return "Başka bankaya 89/1"
        if durum == CevapDurumu.HESAP_VAR_BAKIYE_YOK:
            return "89/2 gönder"
        if durum == CevapDurumu.ALACAK_VAR:
            return "Tahsil için işlem yap"
        return "Manuel incele"

    def _aggregate(self, sonuc: HacizIhbarAnalizSonucu, islenen: List[str]):
        """Sonuçları topla"""
        muhataplar = set()
        
        for c in sonuc.cevaplar:
            muhataplar.add(c.muhatap_adi)
            
            if c.muhatap_turu == MuhatapTuru.BANKA:
                sonuc.banka_sayisi += 1
            elif c.muhatap_turu == MuhatapTuru.TUZEL_KISI:
                sonuc.tuzel_kisi_sayisi += 1
            else:
                sonuc.gercek_kisi_sayisi += 1
            
            sonuc.toplam_bloke += c.bloke_tutari
            sonuc.toplam_alacak += c.alacak_tutari
        
        sonuc.toplam_muhatap = len(muhataplar)
        
        # Özet rapor
        lines = [
            "=" * 60,
            "📋 89/1-2-3 HACİZ İHBAR ANALİZ RAPORU",
            f"Tarih: {datetime.now().strftime('%d.%m.%Y %H:%M')}",
            "=" * 60,
            "",
            "📊 GENEL ÖZET",
            "-" * 40,
            f"  Toplam Muhatap: {sonuc.toplam_muhatap}",
            f"    🏦 Banka: {sonuc.banka_sayisi}",
            f"    🏢 Tüzel: {sonuc.tuzel_kisi_sayisi}",
            f"    👤 Gerçek: {sonuc.gercek_kisi_sayisi}",
            f"  💰 TOPLAM BLOKE: {sonuc.toplam_bloke:,.2f} TL",
            f"  💵 TOPLAM ALACAK: {sonuc.toplam_alacak:,.2f} TL",
            "",
            "💰 BLOKE DETAY",
            "-" * 40,
        ]
        
        blokeler = [c for c in sonuc.cevaplar if c.cevap_durumu == CevapDurumu.BLOKE_VAR]
        if blokeler:
            for c in blokeler:
                lines.append(f"  ✅ {c.muhatap_adi}: {c.bloke_tutari:,.2f} TL")
        else:
            lines.append("  Bloke kaydı yok")
        
        lines.extend(["", "=" * 60])
        sonuc.ozet_rapor = "\n".join(lines)


# === TEST ===
if __name__ == "__main__":
    print("🧪 HacizIhbarAnalyzer Test")
    print("=" * 50)
    
    analyzer = HacizIhbarAnalyzer()
    
    # Test 1: Context-Aware (Dosya borcu vs Bloke)
    test1 = """
    T.C. ZİRAAT BANKASI A.Ş.
    Dosya Borcu: 100.000,00 TL
    Konu: 89/1 Haciz İhbarnamesi
    Hesaplar üzerinde 45.678,90 TL tutarında bloke tesis edilmiştir.
    """
    
    result = analyzer._analiz_et(test1, "ziraat.pdf", "/tmp/ziraat.pdf")
    print(f"\nTest 1 - Ziraat (Context-Aware):")
    print(f"  Muhatap: {result.muhatap_adi}")
    print(f"  Durum: {result.cevap_durumu.value}")
    print(f"  Tutar: {result.bloke_tutari:,.2f} TL")
    print(f"  Beklenen: 45,678.90 TL (NOT 100,000)")
    assert result.bloke_tutari == 45678.90, f"FAIL: {result.bloke_tutari}"
    print("  ✅ PASSED")
    
    # Test 2: Negatif
    test2 = "VAKIFBANK\nBorçlu adına herhangi bir hesap bulunmamaktadır."
    result2 = analyzer._analiz_et(test2, "vakif.pdf", "/tmp/vakif.pdf")
    print(f"\nTest 2 - Vakıf (Negatif):")
    print(f"  Durum: {result2.cevap_durumu.value}")
    assert result2.cevap_durumu == CevapDurumu.HESAP_YOK
    print("  ✅ PASSED")
    
    print("\n" + "=" * 50)
    print("✅ TÜM TESTLER BAŞARILI")
