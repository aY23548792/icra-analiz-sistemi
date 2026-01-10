#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
UYAP DOSYA ANALYZER v12.3 (Enhanced Classification)
"""
import os
import zipfile
import re
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

                    info = zf.getinfo(name)
                    dosya_tarihi = datetime(*info.date_time)
                    name_lower = name.lower()

                    # 1. Tebligat Analizi
                    if "tebligat" in name_lower or "mazbata" in name_lower or "tebliğ" in name_lower:
                        durum = TebligatDurumu.BILINMIYOR
                        if "bila" in name_lower or "iade" in name_lower:
                            durum = TebligatDurumu.BILA
                        elif "okundu" in name_lower or "tebliğ" in name_lower:
                            durum = TebligatDurumu.TEBLIG_EDILDI

                        t = TebligatBilgisi(name, dosya_tarihi, durum, "Otomatik tespit")
                        sonuc.tebligatlar.append(t)

                    # 2. Haciz Analizi (Talep Hariç)
                    elif ("haciz" in name_lower or "yakalama" in name_lower) and "talep" not in name_lower:
                        mal_turu = MalTuru.TASINIR
                        if "taşınmaz" in name_lower or "tapu" in name_lower:
                            mal_turu = MalTuru.TASINMAZ
                        elif "banka" in name_lower:
                            mal_turu = MalTuru.BANKA
                        elif "maaş" in name_lower:
                            mal_turu = MalTuru.MAAS
                        elif "araç" in name_lower or "plaka" in name_lower:
                            mal_turu = MalTuru.TASINIR # Araçlar taşınır sayılır (özel durum yoksa)

                        analiz = IcraUtils.haciz_sure_hesapla(dosya_tarihi, mal_turu)
                        h = HacizBilgisi(mal_turu.value, dosya_tarihi, 0, "Bilinmiyor", analiz.kalan_gun)
                        sonuc.hacizler.append(h)
                    
                    # 3. Genel Evrak Listesi
                    sonuc.evraklar.append(EvrakBilgisi(name, "Genel", dosya_tarihi))
            
            # Aksiyon Önerileri
            if not sonuc.hacizler:
                sonuc.aksiyonlar.append(AksiyonOnerisi("Haciz Yok", "Malvarlığı sorgusu (Araç/Tapu/Banka/SGK) yapın.", IslemDurumu.UYARI))
            else:
                 sonuc.aksiyonlar.append(AksiyonOnerisi("Haciz Kontrolü", f"{len(sonuc.hacizler)} adet haciz işlemi bulundu. Süreleri kontrol ediniz.", IslemDurumu.BILGI))

            bila_sayisi = len([t for t in sonuc.tebligatlar if t.durum == TebligatDurumu.BILA])
            if bila_sayisi > 0:
                sonuc.aksiyonlar.append(AksiyonOnerisi("Bila Tebligat", f"{bila_sayisi} tebligat iade dönmüş. Mernis veya TK 21 sorgulayın.", IslemDurumu.KRITIK))

            # Özet Rapor Oluşturma
            rapor = [
                "📊 UYAP DOSYA ANALİZ RAPORU",
                f"Tarih: {datetime.now().strftime('%d.%m.%Y')}",
                "-"*30,
                f"Toplam Evrak: {sonuc.toplam_evrak}",
                f"Tebligat İşlemi: {len(sonuc.tebligatlar)}",
                f"Haciz İşlemi: {len(sonuc.hacizler)}",
                "",
                "⚠️ ÖNERİLEN AKSİYONLAR:"
            ]
            for a in sonuc.aksiyonlar:
                rapor.append(f"- [{a.oncelik.name}] {a.baslik}: {a.aciklama}")

            sonuc.ozet_rapor = "\n".join(rapor)
                
        except Exception as e:
            sonuc.ozet_rapor = f"Analiz Hatası: {e}"
            
        return sonuc
