#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
UYAP DOSYA ANALYZER v5.1 (Safety Fix)
=====================================
Oracle zekasını korur, CORE yüklenemezse çökmez.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from enum import Enum
from datetime import datetime, timedelta
import os
import zipfile
import re
import tempfile
import shutil

# --- APP.PY'NİN BEKLEDİĞİ ENUMLAR ---
class EvrakTuru(Enum):
    ODEME_EMRI = "Ödeme Emri"
    HACIZ = "Haciz Evrakı"
    TEBLIGAT = "Tebligat Mazbatası"
    SORGULAMA = "Sorgulama Sonucu"
    TALIMAT = "Talimat Evrakı"
    DIGER = "Diğer"

class IslemDurumu(Enum):
    KRITIK = "🔴 KRİTİK"
    UYARI = "⚠️ UYARI"
    BILGI = "ℹ️ BİLGİ"
    TAMAMLANDI = "✅ TAMAMLANDI"

@dataclass
class EvrakBilgisi:
    dosya_adi: str
    evrak_turu: EvrakTuru
    tarih: Optional[datetime]
    ozet: str = ""

@dataclass
class AksiyonOnerisi:
    oncelik: IslemDurumu
    baslik: str
    aciklama: str
    son_tarih: Optional[datetime] = None

@dataclass
class DosyaAnalizSonucu:
    toplam_evrak: int = 0
    tebligatlar: List[Any] = field(default_factory=list)
    hacizler: List[Any] = field(default_factory=list)
    aksiyonlar: List[AksiyonOnerisi] = field(default_factory=list)
    evrak_dagilimi: Dict[str, int] = field(default_factory=dict)
    ozet_rapor: str = ""

# Shared Core Import with Safe Fallback
try:
    from icra_analiz_v2 import IcraUtils, MalTuru, RiskSeviyesi
    CORE_OK = True
except Exception:
    CORE_OK = False
    IcraUtils = None
    MalTuru = None
    RiskSeviyesi = None

class UYAPDosyaAnalyzer:
    
    def __init__(self):
        self.doc_patterns = {
            EvrakTuru.ODEME_EMRI: [r"ödeme emri", r"örnek 7", r"örnek 10"],
            EvrakTuru.TEBLIGAT: [r"tebligat mazbatası", r"tebliğ edildi"],
            EvrakTuru.HACIZ: [r"haciz tutanağı", r"haciz zaptı", r"89/1", r"89/2"],
            EvrakTuru.SORGULAMA: [r"sgk sorgu", r"araç sorgu", r"takbis"],
            EvrakTuru.TALIMAT: [r"talimat"],
        }

    def analiz_et(self, zip_yolu: str) -> DosyaAnalizSonucu:
        sonuc = DosyaAnalizSonucu()
        tmp_dir = tempfile.mkdtemp()
        
        try:
            if zipfile.is_zipfile(zip_yolu):
                with zipfile.ZipFile(zip_yolu, 'r') as zf:
                    zf.extractall(tmp_dir)
            
            for root, _, files in os.walk(tmp_dir):
                for file in files:
                    full_path = os.path.join(root, file)
                    text = IcraUtils.read_file_content(full_path) if CORE_OK else ""
                    if not text.strip(): continue
                    
                    sonuc.toplam_evrak += 1
                    turu = self._classify(text, file)
                    sonuc.evrak_dagilimi[turu.value] = sonuc.evrak_dagilimi.get(turu.value, 0) + 1
                    
                    # Oracle Logic Restoration (with CORE_OK check)
                    if turu == EvrakTuru.HACIZ and CORE_OK and MalTuru and RiskSeviyesi:
                        date = IcraUtils.tarih_parse(text)
                        if date:
                            mal = MalTuru.TASINMAZ if "taşınmaz" in text.lower() else MalTuru.TASINIR
                            h_res = IcraUtils.haciz_sure_hesapla(date, mal)
                            if h_res.risk_seviyesi in [RiskSeviyesi.DUSMUS, RiskSeviyesi.KRITIK]:
                                sonuc.aksiyonlar.append(AksiyonOnerisi(
                                    oncelik=IslemDurumu.KRITIK,
                                    baslik=f"HACİZ DÜŞME RİSKİ",
                                    aciklama=f"{file}: {h_res.durum} - {h_res.onerilen_aksiyon}"
                                ))
                    
                    if turu == EvrakTuru.TALIMAT:
                        if any(x in text.lower() for x in ["masraf", "harç"]):
                            sonuc.aksiyonlar.append(AksiyonOnerisi(
                                oncelik=IslemDurumu.UYARI,
                                    baslik="GİZLİ MASRAF (TALİMAT)",
                                    aciklama=f"{file} dosyasında masraf bulundu. Kapak hesabını kontrol edin."
                            ))
            
            if not sonuc.aksiyonlar:
                sonuc.ozet_rapor = "Analiz tamamlandı. Kritik bir risk tespit edilmedi."
            else:
                sonuc.ozet_rapor = f"Analiz tamamlandı. {len(sonuc.aksiyonlar)} adet aksiyon önerisi bulundu."

        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            
        return sonuc

    def _classify(self, text, filename):
        text_long = (text + " " + filename).lower()
        for tur, patterns in self.doc_patterns.items():
            if any(re.search(p, text_long) for p in patterns):
                return tur
        return EvrakTuru.DIGER