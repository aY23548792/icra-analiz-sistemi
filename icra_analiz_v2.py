#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
İCRA ANALİZ SİSTEMİ - Shared Core (v11.0 Oracle Edition)
========================================================
Centralized logic for Turkish Enforcement Law (İİK).
Incorporates "Context-Aware" parsing and robust deadline engines.

Features:
- İİK 106/110 Deadline Engine (Law 7343 & Provisional Art. 18)
- Robust Regex Patterns (Money, Date, IBAN, Bank Name)
- UDF (XML) Parsing support
- Standardized Enums & Data Classes for consistent analysis
"""

import re
import logging
import os
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import List, Dict, Optional, Union
from enum import Enum
import pdfplumber

# --- LOGGING ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- CONSTANTS & LEGAL THRESHOLDS ---
KANUN_7343_YURURLUK = datetime(2021, 11, 30)
GECICI_M18_SON_GUN = datetime(2023, 3, 8)

BANKA_LISTESI = [
    'Ziraat', 'Halkbank', 'Vakıfbank', 'Akbank', 'Garanti', 
    'İş Bankası', 'Yapı Kredi', 'Finansbank', 'Denizbank', 
    'TEB', 'ING', 'HSBC', 'Şekerbank', 'Kuveyt Türk', 'Türkiye Finans', 
    'Albaraka', 'Vakıf Katılım', 'Ziraat Katılım', 'Emlak Katılım', 
    'Odeabank', 'Fibabanka', 'Anadolubank', 'Burgan', 'Citibank'
]

# --- ENUMS ---

class TakipTuru(Enum):
    ILAMSIZ = "İlamsız İcra (Örnek 7)"
    KAMBIYO = "Kambiyo (Örnek 10)"
    ILAMLI = "İlamlı İcra"
    REHIN = "Rehnin Paraya Çevrilmesi"
    BILINMIYOR = "Tespit Edilemedi"

class MalTuru(Enum):
    TASINIR = "TASINIR"        # Araç, menkul - 6 ay (yeni) / 1 yıl (eski)
    TASINMAZ = "TASINMAZ"      # Ev, arsa - 1 yıl + 3 ay ilan
    BANKA_HESABI = "BANKA"     # Süre yok
    MAAS = "MAAS"              # Süre yok
    DIGER = "DIGER"

class RiskSeviyesi(Enum):
    DUSMUS = "❌ DÜŞMÜŞ"
    KRITIK = "🔴 KRİTİK (0-30 Gün)"
    YUKSEK = "🟠 YÜKSEK (31-90 Gün)"
    ORTA = "🟡 ORTA (91-180 Gün)"
    DUSUK = "🟢 DÜŞÜK (>180 Gün)"
    GUVENLI = "✅ GÜVENLİ"

# --- DATA CLASSES ---

@dataclass
class HacizSureHesabi:
    haciz_tarihi: datetime
    mal_turu: MalTuru
    avans_yatirildi: bool
    avans_tarihi: Optional[datetime]
    son_gun: datetime
    kalan_gun: int
    durum: str  # "DEVAM" veya "DUSMUS"
    risk_seviyesi: RiskSeviyesi
    onerilen_aksiyon: str
    yasal_dayanak: str

# --- CORE UTILITIES ---

class IcraUtils:
    """Static utility methods for parsing and legal calculations."""

    @staticmethod
    def clean_text(text: str) -> str:
        """Normalize Turkish text for robust regex matching."""
        if not text: return ""
        tr_map = {
            ord('İ'): 'i', ord('I'): 'ı', ord('Ğ'): 'ğ',
            ord('Ü'): 'ü', ord('Ş'): 'ş', ord('Ö'): 'ö', ord('Ç'): 'ç'
        }
        return text.translate(tr_map).lower()

    @staticmethod
    def tutar_parse(text: str) -> float:
        """
        Oracle-Grade money parsing. 
        Handles Turkish (1.234,56) and US (1,234.56) formats.
        """
        if not text: return 0.0
        
        # Remove currency symbols and whitespace
        clean = re.sub(r'[TL₺TRYEURUSD\s]', '', text)
        
        # Check format: if there's a dot followed by 3 digits, it's likely Turkish thousands separator
        if re.search(r'\d\.\d{3}', clean):
            clean = clean.replace('.', '').replace(',', '.')
        elif ',' in clean and '.' not in clean: # Simple 1234,56
            clean = clean.replace(',', '.')
        else: # US format or no separators
            clean = clean.replace(',', '')
            
        try:
            return float(clean)
        except ValueError:
            return 0.0

    @staticmethod
    def tarih_parse(text: str) -> Optional[datetime]:
        """Detects dates in various Turkish formats."""
        if not text: return None
        
        # 1. Numeric Formats (DD.MM.YYYY or DD/MM/YYYY)
        numeric_match = re.search(r'(\d{1,2})[./](\d{1,2})[./](\d{4})', text)
        if numeric_match:
            try:
                d, m, y = map(int, numeric_match.groups())
                return datetime(y, m, d)
            except ValueError:
                pass

        # 2. Turkish Month Formats (e.g., "15 Ocak 2025")
        TR_MONTHS = {
            'ocak': 1, 'şubat': 2, 'mart': 3, 'nisan': 4, 'mayıs': 5, 'haziran': 6,
            'temmuz': 7, 'ağustos': 8, 'eylül': 9, 'ekim': 10, 'kasım': 11, 'aralık': 12
        }
        text_lower = IcraUtils.clean_text(text)
        for month, num in TR_MONTHS.items():
            pattern = rf'(\d{{1,2}})\s*{month}\s*(\d{{4}})'
            match = re.search(pattern, text_lower)
            if match:
                try:
                    d, y = int(match.group(1)), int(match.group(2))
                    return datetime(y, num, d)
                except ValueError:
                    continue
        
        return None

    @staticmethod
    def banka_tespit(text: str) -> Optional[str]:
        """Identifies bank name from text using the Oracle list."""
        text_lower = IcraUtils.clean_text(text)
        for banka in BANKA_LISTESI:
            if IcraUtils.clean_text(banka) in text_lower:
                return banka
        return None

    @staticmethod
    def dosya_no_parse(text: str) -> Optional[str]:
        """Extracts Enforcement File Number (e.g., 2025/12345)."""
        pattern = r'(\d{4})\s*/\s*(\d+)'
        match = re.search(pattern, text)
        if match:
            return f"{match.group(1)}/{match.group(2)}"
        return None

    @staticmethod
    def excel_column_mapping(df_columns: List[str]) -> Dict[str, str]:
        """Maps varying Excel column names to internal standard keys."""
        mappings = {
            'haciz_tarihi': ['haciz tarihi', 'hac_tar', 'tarih', 'hacz tarihi'],
            'mal_turu': ['mal türü', 'mal tipi', 'tür', 'tur', 'tasinir_tasinmaz'],
            'dosya_no': ['dosya no', 'esas', 'esas no', 'dosya numarası'],
            'tutar': ['tutar', 'alacak', 'borç', 'miktar', 'toplam']
        }
        result = {}
        for key, variations in mappings.items():
            for col in df_columns:
                if any(v in IcraUtils.clean_text(col) for v in variations):
                    result[key] = col
                    break
        return result

    @staticmethod
    def read_udf(udf_path: str) -> str:
        """Reads UDF (XML based) content and returns clean text."""
        try:
            with zipfile.ZipFile(udf_path, 'r') as zf:
                if 'content.xml' in zf.namelist():
                    xml_data = zf.read('content.xml')
                    root = ET.fromstring(xml_data)
                    text_content = []
                    for elem in root.iter():
                        if elem.text:
                            text_content.append(elem.text.strip())
                        if elem.tail:
                            text_content.append(elem.tail.strip())
                    return "\n".join(filter(None, text_content))
                return ""
        except Exception as e:
            logger.error(f"UDF reading error {udf_path}: {e}")
            return ""

    @staticmethod
    def read_file_content(file_path: str) -> str:
        """Helper to extract text from PDF, UDF, or Text files."""
        if not os.path.exists(file_path):
            return ""
        
        ext = os.path.splitext(file_path)[1].lower()
        try:
            if ext == '.pdf':
                text = ""
                with pdfplumber.open(file_path) as pdf:
                    for page in pdf.pages:
                        extracted = page.extract_text()
                        if extracted:
                            text += extracted + "\n"
                return text
            elif ext == '.udf':
                return IcraUtils.read_udf(file_path)
            elif ext == '.xml':
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    xml_data = f.read()
                    root = ET.fromstring(xml_data)
                    return "".join(root.itertext())
            else:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    return f.read()
        except Exception as e:
            logger.error(f"File reading error {file_path}: {e}")
            return ""

    @staticmethod
    def haciz_sure_hesapla(
        haciz_tarihi: Union[str, datetime],
        mal_turu: Union[str, MalTuru],
        avans_yatirildi: bool = False,
        avans_tarihi: Optional[Union[str, datetime]] = None
    ) -> HacizSureHesabi:
        """
        Oracle-Grade Seizure Deadline Calculator (İİK 106/110)
        Full support for Law 7343 transition and Provisional Art. 18.
        """
        # 1. Normalize Inputs
        if isinstance(haciz_tarihi, str):
            try:
                haciz_dt = datetime.strptime(haciz_tarihi, "%Y-%m-%d")
            except:
                haciz_dt = IcraUtils.tarih_parse(haciz_tarihi) or datetime.now()
        else:
            haciz_dt = haciz_tarihi

        if isinstance(avans_tarihi, str):
            try:
                avans_dt = datetime.strptime(avans_tarihi, "%Y-%m-%d")
            except:
                avans_dt = IcraUtils.tarih_parse(avans_tarihi)
        else:
            avans_dt = avans_tarihi

        if isinstance(mal_turu, str):
            mal_str = mal_turu.upper()
            if 'TAŞINMAZ' in mal_str or 'GAYRİMENKUL' in mal_str: mal = MalTuru.TASINMAZ
            elif 'BANKA' in mal_str: mal = MalTuru.BANKA_HESABI
            elif 'MAAŞ' in mal_str: mal = MalTuru.MAAS
            else: mal = MalTuru.TASINIR
        else:
            mal = mal_turu

        bugun = datetime.now()

        # 2. Bank/Salary Exception
        if mal in [MalTuru.BANKA_HESABI, MalTuru.MAAS]:
            return HacizSureHesabi(
                haciz_tarihi=haciz_dt, mal_turu=mal, avans_yatirildi=False, avans_tarihi=None,
                son_gun=datetime(2099, 12, 31), kalan_gun=9999, durum="DEVAM",
                risk_seviyesi=RiskSeviyesi.GUVENLI,
                onerilen_aksiyon="Banka/Maaş hacizlerinde süre işlemez. Rutin kontrol yapın.",
                yasal_dayanak="Yargıtay İçtihatları"
            )

        # 3. Determine Regime & Duration
        is_new_law = haciz_dt >= KANUN_7343_YURURLUK
        
        if not is_new_law:
            # PROVISIONAL ARTICLE 18 CHECK (Old Law Seizures)
            if not avans_yatirildi or (avans_dt and avans_dt > GECICI_M18_SON_GUN):
                return HacizSureHesabi(
                    haciz_tarihi=haciz_dt, mal_turu=mal, avans_yatirildi=avans_yatirildi, avans_tarihi=avans_dt,
                    son_gun=GECICI_M18_SON_GUN, kalan_gun=(GECICI_M18_SON_GUN - bugun).days,
                    durum="DUSMUS", risk_seviyesi=RiskSeviyesi.DUSMUS,
                    onerilen_aksiyon="HACİZ DÜŞMÜŞ (Geçici m.18). Yeniden haciz isteyin.",
                    yasal_dayanak="7343 s.K. Geçici Madde 18"
                )
            base_days = 365 if mal == MalTuru.TASINIR else 730
        else:
            # New Law (Post 30.11.2021)
            base_days = 180 if mal == MalTuru.TASINIR else 365

        # 4. Calculate Deadline
        # Hard deadline for requesting sale
        deadline = haciz_dt + timedelta(days=base_days)
        if mal == MalTuru.TASINMAZ:
            deadline += timedelta(days=90) # Standard extension for immovable procedures

        kalan = (deadline - bugun).days

        # 5. Risk Assessment
        if kalan < 0:
            risk = RiskSeviyesi.DUSMUS
            aksiyon = "HACİZ DÜŞMÜŞ! Hemen yeniden haciz gönder."
        elif kalan <= 30:
            risk = RiskSeviyesi.KRITIK
            aksiyon = "ACİL! Satış talebi aç ve masrafı yatır."
        elif kalan <= 90:
            risk = RiskSeviyesi.YUKSEK
            aksiyon = "Satış hazırlıklarına başla (Kıymet takdiri)."
        elif kalan <= 180:
            risk = RiskSeviyesi.ORTA
            aksiyon = "Takvime işle, kıymet takdiri planla."
        else:
            risk = RiskSeviyesi.DUSUK
            aksiyon = "Rutin takip."

        return HacizSureHesabi(
            haciz_tarihi=haciz_dt, mal_turu=mal, avans_yatirildi=avans_yatirildi, avans_tarihi=avans_dt,
            son_gun=deadline, kalan_gun=max(0, kalan), durum="DEVAM" if kalan > 0 else "DUSMUS",
            risk_seviyesi=risk, onerilen_aksiyon=aksiyon,
            yasal_dayanak=f"İİK m.{'106' if mal==MalTuru.TASINIR else '110'} ({'Yeni' if is_new_law else 'Eski'})"
        )
