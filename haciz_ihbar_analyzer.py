#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HACİZ İHBAR ANALYZER v5.1 (Safety Fix)
=====================================
Oracle mantığını korur, CORE yüklenemezse çökmez.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from enum import Enum
from datetime import datetime
import re
import os

# --- APP.PY'NİN BEKLEDİĞİ ENUMLAR ---
class IhbarTuru(Enum):
    IHBAR_89_1 = "89/1 - Birinci Haciz İhbarnamesi"
    IHBAR_89_2 = "89/2 - İkinci Haciz İhbarnamesi"
    IHBAR_89_3 = "89/3 - Üçüncü Haciz İhbarnamesi"
    BILINMIYOR = "Tespit Edilemedi"

class MuhatapTuru(Enum):
    BANKA = "🏦 Banka"
    TUZEL_KISI = "🏢 Tüzel Kişi"
    GERCEK_KISI = "👤 Gerçek Kişi"
    KAMU_KURUMU = "🏛️ Kamu Kurumu"
    BILINMIYOR = "❓ Tespit Edilemedi"

class CevapDurumu(Enum):
    BLOKE_VAR = "💰 BLOKE VAR"
    HESAP_VAR_BAKIYE_YOK = "📋 Hesap Var - Bakiye Yok"
    HESAP_YOK = "❌ Hesap Bulunamadı"
    KISMI_BLOKE = "💵 Kısmi Bloke"
    ALACAK_VAR = "💵 Alacak/Hak Var"
    ALACAK_YOK = "❌ Alacak/Hak Yok"
    ODEME_YAPILDI = "✅ Ödeme Yapıldı"
    ITIRAZ = "⚖️ İtiraz Edildi"
    CEVAP_YOK = "⚠️ Cevap Gelmedi"
    PARSE_HATASI = "❓ İncelenmeli"

@dataclass
class HacizIhbarCevabi:
    muhatap: str
    muhatap_turu: MuhatapTuru
    ihbar_turu: IhbarTuru
    cevap_durumu: CevapDurumu
    cevap_tarihi: Optional[datetime]
    bloke_tutari: float = 0.0
    sonraki_adim: str = ""
    aciklama: str = ""
    iban_listesi: List[str] = field(default_factory=list)

@dataclass
class HacizIhbarAnalizSonucu:
    toplam_dosya: int = 0
    cevap_gelen: int = 0
    cevap_gelmeyen: int = 0
    bloke_sayisi: int = 0
    toplam_bloke: float = 0.0
    banka_sayisi: int = 0
    cevaplar: List[HacizIhbarCevabi] = field(default_factory=list)
    ozet_rapor: str = ""

# Shared Core Import with Safe Fallback
try:
    from icra_analiz_v2 import IcraUtils
    CORE_OK = True
except Exception:
    CORE_OK = False
    IcraUtils = None

