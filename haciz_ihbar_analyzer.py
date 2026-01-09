#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HACİZ İHBAR ANALYZER v11.0 - ROBUST EDITION
===========================================
Banka cevaplarını analiz eder. "Ghost Bloke" ve "Missed Bloke" sorunlarını çözer.
Strateji: Geniş Arama -> Negatif Eleme -> Skorlama
"""

from dataclasses import dataclass, field
from typing import List, Tuple
from enum import Enum
from datetime import datetime
import re
import os
import zipfile
try:
    from icra_analiz_v2 import IcraUtils
except ImportError:
    class IcraUtils: # Fallback
        @staticmethod
        def clean_text(t): return t.lower()
        @staticmethod
        def tutar_parse(t): return 0.0

class MuhatapTuru(Enum):
    BANKA = "🏦 Banka"
    TUZEL = "🏢 Şirket"
    DIGER = "❓ Diğer"

class CevapDurumu(Enum):
    BLOKE_VAR = "💰 BLOKE VAR"
    MENFI = "❌ MENFİ (YOK)"
    HESAP_VAR_BAKIYE_YOK = "⚠️ HESAP VAR BAKİYE YOK"
    ITIRAZ = "⚖️ İTİRAZ"
    BELIRSIZ = "❓ İNCELENMELİ"
    KEP = "📧 KEP İLETİSİ"

@dataclass
class HacizIhbarCevabi:
    muhatap: str
    durum: CevapDurumu
    tutar: float
    sonraki_adim: str
    ham_metin: str

@dataclass
class HacizIhbarAnalizSonucu:
    toplam_dosya: int = 0
    toplam_bloke: float = 0.0
    cevaplar: List[HacizIhbarCevabi] = field(default_factory=list)

class HacizIhbarAnalyzer:
    
    BANKALAR = ["Ziraat", "Vakıf", "Halk", "Garanti", "Yapı Kredi", "İş Bankası", "Akbank", "QNB", "Deniz", "TEB", "Kuveyt", "Finans"]
    
    # Kesin Negatif İfadeler
    MENFI_REGEX = [
        r'hesap\s*bulunma',
        r'kayıt\s*yok',
        r'rastlanma',
        r'menfi',
        r'borçlu\s*adına\s*hesap\s*yok',
        r'herhangi\s*bir\s*hak\s*ve\s*alacak\s*yok'
    ]
    
    # Bakiye Yok İfadeleri
    BAKIYE_YOK_REGEX = [
        r'bakiye\s*yok',
        r'bakiye\s*bulunma',
        r'yetersiz',
        r'blokeli\s*tutar\s*:\s*0',
        r'bakiye\s*:\s*0[,.]00'
    ]

    def batch_analiz(self, dosya_yollari: List[str]) -> HacizIhbarAnalizSonucu:
        cevaplar = []
        for yol in dosya_yollari:
            try:
                metin = self._dosya_oku(yol)
                if metin:
                    cevaplar.append(self.analyze_response(metin))
            except Exception as e:
                print(f"Hata {yol}: {e}")

        toplam = sum(c.tutar for c in cevaplar if c.durum == CevapDurumu.BLOKE_VAR)
        return HacizIhbarAnalizSonucu(len(cevaplar), toplam, cevaplar)

    def analyze_response(self, text: str) -> HacizIhbarCevabi:
        clean = IcraUtils.clean_text(text)
        
        # 1. Muhatap Belirle
        muhatap = "Bilinmeyen"
        for b in self.BANKALAR:
            if IcraUtils.clean_text(b) in clean:
                muhatap = b
                break
        
        durum = CevapDurumu.BELIRSIZ
        tutar = 0.0
        sonraki = "İncele"

        # 2. KEP Kontrolü
        if "kep iletisi" in clean and len(text) < 500:
            return HacizIhbarCevabi(muhatap, CevapDurumu.KEP, 0.0, "Bekle", text[:100])

        # 3. Negatif Kontrol (Öncelikli)
        if any(re.search(p, clean) for p in self.MENFI_REGEX):
            return HacizIhbarCevabi(muhatap, CevapDurumu.MENFI, 0.0, "89/1 Başkasına", text[:100])

        # 4. Bloke Arama (Genişletilmiş ve Güçlü Regex)
        # Önce net "bloke: 123 TL" kalıplarını arıyoruz
        # Regex: (Tutar) ... (Bloke) veya (Bloke) ... (Tutar)
        
        bloke_bulundu = False
        
        # Pattern A: "33.534,33 TL ... bloke"
        match_a = re.search(r'(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?)\s*TL.*?bloke', text, re.I | re.DOTALL)
        if match_a:
            tutar = IcraUtils.tutar_parse(match_a.group(1))
            bloke_bulundu = True

        # Pattern B: "bloke ... 33.534,33 TL"
        if not bloke_bulundu:
            match_b = re.search(r'bloke.*?(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?)\s*TL', text, re.I | re.DOTALL)
            if match_b:
                tutar = IcraUtils.tutar_parse(match_b.group(1))
                bloke_bulundu = True
        
        if bloke_bulundu and tutar > 0:
            durum = CevapDurumu.BLOKE_VAR
            sonraki = "Mahsup İste"
        elif any(re.search(p, clean) for p in self.BAKIYE_YOK_REGEX):
             durum = CevapDurumu.HESAP_VAR_BAKIYE_YOK
             sonraki = "89/2 Gönder"
        elif "haciz" in clean or "bloke" in clean:
             # Kelime var ama tutar okunamadı
             durum = CevapDurumu.BLOKE_VAR
             sonraki = "Manuel Kontrol (Tutar Okunamadı)"
        
        return HacizIhbarCevabi(muhatap, durum, tutar, sonraki, text[:200])

    def _dosya_oku(self, yol):
        try:
            # UDF ise XML parse et
            if yol.endswith('.udf'):
                with zipfile.ZipFile(yol) as z:
                    if 'content.xml' in z.namelist():
                        raw = z.read('content.xml').decode('utf-8', 'ignore')
                        # Basit XML temizliği
                        return re.sub(r'<[^>]+>', ' ', raw)
            
            # PDF ise pdfplumber (Import try/except içinde olmalı)
            if yol.endswith('.pdf'):
                import pdfplumber
                with pdfplumber.open(yol) as pdf:
                    return "\n".join([p.extract_text() or "" for p in pdf.pages])
            
            # Text/XML
            with open(yol, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read()
        except: return ""
