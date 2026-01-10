#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HACİZ İHBAR ANALYZER v11.1 - ROBUST EDITION
===========================================
"""

from dataclasses import dataclass, field
from typing import List
from enum import Enum
import re
import os
import zipfile
import sys

# pdfplumber importunu güvenli yap
try:
    import pdfplumber
    PDFPLUMBER_OK = True
except ImportError:
    PDFPLUMBER_OK = False

# IcraUtils'i güvenli import et
try:
    from icra_analiz_v2 import IcraUtils
except ImportError:
    # Fallback Utils
    class IcraUtils:
        @staticmethod
        def clean_text(t): return t.lower() if t else ""
        @staticmethod
        def tutar_parse(t):
            if not t: return 0.0
            clean = re.sub(r'[^\d.,]', '', str(t))
            clean = clean.replace('.', '').replace(',', '.')
            try: return float(clean)
            except: return 0.0

class CevapDurumu(Enum):
    BLOKE_VAR = "💰 BLOKE VAR"
    MENFI = "❌ MENFİ (YOK)"
    HESAP_VAR_BAKIYE_YOK = "⚠️ HESAP VAR BAKİYE YOK"
    ITIRAZ = "⚖️ İTİRAZ"
    BELIRSIZ = "❓ İNCELENMELİ"
    KEP = "📧 KEP İLETİSİ"
    HESAP_YOK = "❌ HESAP YOK" # Alias for MENFI

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
    banka_sayisi: int = 0  # Explicit field added

    @property
    def ozet_rapor(self):
        lines = [f"Toplam Dosya: {self.toplam_dosya}", f"Toplam Bloke: {self.toplam_bloke:,.2f} TL", "-"*20]
        for c in self.cevaplar:
            val = c.durum.value if hasattr(c.durum, 'value') else str(c.durum)
            lines.append(f"{c.muhatap}: {val} - {c.tutar:,.2f} TL ({c.sonraki_adim})")
        return "\n".join(lines)

class HacizIhbarAnalyzer:
    
    BANKALAR = ["Ziraat", "Vakıf", "Halk", "Garanti", "Yapı Kredi", "İş Bankası", "Akbank", "QNB", "Deniz", "TEB", "Kuveyt", "Finans"]
    
    MENFI_REGEX = [
        r'hesap\s*bulunma', r'kayıt\s*yok', r'rastlanma', r'menfi',
        r'borçlu\s*adına\s*hesap\s*yok', r'herhangi\s*bir\s*hak\s*ve\s*alacak\s*yok'
    ]
    
    BAKIYE_YOK_REGEX = [
        r'bakiye\s*yok', r'bakiye\s*bulunma', r'yetersiz',
        r'blokeli\s*tutar\s*:\s*0', r'bakiye\s*:\s*0[,.]00'
    ]

    def batch_analiz(self, dosya_yollari: List[str]) -> HacizIhbarAnalizSonucu:
        cevaplar = []
        # Dosyaları düzleştir
        flat_files = []
        for p in dosya_yollari:
            if os.path.isdir(p):
                for r, _, fs in os.walk(p):
                    for f in fs: flat_files.append(os.path.join(r, f))
            else:
                flat_files.append(p)

        for yol in flat_files:
            try:
                metin = self._dosya_oku(yol)
                if metin:
                    cevaplar.append(self.analyze_response(metin))
            except Exception as e:
                print(f"Hata {yol}: {e}", file=sys.stderr)

        toplam = sum(c.tutar for c in cevaplar if c.durum == CevapDurumu.BLOKE_VAR)
        banka_count = len(set(c.muhatap for c in cevaplar if "Banka" in c.muhatap))

        return HacizIhbarAnalizSonucu(len(cevaplar), toplam, cevaplar, banka_count)

    def analyze_response(self, text: str) -> HacizIhbarCevabi:
        clean = IcraUtils.clean_text(text)
        muhatap = "Bilinmeyen"
        for b in self.BANKALAR:
            if IcraUtils.clean_text(b) in clean:
                muhatap = b + " Bankası"
                break
        
        durum = CevapDurumu.BELIRSIZ
        tutar = 0.0
        sonraki = "İncele"

        if "kep iletisi" in clean and len(text) < 500:
            return HacizIhbarCevabi(muhatap, CevapDurumu.KEP, 0.0, "Bekle", text[:100])

        if any(re.search(p, clean) for p in self.MENFI_REGEX):
            return HacizIhbarCevabi(muhatap, CevapDurumu.MENFI, 0.0, "89/1 Başkasına", text[:100])

        # Bloke Arama
        bloke_bulundu = False
        # Pattern A: "33.534,33 TL ... bloke"
        match_a = re.search(r'(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?)\s*TL.*?bloke', text, re.I | re.DOTALL)
        if match_a:
            tutar = IcraUtils.tutar_parse(match_a.group(1))
            bloke_bulundu = True

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
             durum = CevapDurumu.BLOKE_VAR # Şüpheli ama pozitif sayalım
             sonraki = "Manuel Kontrol (Tutar Okunamadı)"
        
        return HacizIhbarCevabi(muhatap, durum, tutar, sonraki, text[:200])

    def _dosya_oku(self, yol):
        try:
            if yol.endswith('.udf'):
                with zipfile.ZipFile(yol) as z:
                    # XML bul
                    xmls = [n for n in z.namelist() if n.endswith('.xml')]
                    target = 'content.xml' if 'content.xml' in xmls else (xmls[0] if xmls else None)
                    if target:
                        raw = z.read(target).decode('utf-8', 'ignore')
                        return re.sub(r'<[^>]+>', ' ', raw)
            if yol.endswith('.pdf') and PDFPLUMBER_OK:
                with pdfplumber.open(yol) as pdf:
                    return "\n".join([p.extract_text() or "" for p in pdf.pages])
            if os.path.isfile(yol):
                 with open(yol, 'r', encoding='utf-8', errors='ignore') as f:
                    return f.read()
            return ""
        except: return ""
