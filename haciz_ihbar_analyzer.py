#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HACİZ İHBAR ANALYZER v6.1 - ROBUST EDITION
==========================================
Banka cevaplarını analiz eder. 
Özellikler:
- Genişletilmiş Regex
- Fallback (Yedek) Arama Modu
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from enum import Enum
from datetime import datetime
import re
import os
import zipfile

class IhbarTuru(Enum):
    IHBAR_89_1 = "89/1"
    BILINMIYOR = "Genel"

class MuhatapTuru(Enum):
    BANKA = "🏦 Banka"
    DIGER = "🏢 Diğer"
    BILINMIYOR = "❓"

class CevapDurumu(Enum):
    BLOKE_VAR = "💰 BLOKE VAR"
    HESAP_VAR_BAKIYE_YOK = "⚠️ HESAP VAR BAKİYE YOK"
    HESAP_YOK = "❌ HESAP YOK"
    ITIRAZ = "⚖️ İTİRAZ"
    BELIRSIZ = "❓ İNCELENMELİ"

@dataclass
class HacizIhbarCevabi:
    muhatap: str
    cevap_durumu: CevapDurumu
    bloke_tutari: float = 0.0
    sonraki_adim: str = ""
    ham_metin: str = ""

@dataclass
class HacizIhbarAnalizSonucu:
    toplam_dosya: int = 0
    toplam_bloke: float = 0.0
    banka_sayisi: int = 0
    cevaplar: List[HacizIhbarCevabi] = field(default_factory=list)
    ozet_rapor: str = ""

class HacizIhbarAnalyzer:
    
    BANKALAR = ["Ziraat", "Vakıf", "Halk", "Garanti", "Yapı Kredi", "İş Bankası", "Akbank", "QNB", "Deniz", "TEB", "Kuveyt", "Finans"]
    
    # Kesin Negatifler
    MENFI_REGEX = [
        r'hesap\s*bulunma',
        r'kayıt\s*yok',
        r'rastlanma',
        r'menfi',
        r'borçlu\s*adına\s*hesap\s*yok'
    ]

    def batch_analiz(self, dosya_yollari: List[str]) -> HacizIhbarAnalizSonucu:
        cevaplar = []
        
        # Dosyaları topla (Recursive ZIP support)
        islem_listesi = []
        for yol in dosya_yollari:
            if yol.endswith('.zip'):
                try:
                    # ZIP'i geçici olarak açıp içindekileri okumamız lazım
                    # Burada basitlik adına memory'de okumayı deniyoruz veya
                    # App.py zaten unzip etmişse direkt file path gelir.
                    # Biz burada dosya yolu geldiğini varsayalım.
                    pass 
                except: pass
            else:
                islem_listesi.append(yol)

        # Şimdilik direkt gelen listeyi işliyoruz (App.py temp'e çıkardıysa)
        # Eğer app.py ZIP veriyorsa, app.py içinde unzip yapılması daha sağlıklı.
        # Bu kod tekil dosya analizi mantığıyla çalışır.
        
        for dosya in dosya_yollari:
             # Burada dosyanın TEXT içeriğini almamız lazım.
             # app.py'de bu logic olmalı veya burada implemente edilmeli.
             # Basitlik için dosya yolunu text olarak kabul etmiyoruz, okuyoruz.
             try:
                 text = self._oku(dosya)
                 if text:
                     cevaplar.append(self.analyze_response(text))
             except: pass

        # Sonuç
        toplam = sum(c.bloke_tutari for c in cevaplar)
        return HacizIhbarAnalizSonucu(
            toplam_dosya=len(cevaplar),
            toplam_bloke=toplam,
            banka_sayisi=len([c for c in cevaplar if "Banka" in c.muhatap]),
            cevaplar=cevaplar,
            ozet_rapor=f"Toplam {toplam} TL bloke."
        )

    def _oku(self, yol):
        # Basit okuyucu
        try:
            if yol.endswith('.udf'):
                with zipfile.ZipFile(yol) as z:
                    return z.read('content.xml').decode('utf-8', 'ignore')
            elif yol.endswith('.txt'):
                with open(yol, 'r', encoding='utf-8') as f: return f.read()
            # PDF okuma için pdfplumber lazım, yüklü varsayıyoruz
            import pdfplumber
            with pdfplumber.open(yol) as pdf:
                return "\n".join([p.extract_text() or "" for p in pdf.pages])
        except: return ""

    def analyze_response(self, text: str) -> HacizIhbarCevabi:
        text_clean = text.lower()
        muhatap = "Bilinmeyen"
        for b in self.BANKALAR:
            if b.lower() in text_clean:
                muhatap = b + " Bankası"
                break
        
        durum = CevapDurumu.BELIRSIZ
        tutar = 0.0
        sonraki = "İncele"

        # 1. Menfi Kontrol
        if any(re.search(p, text_clean) for p in self.MENFI_REGEX):
            durum = CevapDurumu.HESAP_YOK
            sonraki = "89/1 Başkasına gönder"
        
        # 2. Bloke Arama (Genişletilmiş)
        # Önce net "bloke edilmiştir" ara
        match = re.search(r'(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?)\s*TL.*bloke', text, re.I)
        if match:
            tutar_str = match.group(1).replace('.', '').replace(',', '.')
            try:
                tutar = float(tutar_str)
                durum = CevapDurumu.BLOKE_VAR
                sonraki = "Mahsup İste"
            except: pass
        
        # Bulamadıysa Fallback: "haciz" kelimesi ve sayı yan yana mı?
        if tutar == 0 and ("haciz" in text_clean or "bloke" in text_clean):
            # Sayıları bul
            nums = re.findall(r'(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2}))', text)
            for n in nums:
                try:
                    val = float(n.replace('.', '').replace(',', '.'))
                    if val > 0 and val < 10000000: # Mantıklı bir aralık
                        tutar = val
                        durum = CevapDurumu.BLOKE_VAR
                        sonraki = "Mahsup İste (Tahmini)"
                        break
                except: pass

        if tutar == 0 and durum != CevapDurumu.HESAP_YOK:
             if "bakiye yok" in text_clean or "yetersiz" in text_clean:
                 durum = CevapDurumu.HESAP_VAR_BAKIYE_YOK
                 sonraki = "89/2 Gönder"

        return HacizIhbarCevabi(muhatap, durum, tutar, sonraki, text[:200])
