#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
İCRA ANALİZ SİSTEMİ - Shared Core (v11.0 Oracle Edition)
========================================================
Merkezi mantık birimi. 
- Para birimi ayrıştırma (Robust Regex)
- Tarih formatlama
- İİK 106/110 Süre Motoru

Author: Arda & Claude
"""

import re
import logging
from datetime import datetime, timedelta, date
from dataclasses import dataclass
from typing import Optional, Union
from enum import Enum

# --- LOGGING ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- CONSTANTS ---
KANUN_7343_YURURLUK = datetime(2021, 11, 30)
GECICI_M18_SON_GUN = datetime(2023, 3, 8)

# --- ENUMS ---
class TakipTuru(Enum):
    ILAMSIZ = "İlamsız İcra"
    KAMBIYO = "Kambiyo"
    ILAMLI = "İlamlı İcra"
    REHIN = "Rehnin Paraya Çevrilmesi"
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
    TASINIR = "TASINIR"
    TASINMAZ = "TASINMAZ"
    BANKA_HESABI = "BANKA"
    MAAS = "MAAS"
    DIGER = "DIGER"

class RiskSeviyesi(Enum):
    DUSMUS = "❌ DÜŞMÜŞ"
    KRITIK = "🔴 KRİTİK (0-30 Gün)"
    YUKSEK = "🟠 YÜKSEK (31-90 Gün)"
    ORTA = "🟡 ORTA (91-180 Gün)"
    DUSUK = "🟢 DÜŞÜK (>180 Gün)"
    GUVENLI = "✅ GÜVENLİ"

class IslemDurumu(Enum):
    KRITIK = "🔴 KRİTİK"
    UYARI = "⚠️ UYARI"
    BILGI = "ℹ️ BİLGİ"
    TAMAMLANDI = "✅ TAMAMLANDI"

# --- DATA CLASSES ---
@dataclass
class HacizSureHesabi:
    haciz_tarihi: datetime
    mal_turu: MalTuru
    avans_yatirildi: bool
    son_gun: datetime
    kalan_gun: int
    durum: str
    risk_seviyesi: RiskSeviyesi
    onerilen_aksiyon: str
    yasal_dayanak: str

@dataclass
class AksiyonOnerisi:
    baslik: str
    aciklama: str
    oncelik: IslemDurumu
    son_tarih: Optional[datetime] = None

@dataclass
class EvrakBilgisi:
    dosya_adi: str
    evrak_turu: str
    tarih: Optional[datetime]
    ozet: str = ""
    metin: str = ""

@dataclass
class TebligatBilgisi:
    evrak_adi: str
    tarih: Optional[datetime]
    durum: TebligatDurumu
    aciklama: str

@dataclass
class HacizBilgisi:
    tur: str
    tarih: Optional[datetime]
    tutar: float = 0.0
    hedef: str = ""
    sure_106_110: Optional[int] = None

@dataclass
class DosyaAnalizSonucu:
    toplam_evrak: int = 0
    evraklar: list = None
    tebligatlar: list = None
    hacizler: list = None
    aksiyonlar: list = None
    evrak_dagilimi: dict = None
    tebligat_durumu: TebligatDurumu = TebligatDurumu.BILINMIYOR
    toplam_bloke: float = 0.0
    kritik_tarihler: list = None
    ozet_rapor: str = ""

    def __post_init__(self):
        if self.evraklar is None: self.evraklar = []
        if self.tebligatlar is None: self.tebligatlar = []
        if self.hacizler is None: self.hacizler = []
        if self.aksiyonlar is None: self.aksiyonlar = []
        if self.evrak_dagilimi is None: self.evrak_dagilimi = {}
        if self.kritik_tarihler is None: self.kritik_tarihler = []

# --- UTILITIES ---
class IcraUtils:
    @staticmethod
    def clean_text(text: str) -> str:
        if not text: return ""
        tr_map = {ord('İ'): 'i', ord('I'): 'ı', ord('Ğ'): 'ğ', ord('Ü'): 'ü', ord('Ş'): 'ş', ord('Ö'): 'ö', ord('Ç'): 'ç'}
        return text.translate(tr_map).lower()

    @staticmethod
    def tutar_parse(text: str) -> float:
        """
        Gelişmiş Tutar Ayrıştırıcı (Robust Regex)
        Hem '1.234,56' hem '1,234.56' formatlarını tanır.
        """
        if not text: return 0.0
        # Sadece sayı, nokta ve virgülü bırak
        clean = re.sub(r'[^\d.,]', '', text)
        if not clean: return 0.0
        
        # Format tespiti (Basit heuristic)
        if ',' in clean and '.' in clean:
            if clean.rfind(',') > clean.rfind('.'): # 1.234,56 (TR)
                clean = clean.replace('.', '').replace(',', '.')
            else: # 1,234.56 (US)
                clean = clean.replace(',', '')
        elif ',' in clean: # 1234,56
            clean = clean.replace(',', '.')
        # else: sadece nokta varsa genelde US formatı veya binliksiz TR, dokunma
        
        try:
            return float(clean)
        except ValueError:
            return 0.0

    @staticmethod
    def tarih_parse(text: str) -> Optional[datetime]:
        if not text: return None
        # DD.MM.YYYY veya DD/MM/YYYY
        match = re.search(r'(\d{2})[./](\d{2})[./](\d{4})', text)
        if match:
            try:
                return datetime(int(match.group(3)), int(match.group(2)), int(match.group(1)))
            except: pass
        return None

    @staticmethod
    def haciz_sure_hesapla(haciz_tarihi: datetime, mal_turu: MalTuru, avans_yatirildi: bool = False) -> HacizSureHesabi:
        bugun = datetime.now()
        
        if mal_turu in [MalTuru.BANKA_HESABI, MalTuru.MAAS]:
            return HacizSureHesabi(haciz_tarihi, mal_turu, False, datetime(2099,12,31), 9999, "DEVAM", RiskSeviyesi.GUVENLI, "Süre işlemez", "Yargıtay")

        is_new_law = haciz_tarihi >= KANUN_7343_YURURLUK
        
        if not is_new_law: # Eski Kanun
            if not avans_yatirildi and bugun > GECICI_M18_SON_GUN:
                return HacizSureHesabi(haciz_tarihi, mal_turu, False, GECICI_M18_SON_GUN, 0, "DUSMUS", RiskSeviyesi.DUSMUS, "Yeniden haciz iste", "Geçici m.18")
            base_days = 365 if mal_turu == MalTuru.TASINIR else 730
        else: # Yeni Kanun
            base_days = 180 if mal_turu == MalTuru.TASINIR else 365

        deadline = haciz_tarihi + timedelta(days=base_days)
        if mal_turu == MalTuru.TASINMAZ: deadline += timedelta(days=90) # İlan süresi

        kalan = (deadline - bugun).days
        
        if kalan < 0: risk, aksiyon = RiskSeviyesi.DUSMUS, "Haciz Düştü!"
        elif kalan <= 30: risk, aksiyon = RiskSeviyesi.KRITIK, "ACİL Satış İste!"
        elif kalan <= 90: risk, aksiyon = RiskSeviyesi.YUKSEK, "Hazırlık Yap"
        else: risk, aksiyon = RiskSeviyesi.GUVENLI, "Rutin Takip"

        return HacizSureHesabi(haciz_tarihi, mal_turu, avans_yatirildi, deadline, kalan, "DEVAM" if kalan>0 else "DUSMUS", risk, aksiyon, "İİK 106/110")
