#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HACİZ İHBAR ANALYZER v5.0 (App.py Uyumlu)
=========================================
Banka cevaplarını analiz eder. App.py ile tam uyumlu Enum yapısı kullanır.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from enum import Enum
from datetime import datetime
import re
import os
import zipfile

# --- APP.PY'NİN BEKLEDİĞİ ENUMLAR ---
class IhbarTuru(Enum):
    IHBAR_89_1 = "89/1 - Birinci Haciz İhbarnamesi"
    IHBAR_89_2 = "89/2 - İkinci Haciz İhbarnamesi"
    IHBAR_89_3 = "89/3 - Üçüncü Haciz İhbarnamesi"
    BILINMIYOR = "Tespit Edilemedi"

class MuhatapTuru(Enum):
    BANKA = "🏦 Banka"
    TUZEL_KISI = "🏢 Tüzel Kişi"
    GERCEK_KISI = "👤 Gerçek Kişi"
    KAMU_KURUMU = "🏛️ Kamu Kurumu"
    BILINMIYOR = "❓ Tespit Edilemedi"

class CevapDurumu(Enum):
    BLOKE_VAR = "💰 BLOKE VAR"
    HESAP_VAR_BAKIYE_YOK = "📋 Hesap Var - Bakiye Yok"
    HESAP_YOK = "❌ Hesap Bulunamadı"
    KISMI_BLOKE = "💵 Kısmi Bloke"
    ALACAK_VAR = "💵 Alacak/Hak Var"
    ALACAK_YOK = "❌ Alacak/Hak Yok"
    ODEME_YAPILDI = "✅ Ödeme Yapıldı"
    ITIRAZ = "⚖️ İtiraz Edildi"
    CEVAP_YOK = "⚠️ Cevap Gelmedi"
    PARSE_HATASI = "❓ İncelenmeli"

@dataclass
class HacizIhbarCevabi:
    muhatap: str
    muhatap_turu: MuhatapTuru
    ihbar_turu: IhbarTuru
    cevap_durumu: CevapDurumu
    cevap_tarihi: Optional[datetime]
    bloke_tutari: float = 0.0
    sonraki_adim: str = ""
    aciklama: str = ""
    # Ek alanlar
    alacak_tutari: float = 0.0
    odenen_tutar: float = 0.0
    iban_listesi: List[str] = field(default_factory=list)

@dataclass
class HacizIhbarAnalizSonucu:
    toplam_dosya: int = 0
    cevap_gelen: int = 0
    cevap_gelmeyen: int = 0
    bloke_sayisi: int = 0
    toplam_bloke: float = 0.0
    banka_sayisi: int = 0
    tuzel_kisi_sayisi: int = 0
    gercek_kisi_sayisi: int = 0
    toplam_alacak: float = 0.0
    toplam_odenen: float = 0.0
    cevaplar: List[HacizIhbarCevabi] = field(default_factory=list)
    eksik_ihbarlar: List[Dict] = field(default_factory=list)
    ozet_rapor: str = ""

