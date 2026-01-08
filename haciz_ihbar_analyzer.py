#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HACİZ İHBAR ANALYZER v11.0 (Oracle Edition)
==========================================
Analyzes bank responses (89/1-2-3) using Context-Aware Regex.
Implements "Negative-First" logic: Checks for negative conditions 
(e.g., "no account") BEFORE searching for amounts to prevent false positives.
"""

from typing import List, Optional, Tuple, Dict
from dataclasses import dataclass
from enum import Enum
import re
import os

# Import from Shared Core
from icra_analiz_v2 import IcraUtils

class MuhatapTuru(Enum):
    BANKA = "🏦 Banka"
    TUZEL_KISI = "🏢 Şirket"
    GERCEK_KISI = "👤 Kişi"
    KAMU = "🏛️ Kamu"
    BILINMIYOR = "❓ Bilinmiyor"

class CevapDurumu(Enum):
    BLOKE_VAR = "💰 BLOKE VAR"
    MENFI = "❌ MENFİ (YOK)"
    HESAP_VAR_BAKIYE_YOK = "⚠️ HESAP VAR BAKİYE YOK"
    ITIRAZ = "⚖️ İTİRAZ / İSTİHKAK"
    KEP_ILETISI = "📧 KEP BİLDİRİMİ"
    BELIRSIZ = "❓ İNCELENMELİ"

@dataclass
class BankaCevabi:
    dosya_adi: str
    muhatap: str
    muhatap_turu: MuhatapTuru
    durum: CevapDurumu
    tutar: float
    iban: Optional[str]
    ham_metin: str
    sonraki_adim: str
    dosya_no: Optional[str]

class HacizIhbarAnalyzer:
    """Core logic for parsing bank responses to 89/1-2-3 notifications."""
    
    # 1. Negative Patterns (PRIORITY!)
    MENFI_PATTERNS = [
        re.compile(r'hesap\s*(?:kaydı|bilgisi)?\s*(?:bulunma|yok|mevcut\s*değil)', re.I),
        re.compile(r'borçlu\s*adına\s*kayıt\s*yok', re.I),
        re.compile(r'herhangi\s*bir\s*hak\s*ve\s*alacağa\s*rastlanma', re.I),
        re.compile(r'menfi\s*cevap', re.I),
        re.compile(r'müşteri\s*kaydı?\s*bulunmamakta', re.I)
    ]
    
    # 2. "Balance Empty" Patterns
    BAKIYE_YOK_PATTERNS = [
        re.compile(r'bakiye\s*(?:bulunma|yok|yetersiz)', re.I),
        re.compile(r'bakiye\s*:\s*0[,.]00', re.I),
        re.compile(r'blokeli\s*tutar\s*:\s*0', re.I),
        re.compile(r'kullanılabilir\s*bakiye\s*yok', re.I)
    ]

    # 3. Positive Patterns (Context Aware)
    # Looks for 'bloke'/'haciz' followed closely by a number (up to 50 chars)
    BLOKE_CONTEXT = re.compile(
        r'(?:bloke|haciz|tedbir)(?:.{0,50}?)(?:tutar|bedel|miktar|bakiye)?.{0,20}?'
        r'(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?)', 
        re.IGNORECASE | re.DOTALL
    )

    def analyze_response(self, text: str, filename: str) -> BankaCevabi:
        """
        Oracle-Grade Analysis: Checks Negative constraints BEFORE finding numbers.
        """
        text_clean = IcraUtils.clean_text(text)
        muhatap_adi = IcraUtils.banka_tespit(text) or "Bilinmeyen Üçüncü Şahıs"
        dosya_no = IcraUtils.dosya_no_parse(text)
        
        # Determine Actor Type
        if "bank" in text_clean or muhatap_adi != "Bilinmeyen Üçüncü Şahıs":
            muhatap_turu = MuhatapTuru.BANKA
        elif any(x in text_clean for x in ["ltd", "a.ş.", "şti"]):
            muhatap_turu = MuhatapTuru.TUZEL_KISI
        else:
            muhatap_turu = MuhatapTuru.BILINMIYOR

        durum = CevapDurumu.BELIRSIZ
        tutar = 0.0
        sonraki = "Metni Manuel Kontrol Edin"
        iban = None

        # IBAN Extraction
        iban_match = re.search(r'TR\d{2}\s?(\d{4}\s?){5}\d{2}', text)
        if iban_match:
            iban = iban_match.group(0).replace(" ", "")

        # --- LOGIC GATEWAY (Negative-First) ---
        
        # A. KEP / Pure Notification Check
        if "kep iletisi" in text_clean and len(text) < 400:
            durum = CevapDurumu.KEP_ILETISI
            sonraki = "Bu bir tebligat onayıdır, asıl cevabı bekleyin."
            
        # B. Negative Check (Highest Priority)
        elif any(p.search(text) for p in self.MENFI_PATTERNS):
            durum = CevapDurumu.MENFI
            sonraki = "7 gün bekleyip 89/2 gönderin."
            
        # C. Balance Empty Check
        elif any(p.search(text) for p in self.BAKIYE_YOK_PATTERNS):
            durum = CevapDurumu.HESAP_VAR_BAKIYE_YOK
            sonraki = "7 gün bekleyip 89/2 gönderin (Hesap var ama boş)."
            
        # D. Positive Match
        else:
            match = self.BLOKE_CONTEXT.search(text)
            if match:
                raw_amount = match.group(1)
                tutar = IcraUtils.tutar_parse(raw_amount)
                if tutar > 2.0: # Filter out trace amounts / noise
                    durum = CevapDurumu.BLOKE_VAR
                    sonraki = "MAHSUP TALEBİ GÖNDER! (Tahsilat Potansiyeli)"
                else:
                    durum = CevapDurumu.HESAP_VAR_BAKIYE_YOK
                    sonraki = "Tutar 0 veya çok düşük, 89/2 ile devam."
            elif any(x in text_clean for x in ["bloke konulmuştur", "haciz uygulanmıştır"]):
                # Keyword found but regex failed amount
                durum = CevapDurumu.BLOKE_VAR
                sonraki = "Bloke var denilmiş ama tutar okunamadı (Manuel Kontrol)."
            elif "itiraz" in text_clean or "istihkak" in text_clean:
                durum = CevapDurumu.ITIRAZ
                sonraki = "İtiraz/İstihkak iddiasını değerlendirin."

        return BankaCevabi(
            dosya_adi=filename,
            muhatap=muhatap_adi,
            muhatap_turu=muhatap_turu,
            durum=durum,
            tutar=tutar,
            iban=iban,
            ham_metin=text[:500],
            sonraki_adim=sonraki,
            dosya_no=dosya_no
        )

    def batch_process(self, file_paths: List[str]) -> Dict:
        """Processes multiple files and returns summary statistics."""
        results = []
        total_bloke = 0.0
        
        for fp in file_paths:
            try:
                text = IcraUtils.read_file_content(fp)
                if not text.strip():
                    continue
                
                res = self.analyze_response(text, os.path.basename(fp))
                results.append(res)
                if res.durum == CevapDurumu.BLOKE_VAR:
                    total_bloke += res.tutar
            except Exception as e:
                print(f"Hata: {fp} işlenemedi -> {e}")

        return {
            "results": results,
            "total_bloke": total_bloke,
            "count": len(results),
            "bloke_count": len([r for r in results if r.durum == CevapDurumu.BLOKE_VAR])
        }
