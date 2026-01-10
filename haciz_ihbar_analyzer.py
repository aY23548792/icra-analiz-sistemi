#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HACİZ İHBAR ANALYZER v12.4 (Optimized)
======================================
"""

from dataclasses import dataclass, field
from typing import List
from enum import Enum
import re
import os
import zipfile
import sys
import concurrent.futures

try:
    import pdfplumber
    PDFPLUMBER_OK = True
except ImportError:
    PDFPLUMBER_OK = False

try:
    from icra_analiz_v2 import IcraUtils
except ImportError:
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
    HESAP_YOK = "❌ HESAP YOK"

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
    banka_sayisi: int = 0

    @property
    def ozet_rapor(self):
        lines = [f"Toplam Dosya: {self.toplam_dosya}", f"Toplam Bloke: {self.toplam_bloke:,.2f} TL", "-"*20]
        for c in self.cevaplar:
            val = c.durum.value if hasattr(c.durum, 'value') else str(c.durum)
            lines.append(f"{c.muhatap}: {val} - {c.tutar:,.2f} TL ({c.sonraki_adim})")
        return "\n".join(lines)

class HacizIhbarAnalyzer:
    
    BANKALAR = [
        "Ziraat", "Vakıf", "Halk", "Garanti", "Yapı Kredi", "İş Bankası",
        "Akbank", "QNB", "Finans", "Deniz", "TEB", "Kuveyt", "Albaraka",
        "Türkiye Finans", "Odeabank", "Şekerbank", "ING", "HSBC"
    ]
    
    # Pre-compiled Regex for Performance
    MENFI_REGEX = [re.compile(p, re.I) for p in [
        r'hesap\s*bulunma', r'kayıt\s*yok', r'rastlanma', r'menfi',
        r'borçlu\s*adına\s*hesap\s*yok', r'herhangi\s*bir\s*hak\s*ve\s*alacak\s*yok',
        r'mevcut\s*değil', r'hesap\s*tespit\s*edileme', r'müşteri\s*kaydı\s*yok'
    ]]

    BAKIYE_YOK_REGEX = [re.compile(p, re.I) for p in [
        r'bakiye\s*yok', r'bakiye\s*bulunma', r'yetersiz',
        r'blokeli\s*tutar\s*:\s*0', r'bakiye\s*:\s*0[,.]00',
        r'haczedilecek\s*bakiye\s*yok', r'bakiye\s*sıfır'
    ]]

    BLOKE_REGEX = [re.compile(p, re.I | re.DOTALL) for p in [
        r'(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?)\s*TL.*?bloke',
        r'bloke.*?(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?)\s*TL',
        r'üzerine.*?(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?)\s*TL.*?haciz'
    ]]

    def batch_analiz(self, dosya_yollari: List[str]) -> HacizIhbarAnalizSonucu:
        flat_files = []
        for p in dosya_yollari:
            if os.path.isdir(p):
                for r, _, fs in os.walk(p):
                    for f in fs: flat_files.append(os.path.join(r, f))
            else:
                flat_files.append(p)

        cevaplar = []
        # Parallel Processing
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future_to_file = {executor.submit(self._process_single_file, f): f for f in flat_files}
            for future in concurrent.futures.as_completed(future_to_file):
                res = future.result()
                if res:
                    cevaplar.append(res)

        toplam = sum(c.tutar for c in cevaplar if c.durum == CevapDurumu.BLOKE_VAR)
        banka_count = len(set(c.muhatap for c in cevaplar if "Banka" in c.muhatap))

        return HacizIhbarAnalizSonucu(len(cevaplar), toplam, cevaplar, banka_count)

    def _process_single_file(self, yol):
        try:
            metin = self._dosya_oku(yol)
            if metin and len(metin.strip()) > 10: # Skip empty or too short files
                return self.analyze_response(metin)
        except Exception:
            pass
        return None

    def analyze_response(self, text: str) -> HacizIhbarCevabi:
        # Limit text length to avoid regex hanging on massive files
        process_text = text[:10000]
        clean = IcraUtils.clean_text(process_text)
        muhatap = "Bilinmeyen Muhatap"
        
        for b in self.BANKALAR:
            if IcraUtils.clean_text(b) in clean:
                muhatap = b + " Bankası"
                break
        
        durum = CevapDurumu.BELIRSIZ
        tutar = 0.0
        sonraki = "İncele"

        if "kep iletisi" in clean and len(process_text) < 500:
            return HacizIhbarCevabi(muhatap, CevapDurumu.KEP, 0.0, "Bekle", process_text[:100])

        if any(p.search(clean) for p in self.MENFI_REGEX):
            return HacizIhbarCevabi(muhatap, CevapDurumu.MENFI, 0.0, "89/1 Başkasına", process_text[:200])

        for regex in self.BLOKE_REGEX:
            match = regex.search(process_text)
            if match:
                parsed_tutar = IcraUtils.tutar_parse(match.group(1))
                if parsed_tutar > 0:
                    tutar = parsed_tutar
                    durum = CevapDurumu.BLOKE_VAR
                    sonraki = "Mahsup İste"
                    break
        
        if durum == CevapDurumu.BELIRSIZ:
            if any(p.search(clean) for p in self.BAKIYE_YOK_REGEX):
                 durum = CevapDurumu.HESAP_VAR_BAKIYE_YOK
                 sonraki = "89/2 Gönder"
            elif "haciz" in clean or "bloke" in clean:
                 durum = CevapDurumu.BLOKE_VAR
                 sonraki = "Manuel Kontrol"

        return HacizIhbarCevabi(muhatap, durum, tutar, sonraki, process_text[:300])

    def _dosya_oku(self, yol):
        try:
            if yol.endswith('.udf'):
                with zipfile.ZipFile(yol) as z:
                    xmls = [n for n in z.namelist() if n.endswith('.xml')]
                    target = 'content.xml' if 'content.xml' in xmls else (xmls[0] if xmls else None)
                    if target:
                        return re.sub(r'<[^>]+>', ' ', z.read(target).decode('utf-8', 'ignore'))

            if yol.endswith('.pdf') and PDFPLUMBER_OK:
                # Optimized PDF read: only first 3 pages
                with pdfplumber.open(yol) as pdf:
                    pages = pdf.pages[:3]
                    return "\n".join([p.extract_text() or "" for p in pages])

            if os.path.isfile(yol):
                 with open(yol, 'r', encoding='utf-8', errors='ignore') as f:
                    return f.read(20000) # Limit read size
            return ""
        except: return ""
