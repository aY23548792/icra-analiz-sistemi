#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
UYAP DOSYA ANALYZER v11.0 (Oracle Edition)
==========================================
Analyzes UYAP ZIP archives focusing on:
- Seizure Deadlines (İİK 106/110)
- Talimat (Instruction) file detection & expense risk analysis
- Document classification (Ödeme Emri, Takip Talebi, etc.)
"""

import os
import re
import zipfile
import tempfile
import shutil
from typing import List, Dict, Optional
from dataclasses import dataclass

# Import Shared Core
from icra_analiz_v2 import IcraUtils, MalTuru, RiskSeviyesi

@dataclass
class UygulananHaciz:
    tarih: str
    mal_turu: str
    durum: str
    kalan_gun: int
    risk: str
    aksiyon: str
    dayanak: str

class UyapDosyaAnalyzer:
    """Parses UYAP ZIPs to extract legal timelines and fiscal risks."""

    DOC_TYPES = {
        "TAKIP_TALEBI": [r"takip talebi"],
        "ODEME_EMRI": [r"ödeme emri", r"örnek 7", r"örnek 10"],
        "TEBLIGAT": [r"tebligat mazbatası", r"tebliğ edildi"],
        "HACIZ_ZABTI": [r"haciz tutanağı", r"haciz zaptı"],
        "TALIMAT": [r"talimat yazısı", r"talimat tensip", r"talimat müzekkeresi"],
        "KIYMET_TAKDIRI": [r"kıymet takdiri", r"bilirkişi raporu"],
        "SATIS_ILANI": [r"satış ilanı", r"artırma ilanı"]
    }

    def _classify(self, text: str, filename: str) -> str:
        text_lower = IcraUtils.clean_text(text + " " + filename)
        for dtype, patterns in self.DOC_TYPES.items():
            if any(re.search(p, text_lower) for p in patterns):
                return dtype
        return "DIGER"

    def analyze_zip(self, zip_path: str) -> Dict:
        """Processes a UYAP ZIP and returns a structured summary."""
        temp_dir = tempfile.mkdtemp()
        summary = {
            "dosya_sayisi": 0,
            "evraklar": [],
            "hacizler": [],
            "talimat_uyarilari": [],
            "kritik_notlar": []
        }

        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                # Filter out system files like __MACOSX
                valid_files = [f for f in zf.namelist() if not f.startswith('__') and not f.endswith('/')]
                summary["dosya_sayisi"] = len(valid_files)
                zf.extractall(temp_dir)
                
                for file in valid_files:
                    full_path = os.path.join(temp_dir, file)
                    text = IcraUtils.read_file_content(full_path)
                    if not text.strip():
                        continue
                    
                    doc_date = IcraUtils.tarih_parse(text)
                    doc_type = self._classify(text, file)
                    text_lower = IcraUtils.clean_text(text)

                    # 1. Document Entry
                    summary["evraklar"].append({
                        "id": file,
                        "tur": doc_type,
                        "tarih": doc_date.strftime("%d.%m.%Y") if doc_date else "Bilinmiyor"
                    })

                    # 2. TALIMAT DEDEKTÖRÜ (Kozan Logic)
                    if doc_type == "TALIMAT" or "talimat" in text_lower:
                        # Check for keywords suggesting hidden expenses
                        if any(x in text_lower for x in ["masraf", "harç", "makbuz", "tahsilat"]):
                            summary["talimat_uyarilari"].append({
                                "dosya": file,
                                "mesaj": "⚠️ Talimat Dosyasında Masraf Tespiti: UYAP kapak hesabına eklenmemiş olabilir! (İİK m.59 hatırlatması)"
                            })

                    # 3. HACİZ SÜRE ANALİZİ
                    if doc_type == "HACIZ_ZABTI" and doc_date:
                        # Detect asset type from text
                        mal = MalTuru.TASINIR
                        if any(x in text_lower for x in ["taşınmaz", "tapu", "ada", "parsel"]):
                            mal = MalTuru.TASINMAZ
                        elif any(x in text_lower for x in ["plaka", "araç", "şasi"]):
                            mal = MalTuru.TASINIR # Still movable
                        
                        # Use Centralized Deadline Engine
                        analiz = IcraUtils.haciz_sure_hesapla(doc_date, mal)
                        
                        summary["hacizler"].append(UygulananHaciz(
                            tarih=doc_date.strftime("%d.%m.%Y"),
                            mal_turu=mal.value,
                            durum=analiz.durum,
                            kalan_gun=analiz.kalan_gun,
                            risk=analiz.risk_seviyesi.value,
                            aksiyon=analiz.onerilen_aksiyon,
                            dayanak=analiz.yasal_dayanak
                        ))

        except Exception as e:
            summary["kritik_notlar"].append(f"Hata: ZIP işlenemedi -> {str(e)}")
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
        
        return summary
