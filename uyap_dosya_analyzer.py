#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
UYAP DOSYA ANALYZER v11.1
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

                    # Dosya tarihini almaya çalış (modifiyed date)
                    info = zf.getinfo(name)
                    dosya_tarihi = datetime(*info.date_time)

                    # Basit sınıflandırma
                    name_lower = name.lower()
                    if "tebligat" in name_lower:
                        t = TebligatBilgisi(name, dosya_tarihi, TebligatDurumu.BILINMIYOR, "")
                        sonuc.tebligatlar.append(t)
                    elif "haciz" in name_lower and "talep" not in name_lower: # Talep değilse, haciz işlemidir varsayımı
                        # Süre hesabı - Dosya tarihini baz alıyoruz
                        # Mal türü tahmini (basit)
                        mal_turu = MalTuru.TASINIR # Varsayılan
                        if "taşınmaz" in name_lower or "tapu" in name_lower:
                            mal_turu = MalTuru.TASINMAZ
                        elif "banka" in name_lower:
                            mal_turu = MalTuru.BANKA
                        elif "maaş" in name_lower:
                            mal_turu = MalTuru.MAAS

                        analiz = IcraUtils.haciz_sure_hesapla(dosya_tarihi, mal_turu)
                        h = HacizBilgisi(mal_turu.value, dosya_tarihi, 0, "Bilinmiyor", analiz.kalan_gun)
                        sonuc.hacizler.append(h)
                    
                    sonuc.evraklar.append(EvrakBilgisi(name, "Genel", dosya_tarihi))
            
            if not sonuc.hacizler:
                sonuc.aksiyonlar.append(AksiyonOnerisi("Haciz Yok", "Malvarlığı sorgusu yapın", IslemDurumu.UYARI))
            else:
                 sonuc.aksiyonlar.append(AksiyonOnerisi("Haciz Kontrolü", f"{len(sonuc.hacizler)} adet haciz bulundu. Süreleri kontrol edin.", IslemDurumu.BILGI))
                
        except Exception as e:
            sonuc.ozet_rapor = f"Hata: {e}"
            
        return sonuc

    def excel_olustur(self, sonuc, yol):
        # Pandas ile excel (basit)
        import pandas as pd
        df = pd.DataFrame([vars(e) for e in sonuc.evraklar])
        df.to_excel(yol)