class HacizIhbarAnalyzer:
    
    # Banka İsimleri
    BANKALAR = [
        "Ziraat", "Vakıf", "Halk", "Garanti", "Yapı Kredi", "İş Bankası", 
        "Akbank", "QNB", "Deniz", "TEB", "Kuveyt", "Albaraka", "Finans", "Odea"
    ]
    
    # Regex Patterns
    MENFI_PATTERNS = [
        r'hesap\s*(?:kaydı|bilgisi)?\s*(?:bulunma|yok|mevcut\s*değil)',
        r'borçlu\s*adına\s*kayıt\s*yok',
        r'herhangi\s*bir\s*hak\s*ve\s*alacağa\s*rastlanma',
        r'menfi\s*cevap',
        r'haciz\s*kaydı\s*işlenememiştir'
    ]
    
    BAKIYE_YOK_PATTERNS = [
        r'bakiye\s*(?:bulunma|yok|yetersiz)',
        r'bakiye\s*:\s*0[,.]00',
        r'blokeli\s*tutar\s*:\s*0',
        r'üzerine\s*haciz\s*şerhi\s*işlen' # Tutar yoksa sadece şerh işlenmiştir
    ]

    BLOKE_CONTEXT = re.compile(
        r'(?:bloke|haciz|tedbir)(?:.{0,50}?)(?:tutar|bedel|miktar|üzerine)?.{0,20}?'
        r'(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?)', 
        re.IGNORECASE | re.DOTALL
    )

    def batch_analiz(self, dosya_yollari: List[str]) -> HacizIhbarAnalizSonucu:
        cevaplar = []
        
        # 1. Dosyaları Düzleştir (Recursive)
        tum_dosyalar = self._dosyalari_topla(dosya_yollari)
        
        # 2. Analiz Et
        for dosya_yolu in tum_dosyalar:
            try:
                # UDF ise UDF oku, değilse düz oku
                metin = self._dosya_oku(dosya_yolu)
                if not metin: continue
                
                cevap = self.analyze_response(metin, os.path.basename(dosya_yolu))
                cevaplar.append(cevap)
            except Exception as e:
                print(f"Hata ({dosya_yolu}): {e}")

        return self._sonuc_olustur(cevaplar)

    def analyze_response(self, text: str, filename: str) -> HacizIhbarCevabi:
        text_clean = text.lower()
        muhatap_adi, muhatap_turu = self._muhatap_belirle(text)
        
        durum = CevapDurumu.PARSE_HATASI
        tutar = 0.0
        sonraki = "İncele"
        
        # --- MANTIK ---
        
        # 1. Negatif Kontrol (Öncelikli)
        is_menfi = any(re.search(p, text_clean, re.IGNORECASE) for p in self.MENFI_PATTERNS)
        
        if is_menfi:
            durum = CevapDurumu.HESAP_YOK
            sonraki = "89/1 Başka bankaya gönder"
        
        # 2. Bakiye Yok Kontrolü
        elif any(re.search(p, text_clean, re.IGNORECASE) for p in self.BAKIYE_YOK_PATTERNS):
            durum = CevapDurumu.HESAP_VAR_BAKIYE_YOK
            sonraki = "89/2 Gönder (Haciz şerhi işlendi ama para yok)"
            
        # 3. Pozitif Kontrol (Bloke)
        else:
            match = self.BLOKE_CONTEXT.search(text)
            if match:
                raw = match.group(1)
                tutar = self._tutar_parse(raw)
                if tutar > 0:
                    durum = CevapDurumu.BLOKE_VAR
                    sonraki = "MAHSUP TALEBİ GÖNDER!"
                else:
                    durum = CevapDurumu.HESAP_VAR_BAKIYE_YOK
                    sonraki = "89/2 Gönder"
            elif "bloke" in text_clean or "haciz" in text_clean:
                # Tutar okuyamadık ama bloke kelimesi var
                durum = CevapDurumu.BLOKE_VAR
                sonraki = "Manuel Kontrol (Tutar Okunamadı)"

        return HacizIhbarCevabi(
            muhatap=muhatap_adi,
            muhatap_turu=muhatap_turu,
            ihbar_turu=IhbarTuru.IHBAR_89_1, # Varsayılan
            cevap_durumu=durum,
            cevap_tarihi=datetime.now(),
            bloke_tutari=tutar,
            sonraki_adim=sonraki,
            aciklama=f"{durum.value} - {tutar}"
        )

    def _muhatap_belirle(self, text: str) -> Tuple[str, MuhatapTuru]:
        for bank in self.BANKALAR:
            if bank.lower() in text.lower():
                return (f"{bank} Bankası", MuhatapTuru.BANKA)
        
        if "a.ş." in text.lower() or "ltd." in text.lower():
            return ("Şirket", MuhatapTuru.TUZEL_KISI)
            
        return ("Bilinmeyen", MuhatapTuru.BILINMIYOR)

    def _tutar_parse(self, text: str) -> float:
        if not text: return 0.0
        clean = text.replace('.', '').replace(',', '.')
        try:
            return float(clean)
        except:
            return 0.0

    def _dosyalari_topla(self, yollar: List[str]) -> List[str]:
        # Recursive dosya toplama (Neat PDF'teki gibi)
        dosyalar = []
        for yol in yollar:
            if os.path.isfile(yol) and yol.endswith('.zip'):
                # Geçici olarak açıp içine bakmak gerekir, basitleştirilmiş:
                try:
                    z = zipfile.ZipFile(yol)
                    # Sadece isimleri değil içerikleri lazım, bu yüzden app.py'de
                    # unzip edilmiş hali gelirse daha iyi.
                    # Şimdilik app.py'nin unzip ettiğini varsayalım.
                    pass
                except: pass
            elif os.path.isdir(yol):
                for root, _, files in os.walk(yol):
                    for f in files:
                        if f.endswith(('.pdf', '.udf', '.txt')):
                            dosyalar.append(os.path.join(root, f))
            else:
                dosyalar.append(yol)
        return dosyalar

    def _dosya_oku(self, yol):
        try:
            if yol.endswith('.udf'):
                # Basit UDF okuma
                with zipfile.ZipFile(yol, 'r') as zf:
                    if 'content.xml' in zf.namelist():
                        return zf.read('content.xml').decode('utf-8', errors='ignore')
            elif yol.endswith('.txt'):
                with open(yol, 'r', encoding='utf-8') as f: return f.read()
            # PDF okuma (pdfplumber gerektirir, basitlik için atlandı, text gelmeli)
            return ""
        except:
            return ""

    def _sonuc_olustur(self, cevaplar: List[HacizIhbarCevabi]) -> HacizIhbarAnalizSonucu:
        toplam_bloke = sum(c.bloke_tutari for c in cevaplar if c.bloke_tutari)
        banka_sayisi = len(set(c.muhatap for c in cevaplar if c.muhatap_turu == MuhatapTuru.BANKA))
        
        return HacizIhbarAnalizSonucu(
            toplam_dosya=len(cevaplar),
            cevap_gelen=len(cevaplar),
            toplam_bloke=toplam_bloke,
            bloke_sayisi=len([c for c in cevaplar if c.cevap_durumu == CevapDurumu.BLOKE_VAR]),
            banka_sayisi=banka_sayisi,
            cevaplar=cevaplar,
            ozet_rapor=f"Toplam {len(cevaplar)} cevap, {toplam_bloke} TL bloke."
        )
