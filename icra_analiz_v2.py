#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
İCRA DOSYA ANALİZ SİSTEMİ - Shared Core (v11.0)
===============================================
Common data structures, enums, and utility functions shared across modules.
Contains logic for:
- Legal Deadlines (106/110)
- Document Categorization
- Regex Pattern Matching

Author: Arda & Claude
"""

import os
import re
import zipfile
import tempfile
import shutil
import logging
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Any, Union
from enum import Enum

# --- LOGGING ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- OPTIONAL IMPORTS ---
try:
    import pdfplumber
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False

# ============================================================================
# ENUMS
# ============================================================================

class TakipTuru(Enum):
    ILAMSIZ = "İlamsız İcra (Örnek 7)"
    KAMBIYO = "Kambiyo Senetlerine Özgü (Örnek 10)"
    ILAMLI = "İlamlı İcra (Örnek 4-5)"
    REHIN = "Rehnin Paraya Çevrilmesi"
    IFLAS = "İflas Takibi"
    BILINMIYOR = "Tespit Edilemedi"

class TebligatDurumu(Enum):
    TEBLIG_EDILDI = "✅ Tebliğ Edildi"
    BILA = "⚠️ Bila (Tebliğ Edilemedi)"
    MADDE_21 = "📍 Madde 21 (Muhtar/Komşu)"
    MADDE_35 = "📍 Madde 35 (Eski Adres)"
    MERNIS = "🏠 Mernis Adresi"
    MERSIS = "🏢 Mersis Adresi"
    ILANEN = "📰 İlanen Tebliğ"
    BEKLENIYOR = "⏳ Tebligat Bekleniyor"
    BILINMIYOR = "❓ Durum Belirsiz"

class HacizTuru(Enum):
    BANKA_89_1 = "🏦 Banka 89/1"
    BANKA_89_2 = "🏦 Banka 89/2"
    BANKA_89_3 = "🏦 Banka 89/3"
    SGK_MAAS = "💼 SGK Maaş"
    ARAC = "🚗 Araç Haczi"
    TASINMAZ = "🏠 Taşınmaz Haczi"
    MENKUL = "📦 Menkul Haczi"
    POSTA_CEKI = "📮 Posta Çeki"
    DIGER = "📋 Diğer"

class EvrakKategorisi(Enum):
    ODEME_EMRI = "Ödeme Emri"
    TEBLIGAT_MAZBATA = "Tebligat Mazbatası"
    HACIZ_IHBARNAMESI = "Haciz İhbarnamesi"
    HACIZ_TUTANAGI = "Haciz Tutanağı"
    KIYMET_TAKDIRI = "Kıymet Takdiri"
    SATIS_ILANI = "Satış İlanı"
    TAKYIDAT = "Takyidat/Tapu Kaydı"
    MAHKEME_KARARI = "Mahkeme Kararı"
    TALEP_DILEKCE = "Talep/Dilekçe"
    BANKA_CEVABI = "Banka Cevabı"
    BILINMIYOR = "Diğer Evrak"

class IslemDurumu(Enum):
    KRITIK = "🔴 KRİTİK"
    UYARI = "🟠 UYARI"
    BILGI = "🔵 BİLGİ"
    TAMAMLANDI = "✅ TAMAMLANDI"

# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class AksiyonOnerisi:
    """Action item for the lawyer"""
    baslik: str
    aciklama: str
    oncelik: IslemDurumu
    son_tarih: Optional[datetime] = None

@dataclass
class EvrakBilgisi:
    """Metadata for a single document"""
    dosya_adi: str
    evrak_turu: EvrakKategorisi
    tarih: Optional[datetime]
    metin_ozeti: str  # First 200 chars or relevant snippet
    sayfa_sayisi: int = 1

@dataclass
class TebligatBilgisi:
    """Notification details"""
    evrak_adi: str
    durum: TebligatDurumu
    tarih: Optional[datetime]
    alici: str = ""
    adres: str = ""
    mazbata_metni: str = ""

@dataclass
class HacizBilgisi:
    """Seizure details"""
    tur: HacizTuru
    tarih: Optional[datetime]
    hedef: str          # Banka adı, Plaka, Ada/Parsel
    tutar: float = 0.0
    dosya_adi: str = ""
    
    # 106/110 Calculation
    dusme_tarihi: Optional[datetime] = None
    sure_106_110: Optional[int] = None  # Remaining days
    satis_istendi: bool = False

@dataclass
class DosyaAnalizSonucu:
    """Master result object for File Analysis"""
    dosya_no: str = ""
    takip_turu: TakipTuru = TakipTuru.BILINMIYOR
    
    # Statistics
    toplam_evrak: int = 0
    evrak_dagilimi: Dict[str, int] = field(default_factory=dict)
    
    # Financials - NOTE: toplam_bloke is NOT calculated here!
    # It is ONLY calculated in haciz_ihbar_analyzer.py (Single Source of Truth)
    toplam_bloke: float = 0.0
    toplam_dosya_borcu: float = 0.0
    
    # Lists
    evraklar: List[EvrakBilgisi] = field(default_factory=list)
    tebligatlar: List[TebligatBilgisi] = field(default_factory=list)
    hacizler: List[HacizBilgisi] = field(default_factory=list)
    aksiyonlar: List[AksiyonOnerisi] = field(default_factory=list)
    
    # State
    tebligat_durumu: TebligatDurumu = TebligatDurumu.BILINMIYOR
    ozet_rapor: str = ""

# ============================================================================
# SHARED UTILITIES
# ============================================================================

class IcraUtils:
    """Static utility methods for parsing and conversions."""
    
    # TR Character Map (class-level for performance)
    TR_MAP = {
        ord('İ'): 'i', ord('I'): 'ı', ord('Ğ'): 'ğ',
        ord('Ü'): 'ü', ord('Ş'): 'ş', ord('Ö'): 'ö', ord('Ç'): 'ç'
    }

    @staticmethod
    def clean_text(text: str) -> str:
        """Normalize Turkish text to lowercase with proper character handling."""
        if not text: return ""
        return text.translate(IcraUtils.TR_MAP).lower()

    @staticmethod
    def extract_date(text: str) -> Optional[datetime]:
        """Find the most likely date in text."""
        if not text: return None
        # Format: DD.MM.YYYY or DD/MM/YYYY
        matches = re.findall(r'(\d{2})[./](\d{2})[./](\d{4})', text)
        valid_dates = []
        for d, m, y in matches:
            try:
                dt = datetime(int(y), int(m), int(d))
                # Sanity check: Date must be reasonable (1990-2030)
                if 1990 <= dt.year <= 2030:
                    valid_dates.append(dt)
            except ValueError:
                continue
        
        # Heuristic: The most recent date is usually the document date
        return max(valid_dates) if valid_dates else None

    @staticmethod
    def extract_money(text: str) -> float:
        """Extract monetary value (TL)."""
        if not text: return 0.0
        # Look for patterns ending in TL, TRY
        pattern = r'(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?)\s*(?:TL|₺|TRY)'
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            # Handle 1.234,56 vs 1,234.56
            val_str = match.group(1)
            if ',' in val_str[-3:]: # TR format
                val_str = val_str.replace('.', '').replace(',', '.')
            else:
                val_str = val_str.replace(',', '')
            try:
                return float(val_str)
            except:
                pass
        return 0.0

    @staticmethod
    def extract_iban(text: str) -> List[str]:
        """Extract TR IBANs."""
        # Pattern: TR followed by 24 digits (with optional spaces)
        raw_matches = re.findall(r'TR\s*\d{2}\s*\d{4}\s*\d{4}\s*\d{4}\s*\d{4}\s*\d{4}\s*\d{2}', text)
        # Clean up spaces
        cleaned = [re.sub(r'\s', '', m) for m in raw_matches]
        return list(set(cleaned))

    @staticmethod
    def read_file_content(path: str) -> str:
        """Read content from PDF, XML (UDF), or TXT."""
        ext = os.path.splitext(path)[1].lower()
        text = ""
        
        try:
            if ext == '.pdf' and PDF_AVAILABLE:
                with pdfplumber.open(path) as pdf:
                    for page in pdf.pages:
                        extracted = page.extract_text()
                        if extracted: text += extracted + "\n"
            
            elif ext == '.udf':
                # UDF is actually a ZIP containing content.xml
                try:
                    with zipfile.ZipFile(path, 'r') as zf:
                        if 'content.xml' in zf.namelist():
                            xml_content = zf.read('content.xml').decode('utf-8', errors='ignore')
                            # Simple strip tags (faster than XML parsing for just text)
                            text = re.sub(r'<[^>]+>', ' ', xml_content)
                except zipfile.BadZipFile:
                    logger.warning(f"UDF file is not a valid ZIP: {path}")
            
            elif ext in ['.txt', '.xml', '.html']:
                with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                    text = f.read()
                    
        except Exception as e:
            logger.error(f"Error reading file {path}: {e}")
            
        return text

# ============================================================================
# BASE ANALYZER CLASS
# ============================================================================

class BaseAnalyzer:
    """Parent class for specific analyzers. Provides temp directory management."""
    
    def __init__(self):
        self.temp_dir = None
    
    def setup_temp_dir(self) -> str:
        """Create a temporary directory for file operations."""
        self.temp_dir = tempfile.mkdtemp()
        return self.temp_dir
    
    def cleanup(self):
        """Remove temporary directory and all contents."""
        if self.temp_dir and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)
            self.temp_dir = None

    def unzip_file(self, zip_path: str, target_dir: str):
        """Extract ZIP file to target directory."""
        with zipfile.ZipFile(zip_path, 'r') as zf:
            zf.extractall(target_dir)

# ============================================================================
# TEST RUNNER
# ============================================================================
if __name__ == "__main__":
    print("🧪 Testing IcraUtils...")
    print("=" * 50)
    
    # Test 1: Date Extraction
    txt_date = "Tarih: 15.10.2023 ve vade tarihi 01/01/2024"
    dt = IcraUtils.extract_date(txt_date)
    print(f"Test 1 - Date Extracted: {dt}")
    assert dt is not None
    assert dt.year == 2024  # Most recent date
    print("  ✅ PASSED")
    
    # Test 2: Money Extraction
    txt_money = "Borç miktarı 123.456,78 TL dir."
    amt = IcraUtils.extract_money(txt_money)
    print(f"Test 2 - Money Extracted: {amt}")
    assert amt == 123456.78
    print("  ✅ PASSED")
    
    # Test 3: Clean Text (Turkish characters)
    txt_dirty = "İĞNE ŞÖYLE"
    cleaned = IcraUtils.clean_text(txt_dirty)
    print(f"Test 3 - Cleaned: '{cleaned}'")
    assert cleaned == "iğne şöyle"
    print("  ✅ PASSED")
    
    # Test 4: IBAN Extraction
    txt_iban = "IBAN: TR33 0006 1005 1978 6457 8413 26 numaralı hesaba"
    ibans = IcraUtils.extract_iban(txt_iban)
    print(f"Test 4 - IBANs: {ibans}")
    assert len(ibans) == 1
    assert ibans[0] == "TR330006100519786457841326"
    print("  ✅ PASSED")
    
    print("\n" + "=" * 50)
    print("✅ TÜM TESTLER BAŞARIYLA GEÇTİ!")
    print("=" * 50)
