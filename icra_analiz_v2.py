#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
İCRA ANALİZ SİSTEMİ - Shared Core v12.5
=======================================
Merkezi yardımcı fonksiyonlar ve veri yapıları.

Author: Arda & Claude
"""

import re
from datetime import datetime, timedelta
from typing import Optional

# === CONSTANTS ===
KANUN_7343_YURURLUK = datetime(2021, 11, 30)

class IcraUtils:
    """Merkezi yardımcı fonksiyonlar"""
    
    # Türkçe karakter dönüşüm haritası
    TR_LOWER_MAP = {
        ord('İ'): 'i', ord('I'): 'ı',
        ord('Ğ'): 'ğ', ord('Ü'): 'ü',
        ord('Ş'): 'ş', ord('Ö'): 'ö',
        ord('Ç'): 'ç'
    }
    
    TR_UPPER_MAP = {
        ord('i'): 'İ', ord('ı'): 'I',
        ord('ğ'): 'Ğ', ord('ü'): 'Ü',
        ord('ş'): 'Ş', ord('ö'): 'Ö',
        ord('ç'): 'Ç'
    }

    @staticmethod
    def clean_text(text: str) -> str:
        """Türkçe karakter normalizasyonu ile küçük harf"""
        if not text:
            return ""
        return text.translate(IcraUtils.TR_LOWER_MAP).lower()
    
    @staticmethod
    def tr_upper(text: str) -> str:
        """Türkçe karakter normalizasyonu ile büyük harf"""
        if not text:
            return ""
        return text.translate(IcraUtils.TR_UPPER_MAP).upper()

    @staticmethod
    def tutar_parse(text: str) -> float:
        """
        Gelişmiş Tutar Ayrıştırıcı
        
        Desteklenen formatlar:
        - '1.234,56' -> 1234.56 (TR format)
        - '1,234.56' -> 1234.56 (US format)
        - '12.500' -> 12500.0 (TR thousands)
        - '45678' -> 45678.0 (Plain)
        """
        if not text:
            return 0.0
        
        # Sadece rakam ve ayraçları al
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
                # TR format: 1.234,56
                clean = clean.replace('.', '').replace(',', '.')
            else:
                # US format: 1,234.56
                clean = clean.replace(',', '')
        
        # Sadece nokta var
        elif dot_count > 0:
            if dot_count > 1:
                # Birden fazla nokta = binlik ayraç
                clean = clean.replace('.', '')
            elif re.search(r'\.\d{3}$', clean):
                # Son 3 rakam = binlik (12.500)
                clean = clean.replace('.', '')
            # Aksi halde ondalık nokta
        
        # Sadece virgül var
        elif comma_count > 0:
            if comma_count > 1:
                # Birden fazla virgül = binlik ayraç
                clean = clean.replace(',', '')
            elif re.search(r',\d{3}$', clean):
                # Son 3 rakam = binlik
                clean = clean.replace(',', '')
            else:
                # Ondalık virgül
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
                gun = int(match.group(1))
                ay = int(match.group(2))
                yil = int(match.group(3))
                return datetime(yil, ay, gun)
            except ValueError:
                pass
        return None

    @staticmethod
    def tarih_format(tarih: datetime, format: str = "DD.MM.YYYY") -> str:
        """Tarihi formatla"""
        if not tarih:
            return ""
        if format == "DD.MM.YYYY":
            return tarih.strftime("%d.%m.%Y")
        elif format == "YYYY-MM-DD":
            return tarih.strftime("%Y-%m-%d")
        return str(tarih)


# === TEST ===
if __name__ == "__main__":
    print("🧪 IcraUtils v12.5 Test")
    print("=" * 50)
    
    # Tutar testleri
    tutar_tests = [
        ("1.234,56", 1234.56),
        ("12.500", 12500.0),
        ("1,234.56", 1234.56),
        ("45.678,90 TL", 45678.90),
        ("1.000.000,00", 1000000.0),
        ("45678", 45678.0),
        ("100,00", 100.0),
    ]
    
    print("\n📊 Tutar Parse Testleri:")
    for inp, expected in tutar_tests:
        result = IcraUtils.tutar_parse(inp)
        status = "✅" if abs(result - expected) < 0.01 else "❌"
        print(f"  {status} '{inp}' → {result:,.2f} (beklenen: {expected:,.2f})")
    
    # Türkçe lowercase testleri
    print("\n🔤 Türkçe Lowercase Testleri:")
    tr_tests = [
        ("İSTANBUL", "istanbul"),
        ("IRAK", "ırak"),
        ("ŞİŞLİ", "şişli"),
    ]
    for inp, expected in tr_tests:
        result = IcraUtils.clean_text(inp)
        status = "✅" if result == expected else "❌"
        print(f"  {status} '{inp}' → '{result}' (beklenen: '{expected}')")
    
    print("\n✅ Testler tamamlandı")