class HacizIhbarAnalyzer:
    
    def __init__(self):
        # Oracle Patterns
        self.MENFI_PATTERNS = [
            re.compile(r'hesap\s*(?:kaydı|bilgisi)?\s*(?:bulunma|yok|mevcut\s*değil)', re.I),
            re.compile(r'borçlu\s*adına\s*kayıt\s*yok', re.I),
            re.compile(r'herhangi\s*bir\s*hak\s*ve\s*alacağa\s*rastlanma', re.I),
            re.compile(r'menfi\s*cevap', re.I),
            re.compile(r'müşteri\s*kaydı?\s*bulunmamakta', re.I)
        ]
        
        self.BAKIYE_YOK_PATTERNS = [
            re.compile(r'bakiye\s*(?:bulunma|yok|yetersiz)', re.I),
            re.compile(r'bakiye\s*:\s*0[,.]00', re.I),
            re.compile(r'blokeli\s*tutar\s*:\s*0', re.I),
            re.compile(r'kullanılabilir\s*bakiye\s*yok', re.I)
        ]

        self.BLOKE_CONTEXT = [
            # Pattern 1: [Keyword] ... [Amount]
            re.compile(
                r'(?:bloke|haciz|tedbir|mahsus|mevduat|bakiyesi|tutar)(?:.{0,60}?)'
                r'(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?)', 
                re.IGNORECASE | re.DOTALL
            ),
            # Pattern 2: [Amount] ... [Keyword]
            re.compile(
                r'(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?)(?:.{0,20}?)(?:tl|₺|try)?(?:.{0,40}?)'
                r'(?:bloke|haciz|şerh|konul|işlem|mevcut)',
                re.IGNORECASE | re.DOTALL
            )
        ]

    def batch_analiz(self, dosya_yollari: List[str]) -> HacizIhbarAnalizSonucu:
        results = []
        total_bloke = 0.0
        all_files = []
        for path in dosya_yollari:
            if os.path.isdir(path):
                for root, _, files in os.walk(path):
                    for f in files:
                        all_files.append(os.path.join(root, f))
            else:
                all_files.append(path)

        for fp in all_files:
            try:
                text = IcraUtils.read_file_content(fp) if CORE_OK else self._fallback_read(fp)
                if not text.strip(): continue
                
                res = self.analyze_response(text, os.path.basename(fp))
                results.append(res)
                if res.cevap_durumu in [CevapDurumu.BLOKE_VAR, CevapDurumu.KISMI_BLOKE]:
                    total_bloke += res.bloke_tutari
            except Exception as e:
                print(f"Hata: {fp} -> {e}")

        return HacizIhbarAnalizSonucu(
            toplam_dosya=len(results),
            cevap_gelen=len(results),
            toplam_bloke=total_bloke,
            bloke_sayisi=len([r for r in results if r.bloke_tutari > 0]),
            banka_sayisi=len(set(r.muhatap for r in results if r.muhatap_turu == MuhatapTuru.BANKA)),
            cevaplar=results,
            ozet_rapor=f"Analiz tamamlandı. Toplam {total_bloke:,.2f} TL bloke bulundu."
        )

    def analyze_response(self, text: str, filename: str) -> HacizIhbarCevabi:
        text_clean = IcraUtils.clean_text(text) if CORE_OK else text.lower()
        muhatap_adi = IcraUtils.banka_tespit(text) if CORE_OK else "Bilinmeyen"
        
        muhatap_turu = MuhatapTuru.BILINMIYOR
        if muhatap_adi and muhatap_adi != "Bilinmeyen":
            muhatap_turu = MuhatapTuru.BANKA
        elif any(x in text_clean for x in ["ltd", "a.ş.", "şti"]):
            muhatap_turu = MuhatapTuru.TUZEL_KISI

        durum = CevapDurumu.PARSE_HATASI
        tutar = 0.0
        sonraki = "İncele"
        
        # --- ORACLE NEGATIVE-FIRST LOGIC ---
        if any(p.search(text) for p in self.MENFI_PATTERNS):
            durum = CevapDurumu.HESAP_YOK
            sonraki = "89/1 Başka bankaya gönder"
        elif any(p.search(text) for p in self.BAKIYE_YOK_PATTERNS):
            durum = CevapDurumu.HESAP_VAR_BAKIYE_YOK
            sonraki = "89/2 Gönder (Hesap boş)"
        # 3. Pozitif Kontrol (Bloke)
        else:
            found_match = None
            for pattern in self.BLOKE_CONTEXT:
                found_match = pattern.search(text)
                if found_match: break
            
            if found_match:
                # Get the group containing the number
                try:
                    raw_amount = found_match.group(1)
                except IndexError:
                    raw_amount = "0"
                
                tutar = IcraUtils.tutar_parse(raw_amount) if CORE_OK else self._fallback_parse(raw_amount)
                if tutar > 5.0:
                    durum = CevapDurumu.BLOKE_VAR
                    sonraki = "MAHSUP TALEBİ GÖNDER!"
                else:
                    durum = CevapDurumu.HESAP_VAR_BAKIYE_YOK
                    sonraki = "89/2 Gönder"
            elif any(x in text_clean for x in ["bloke", "haciz", "şerh"]):
                durum = CevapDurumu.BLOKE_VAR
                sonraki = "Manuel Kontrol (Tutar Okunamadı)"
            elif "itiraz" in text_clean:
                durum = CevapDurumu.ITIRAZ
                sonraki = "İtirazı değerlendirin"

        return HacizIhbarCevabi(
            muhatap=muhatap_adi if muhatap_adi else filename,
            muhatap_turu=muhatap_turu,
            ihbar_turu=IhbarTuru.IHBAR_89_1,
            cevap_durumu=durum,
            cevap_tarihi=datetime.now(),
            bloke_tutari=tutar,
            sonraki_adim=sonraki,
            aciklama=f"{durum.value} - {tutar:,.2f} TL"
        )

    def _fallback_read(self, path):
        try:
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read()
        except: return ""

    def _fallback_parse(self, val):
        try:
            return float(val.replace('.', '').replace(',', '.'))
        except: return 0.0