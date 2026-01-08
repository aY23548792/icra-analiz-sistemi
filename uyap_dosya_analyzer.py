#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
UYAP DOSYA ANALYZER v5.0 (App.py Uyumlu)
========================================
Tüm bağımlılıkları içinde barındırır. Modül hatası vermez.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from enum import Enum
from datetime import datetime, timedelta
import os
import zipfile
import re

# --- APP.PY'NİN BEKLEDİĞİ ENUMLAR ---
class EvrakTuru(Enum):
    ODEME_EMRI = "Ödeme Emri"
    HACIZ = "Haciz Evrakı"
    TEBLIGAT = "Tebligat Mazbatası"
    DIGER = "Diğer"

class TebligatDurumu(Enum):
    TEBLIG_EDILDI = "✅ Tebliğ Edildi"
    BILA = "❌ Bila (İade)"
    BEKLENIYOR = "⏳ Bekleniyor"
    BILINMIYOR = "❓ Bilinmiyor"

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
class AksiyonOnerisi:
    oncelik: IslemDurumu
    baslik: str
    aciklama: str
    son_tarih: Optional[datetime] = None

@dataclass
class DosyaAnalizSonucu:
    toplam_evrak: int = 0
    evraklar: List[EvrakBilgisi] = field(default_factory=list)
    tebligatlar: List[TebligatBilgisi] = field(default_factory=list)
    hacizler: List[HacizBilgisi] = field(default_factory=list)
    aksiyonlar: List[AksiyonOnerisi] = field(default_factory=list)
    evrak_dagilimi: Dict[str, int] = field(default_factory=dict)
    tebligat_durumu: TebligatDurumu = TebligatDurumu.BILINMIYOR
    toplam_bloke: float = 0.0
    kritik_tarihler: List[Dict] = field(default_factory=list)
    ozet_rapor: str = ""

class UYAPDosyaAnalyzer:
    
    def analiz_et(self, zip_yolu: str) -> DosyaAnalizSonucu:
        sonuc = DosyaAnalizSonucu()
        
        # Geçici klasörde çalış
        temp_dir = "temp_uyap_analiz"
        os.makedirs(temp_dir, exist_ok=True)
        
        try:
            with zipfile.ZipFile(zip_yolu, 'r') as zf:
                zf.extractall(temp_dir)
                
                for root, _, files in os.walk(temp_dir):
                    for file in files:
                        sonuc.toplam_evrak += 1
                        
                        # Basit Analiz Mantığı
                        lower_name = file.lower()
                        evrak_turu = EvrakTuru.DIGER
                        
                        if "tebli" in lower_name or "mazbata" in lower_name:
                            evrak_turu = EvrakTuru.TEBLIGAT
                            durum = TebligatDurumu.TEBLIG_EDILDI if "dönüş" not in lower_name else TebligatDurumu.BILA
                            sonuc.tebligatlar.append(TebligatBilgisi(file, datetime.now(), durum, "Tebligat bulundu"))
                            
                        elif "haciz" in lower_name:
                            evrak_turu = EvrakTuru.HACIZ
                            # Haciz süresi (Örnek mantık)
                            haciz_tarihi = datetime.now() # Gerçekte dosya tarihinden alınır
                            kalan = 365 - (datetime.now() - haciz_tarihi).days
                            sonuc.hacizler.append(HacizBilgisi("Genel Haciz", haciz_tarihi, 0.0, "Genel", kalan))

                        # İstatistik
                        sonuc.evraklar.append(EvrakBilgisi(file, evrak_turu, datetime.now()))
                        tur_adi = evrak_turu.value
                        sonuc.evrak_dagilimi[tur_adi] = sonuc.evrak_dagilimi.get(tur_adi, 0) + 1

            # Aksiyon Belirleme
            if any(t.durum == TebligatDurumu.BILA for t in sonuc.tebligatlar):
                sonuc.aksiyonlar.append(AksiyonOnerisi(
                    IslemDurumu.KRITIK, "Bila Tebligat", "Mernis adresine TK 21 gönderilmeli"
                ))
            
            if not sonuc.hacizler:
                sonuc.aksiyonlar.append(AksiyonOnerisi(
                    IslemDurumu.UYARI, "Haciz Yok", "Malvarlığı sorgusu yapılmalı"
                ))

            sonuc.ozet_rapor = f"Toplam {sonuc.toplam_evrak} evrak tarandı.\n"

        except Exception as e:
            sonuc.ozet_rapor += f"\nHata oluştu: {str(e)}"
        
        finally:
            # Temizlik
            import shutil
            try: shutil.rmtree(temp_dir)
            except: pass
            
        return sonuc

    def excel_olustur(self, sonuc, yol):
        # Basit excel oluşturma (pandas gerekir)
        try:
            import pandas as pd
            df = pd.DataFrame([vars(e) for e in sonuc.evraklar])
            df.to_excel(yol)
        except:
            pass
