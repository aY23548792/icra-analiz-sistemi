#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
UYAP DOSYA ANALYZER v11.0
=========================
"""
import os
import zipfile
from icra_analiz_v2 import (
    DosyaAnalizSonucu, EvrakBilgisi, TebligatBilgisi, HacizBilgisi,
    AksiyonOnerisi, TebligatDurumu, IslemDurumu, MalTuru, IcraUtils
)
from datetime import datetime

class UYAPDosyaAnalyzer:
    def analiz_et(self, zip_yolu: str) -> DosyaAnalizSonucu:
        sonuc = DosyaAnalizSonucu()
        try:
            with zipfile.ZipFile(zip_yolu, 'r') as zf:
                for name in zf.namelist():
                    sonuc.toplam_evrak += 1
                    # Basit sınıflandırma
                    if "tebligat" in name.lower():
                        t = TebligatBilgisi(name, datetime.now(), TebligatDurumu.BILINMIYOR, "")
                        sonuc.tebligatlar.append(t)
                    elif "haciz" in name.lower():
                        # Süre hesabı
                        analiz = IcraUtils.haciz_sure_hesapla(datetime(2023,1,1), MalTuru.TASINMAZ)
                        h = HacizBilgisi("Taşınmaz", datetime(2023,1,1), 0, "Tapu", analiz.kalan_gun)
                        sonuc.hacizler.append(h)
                    
                    sonuc.evraklar.append(EvrakBilgisi(name, "Genel", datetime.now()))
            
            if not sonuc.hacizler:
                sonuc.aksiyonlar.append(AksiyonOnerisi("Haciz Yok", "Malvarlığı sorgusu yapın", IslemDurumu.UYARI))
                
        except Exception as e:
            sonuc.ozet_rapor = f"Hata: {e}"
            
        return sonuc

    def excel_olustur(self, sonuc, yol):
        # Pandas ile excel (basit)
        import pandas as pd
        df = pd.DataFrame([vars(e) for e in sonuc.evraklar])
        df.to_excel(yol)
