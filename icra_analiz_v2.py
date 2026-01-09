#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
İCRA ANALİZ SİSTEMİ - Shared Core (v12.0)
=========================================
Merkezi mantık birimi.
- Para birimi ayrıştırma (Robust)
- Tarih formatlama
- İİK 106/110 Süre Motoru

Author: Arda & Claude
"""

import re
import logging
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Optional, List, Dict
from enum import Enum

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === CONSTANTS ===
KANUN_7343_YURURLUK = datetime(2021, 11, 30)

# === ENUMS ===
class TakipTuru(Enum):
    ILAMSIZ = "İlamsız İcra"
    KAMBIYO = "Kambiyo"
    ILAMLI = "İlamlı İcra"
    BILINMIYOR = "Tespit Edilemedi"

class TebligatDurumu(Enum):
    TEBLIG_EDILDI = "✅ Tebliğ Edildi"
    BILA = "❌ Bila (İade)"
    MADDE_21 = "📍 Madde 21"
    MADDE_35 = "📍 Madde 35"
    MERNIS = "🏠 Mernis"
    BEKLENIYOR = "⏳ Bekleniyor"
    BILINMIYOR = "❓ Belirsiz"

class MalTuru(Enum):
    TASINIR = "Taşınır"
    TASINMAZ = "Taşınmaz"
    BANKA = "Banka Hesabı"
    MAAS = "Maaş"

class RiskSeviyesi(Enum):
    DUSMUS = "❌ DÜŞMÜŞ"
    KRITIK = "🔴 KRİTİK"
    YUKSEK = "🟠 YÜKSEK"
    ORTA = "🟡 ORTA"
    DUSUK = "🟢 DÜŞÜK"
    GUVENLI = "✅ GÜVENLİ"

class IslemDurumu(Enum):
    KRITIK = "🔴 KRİTİK"
    UYARI = "⚠️ UYARI"
    BILGI = "ℹ️ BİLGİ"
    TAMAMLANDI = "✅ TAMAMLANDI"

class EvrakKategorisi(Enum):
    ODEME_EMRI = "Ödeme Emri"
    TEBLIGAT = "Tebligat"
    HACIZ_IHBAR = "Haciz İhbarnamesi"
    BANKA_CEVABI = "Banka Cevabı"
    KIYMET_TAKDIRI = "Kıymet Takdiri"
    SATIS_ILANI = "Satış İlanı"
    MAHKEME = "Mahkeme Kararı"
    TAKYIDAT = "Takyidat"
    DIGER = "Diğer"

class HacizTuru(Enum):
    BANKA_89_1 = "🏦 Banka 89/1"
    ARAC = "🚗 Araç"
    TASINMAZ = "🏠 Taşınmaz"
    MENKUL = "📦 Menkul"
    DIGER = "📋 Diğer"

# === DATA CLASSES ===
@dataclass
class HacizSureHesabi:
    haciz_tarihi: datetime
    mal_turu: MalTuru
    son_gun: datetime
    kalan_gun: int
    risk: RiskSeviyesi
    aksiyon: str

@dataclass
class AksiyonOnerisi:
    baslik: str
    aciklama: str
    oncelik: IslemDurumu
    son_tarih: Optional[datetime] = None

@dataclass
class EvrakBilgisi:
    dosya_adi: str
    evrak_turu: EvrakKategorisi
    tarih: Optional[datetime]
    ozet: str = ""

@dataclass
class TebligatBilgisi:
    evrak_adi: str
    tarih: Optional[datetime]
    durum: TebligatDurumu
    aciklama: str = ""

@dataclass
class HacizBilgisi:
    tur: HacizTuru
    tarih: Optional[datetime]
    hedef: str = ""
    tutar: float = 0.0
    sure_106_110: Optional[int] = None
    dosya_adi: str = ""

@dataclass
class DosyaAnalizSonucu:
    toplam_evrak: int = 0
    evraklar: List[EvrakBilgisi] = field(default_factory=list)
    tebligatlar: List[TebligatBilgisi] = field(default_factory=list)
    hacizler: List[HacizBilgisi] = field(default_factory=list)
    aksiyonlar: List[AksiyonOnerisi] = field(default_factory=list)
    evrak_dagilimi: Dict[str, int] = field(default_factory=dict)
    toplam_bloke: float = 0.0
    ozet_rapor: str = ""

# === UTILITIES ===
class IcraUtils:
    """Merkezi yardımcı fonksiyonlar"""
    
    TR_LOWER_MAP = {
        ord('İ'): 'i', ord('I'): 'ı',
        ord('Ğ'): 'ğ', ord('Ü'): 'ü',
        ord('Ş'): 'ş', ord('Ö'): 'ö',
        ord('Ç'): 'ç'
    }

    @staticmethod
    def clean_text(text: str) -> str:
        """Türkçe karakter normalizasyonu ile küçük harf"""
        if not text:
            return ""
        return text.translate(IcraUtils.TR_LOWER_MAP).lower()

    @staticmethod
    def tutar_parse(text: str) -> float:
        """
        Gelişmiş Tutar Ayrıştırıcı
        '1.234,56' -> 1234.56 (TR format)
        '1,234.56' -> 1234.56 (US format)
        '12.500' -> 12500.0 (TR thousands)
        """
        if not text:
            return 0.0
        
        clean = re.sub(r'[^\d.,]', '', str(text))
        if not clean:
            return 0.0
        
        dot_count = clean.count('.')
        comma_count = clean.count(',')
        
        # Her iki ayraç da var
        if dot_count > 0 and comma_count > 0:
            last_dot = clean.rfind('.')
            last_comma = clean.rfind(',')
            if last_comma > last_dot:
                # TR: 1.234,56
                clean = clean.replace('.', '').replace(',', '.')
            else:
                # US: 1,234.56
                clean = clean.replace(',', '')
        
        # Sadece nokta var
        elif dot_count > 0:
            if dot_count > 1:
                clean = clean.replace('.', '')
            elif re.search(r'\.\d{3}$', clean):
                clean = clean.replace('.', '')
        
        # Sadece virgül var
        elif comma_count > 0:
            if comma_count > 1:
                clean = clean.replace(',', '')
            elif re.search(r',\d{3}$', clean):
                clean = clean.replace(',', '')
            else:
                clean = clean.replace(',', '.')
        
        try:
            return float(clean)
        except ValueError:
            return 0.0

    @staticmethod
    def tarih_parse(text: str) -> Optional[datetime]:
        """DD.MM.YYYY veya DD/MM/YYYY formatını parse et"""
        if not text:
            return None
        match = re.search(r'(\d{2})[./](\d{2})[./](\d{4})', text)
        if match:
            try:
                return datetime(int(match.group(3)), int(match.group(2)), int(match.group(1)))
            except ValueError:
                pass
        return None

    @staticmethod
    def haciz_sure_hesapla(haciz_tarihi: datetime, mal_turu: MalTuru) -> HacizSureHesabi:
        """İİK 106/110 süre hesaplama"""
        bugun = datetime.now()
        
        # Banka ve maaş hacizlerinde süre işlemez
        if mal_turu in [MalTuru.BANKA, MalTuru.MAAS]:
            return HacizSureHesabi(
                haciz_tarihi, mal_turu,
                datetime(2099, 12, 31), 9999,
                RiskSeviyesi.GUVENLI, "Süre işlemez"
            )
        
        # Yeni kanun (7343) sonrası
        if mal_turu == MalTuru.TASINIR:
            base_days = 180 if haciz_tarihi >= KANUN_7343_YURURLUK else 365
        else:  # TASINMAZ
            base_days = 365 if haciz_tarihi >= KANUN_7343_YURURLUK else 730
        
        deadline = haciz_tarihi + timedelta(days=base_days)
        kalan = (deadline - bugun).days
        
        if kalan < 0:
            risk, aksiyon = RiskSeviyesi.DUSMUS, "Haciz düştü! Yeniden haciz gerekli"
        elif kalan <= 30:
            risk, aksiyon = RiskSeviyesi.KRITIK, "ACİL satış talebi!"
        elif kalan <= 90:
            risk, aksiyon = RiskSeviyesi.YUKSEK, "Satış hazırlığı yap"
        elif kalan <= 180:
            risk, aksiyon = RiskSeviyesi.ORTA, "Planla"
        else:
            risk, aksiyon = RiskSeviyesi.GUVENLI, "Rutin takip"
        
        return HacizSureHesabi(haciz_tarihi, mal_turu, deadline, kalan, risk, aksiyon)


# === TEST ===
if __name__ == "__main__":
    print("🧪 IcraUtils Test")
    print("=" * 40)
    
    # Tutar testleri
    test_cases = [
        ("1.234,56", 1234.56),
        ("12.500", 12500.0),
        ("1,234.56", 1234.56),
        ("45.678,90 TL", 45678.90),
    ]
    
    for inp, expected in test_cases:
        result = IcraUtils.tutar_parse(inp)
        status = "✅" if abs(result - expected) < 0.01 else "❌"
        print(f"{status} '{inp}' -> {result} (beklenen: {expected})")
    
    print("\n✅ Testler tamamlandı")
