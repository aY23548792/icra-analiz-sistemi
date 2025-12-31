#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
89/1-2-3 HACİZ İHBAR ANALİZ MODÜLÜ v2.0
=======================================
Banka VE 3. Şahıs (Gerçek/Tüzel Kişi) cevaplarını analiz eder.

Özellikler:
- Banka cevapları (tüm Türkiye bankaları)
- 3. Şahıs Tüzel Kişi (şirketler, kurumlar)
- 3. Şahıs Gerçek Kişi (borçlunun alacaklı olduğu kişiler)
- Batch yükleme (birden fazla ZIP/dosya)
- 89/1 → 89/2 → 89/3 akış takibi
"""

import os
import re
import zipfile
import tempfile
import shutil
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from pathlib import Path
from enum import Enum

# PDF okuma
try:
    import pdfplumber
    PDF_SUPPORT = True
except ImportError:
    PDF_SUPPORT = False

try:
    import pandas as pd
    PANDAS_SUPPORT = True
except ImportError:
    PANDAS_SUPPORT = False


# ============================================================================
# ENUMLAR
# ============================================================================

class IhbarTuru(Enum):
    IHBAR_89_1 = "89/1 - Birinci Haciz İhbarnamesi"
    IHBAR_89_2 = "89/2 - İkinci Haciz İhbarnamesi"
    IHBAR_89_3 = "89/3 - Üçüncü Haciz İhbarnamesi"
    BILINMIYOR = "Tespit Edilemedi"


class MuhatapTuru(Enum):
    """89/1 muhatabı türü"""
    BANKA = "🏦 Banka"
    TUZEL_KISI = "🏢 Tüzel Kişi (Şirket)"
    GERCEK_KISI = "👤 Gerçek Kişi (3. Şahıs)"
    KAMU_KURUMU = "🏛️ Kamu Kurumu"
    BILINMIYOR = "❓ Tespit Edilemedi"


class CevapDurumu(Enum):
    # Banka için
    BLOKE_VAR = "💰 BLOKE VAR"
    HESAP_VAR_BAKIYE_YOK = "📋 Hesap Var - Bakiye Yok"
    HESAP_YOK = "❌ Hesap Bulunamadı"
    KISMI_BLOKE = "💵 Kısmi Bloke"
    
    # 3. Şahıs için
    ALACAK_VAR = "💵 Alacak/Hak Var"
    ALACAK_YOK = "❌ Alacak/Hak Yok"
    ODEME_YAPILDI = "✅ Ödeme Yapıldı"
    ODEME_TAAHHUT = "📝 Ödeme Taahhüdü"
    
    # Ortak
    ITIRAZ = "⚖️ İtiraz Edildi"
    CEVAP_YOK = "⚠️ Cevap Gelmedi"
    CEVAP_BEKLENIYOR = "⏳ Cevap Bekleniyor"
    PARSE_HATASI = "❓ Parse Edilemedi"


# ============================================================================
# VERİ YAPILARI
# ============================================================================

@dataclass
class HacizIhbarCevabi:
    """Tek bir 89/1-2-3 cevabı (Banka veya 3. Şahıs)"""
    muhatap_adi: str
    muhatap_turu: MuhatapTuru
    ihbar_turu: IhbarTuru
    cevap_durumu: CevapDurumu
    cevap_tarihi: Optional[datetime]
    
    # Tutarlar
    bloke_tutari: Optional[float] = None      # Banka blokesi
    alacak_tutari: Optional[float] = None     # 3. şahıs alacağı
    odenen_tutar: Optional[float] = None      # Ödenen miktar
    
    # Detaylar
    hesap_sayisi: int = 0
    iban_listesi: List[str] = field(default_factory=list)
    vkn: Optional[str] = None                 # Tüzel kişi VKN
    tckn: Optional[str] = None                # Gerçek kişi TCKN
    
    # Meta
    aciklama: str = ""
    dosya_adi: str = ""
    kaynak_zip: str = ""                      # Batch için hangi ZIP'ten geldi
    ham_metin: str = ""
    
    # Aksiyon
    sonraki_adim: str = ""


@dataclass
class HacizIhbarAnalizSonucu:
    """Tüm 89/1-2-3 cevapları analiz sonucu"""
    dosya_no: Optional[str] = None
    
    # Sayılar
    toplam_muhatap: int = 0
    banka_sayisi: int = 0
    tuzel_kisi_sayisi: int = 0
    gercek_kisi_sayisi: int = 0
    cevap_gelen: int = 0
    cevap_gelmeyen: int = 0
    
    # Tutarlar
    toplam_bloke: float = 0.0
    toplam_alacak: float = 0.0
    toplam_odenen: float = 0.0
    
    # Detaylar
    cevaplar: List[HacizIhbarCevabi] = field(default_factory=list)
    eksik_ihbarlar: List[Dict] = field(default_factory=list)
    kritik_uyarilar: List[str] = field(default_factory=list)
    
    # Batch bilgisi
    yuklenen_dosyalar: List[str] = field(default_factory=list)
    
    # Rapor
    ozet_rapor: str = ""


# ============================================================================
# ANA ANALİZ SINIFI
# ============================================================================

class HacizIhbarAnalyzer:
    """89/1-2-3 Haciz İhbarı Analiz Sınıfı - Banka + 3. Şahıs Destekli"""
    
    # ========================================================================
    # BANKALAR
    # ========================================================================
    
    BANKALAR = {
        'ziraat': ['ziraat', 't.c. ziraat', 'ziraatbank', 'ziraat bank'],
        'halk': ['halk', 'halkbank', 'türkiye halk'],
        'vakif': ['vakıf', 'vakıfbank', 'vakifbank'],
        'is': ['iş bank', 'işbank', 'türkiye iş', 'isbank'],
        'garanti': ['garanti', 'garanti bbva'],
        'yapi_kredi': ['yapı kredi', 'yapıkredi', 'ykb'],
        'akbank': ['akbank'],
        'qnb': ['qnb', 'finansbank', 'qnb finansbank'],
        'denizbank': ['deniz', 'denizbank'],
        'ing': ['ing', 'ing bank'],
        'hsbc': ['hsbc'],
        'teb': ['teb', 'türk ekonomi'],
        'sekerbank': ['şeker', 'şekerbank', 'sekerbank'],
        'anadolu': ['anadolubank', 'anadolu bank'],
        'fibabanka': ['fibabanka', 'fiba'],
        'odeabank': ['odeabank', 'odea'],
        'alternatif': ['alternatif', 'alternatifbank'],
        'burgan': ['burgan', 'burganbank'],
        'icbc': ['icbc', 'china'],
        'kuveyt': ['kuveyt', 'kuveyt türk'],
        'turkiye_finans': ['türkiye finans'],
        'albaraka': ['albaraka'],
        'ptt': ['ptt', 'pttbank'],
        'emlak': ['emlak', 'emlakbank', 'emlak katılım'],
        'vakif_katilim': ['vakıf katılım'],
        'ziraat_katilim': ['ziraat katılım'],
    }
    
    BANKA_ISIMLERI = {
        'ziraat': 'Ziraat Bankası',
        'halk': 'Halkbank',
        'vakif': 'VakıfBank',
        'is': 'İş Bankası',
        'garanti': 'Garanti BBVA',
        'yapi_kredi': 'Yapı Kredi',
        'akbank': 'Akbank',
        'qnb': 'QNB Finansbank',
        'denizbank': 'Denizbank',
        'ing': 'ING Bank',
        'hsbc': 'HSBC',
        'teb': 'TEB',
        'sekerbank': 'Şekerbank',
        'anadolu': 'Anadolubank',
        'fibabanka': 'Fibabanka',
        'odeabank': 'Odeabank',
        'alternatif': 'Alternatifbank',
        'burgan': 'Burganbank',
        'icbc': 'ICBC Turkey',
        'kuveyt': 'Kuveyt Türk',
        'turkiye_finans': 'Türkiye Finans',
        'albaraka': 'Albaraka Türk',
        'ptt': 'PTTBank',
        'emlak': 'Emlak Katılım',
        'vakif_katilim': 'Vakıf Katılım',
        'ziraat_katilim': 'Ziraat Katılım',
    }
    
    # ========================================================================
    # KAMU KURUMLARI
    # ========================================================================
    
    KAMU_KURUMLARI = [
        'sgk', 'sosyal güvenlik', 'emekli sandığı', 'bağkur',
        'maliye', 'vergi dairesi', 'gelir idaresi',
        'belediye', 'büyükşehir',
        'tapu', 'kadastro',
        'emniyet', 'trafik',
        'milli eğitim', 'sağlık bakanlığı',
        'tsk', 'msb',
    ]
    
    # ========================================================================
    # ŞİRKET TÜRLERİ
    # ========================================================================
    
    SIRKET_TURLERI = [
        r'a\.?\s*ş\.?', r'anonim\s*şirket',
        r'ltd\.?\s*şti\.?', r'limited\s*şirket',
        r'koll\.?\s*şti\.?', r'kollektif',
        r'kom\.?\s*şti\.?', r'komandit',
        r'koop\.?', r'kooperatif',
        r'holding',
        r'şirket', r'ticaret', r'sanayi',
        r'grup', r'grubu',
    ]
    
    # ========================================================================
    # CEVAP PATTERN'LERİ
    # ========================================================================
    
    # Bloke (banka)
    BLOKE_PATTERNS = [
        r'bloke\s*(?:edil|konul)[^\d]*(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?)',
        r'bloke\s*tutar[ıi]?\s*:?\s*(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?)',
        r'(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?)\s*(?:TL|₺)?\s*bloke',
        r'haciz\s*(?:uygulan|konul)[^\d]*(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?)',
    ]
    
    # Hesap yok (banka)
    HESAP_YOK_PATTERNS = [
        r'hesab[ıi]\s*(?:bulun|mevcut\s*değil|yok)',
        r'kayıtl[ıi]\s*(?:hesab[ıi]?\s*)?(?:bulun|yok)',
        r'müşteri\s*kayd[ıi]\s*(?:bulun|yok|mevcut\s*değil)',
        r'herhangi\s*bir\s*hesap',
        r'hesap\s*kayd[ıi]\s*(?:bulun|tespit\s*edil)eme',
    ]
    
    # Bakiye yok (banka)
    BAKIYE_YOK_PATTERNS = [
        r'bakiye(?:si)?\s*(?:bulun|yok|mevcut\s*değil)',
        r'bakiye\s*:?\s*0[,.]?0{0,2}',
        r'müsait\s*bakiye(?:si)?\s*(?:bulun|yok)',
        r'bloke\s*(?:edilebilir|konulabilir)\s*(?:tutar|bakiye)\s*(?:bulun|yok)',
    ]
    
    # 3. Şahıs - Alacak var
    ALACAK_VAR_PATTERNS = [
        r'alacak\s*(?:hakkı|mevcut|var)',
        r'borç(?:lu|umuz)\s*(?:bulun|mevcut)',
        r'ödeme\s*(?:yapılacak|bekle)',
        r'hak\s*(?:sahip|mevcut)',
        r'(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?)\s*(?:TL|₺)?\s*(?:alacak|borç)',
    ]
    
    # 3. Şahıs - Alacak yok
    ALACAK_YOK_PATTERNS = [
        r'alacak\s*(?:bulun|yok|mevcut\s*değil)',
        r'borç\s*(?:bulun|yok)',
        r'ilişki\s*(?:bulun|yok|mevcut\s*değil)',
        r'ticari\s*(?:ilişki|alışveriş)\s*(?:bulun|yok)',
        r'kayıtlarımızda\s*(?:bulun|yok)',
    ]
    
    # 3. Şahıs - Ödeme yapıldı
    ODEME_PATTERNS = [
        r'ödeme\s*(?:yapıl|gerçekleştir)',
        r'(?:hesab|kasanıza)\s*(?:yatırıl|gönderil)',
        r'havale\s*(?:edil|yapıl)',
        r'(?:icra\s*)?(?:dosyasına|dairesine)\s*(?:ödeme|yatır)',
    ]
    
    # İtiraz
    ITIRAZ_PATTERNS = [
        r'itiraz\s*(?:ed|et)',
        r'kabul\s*(?:etm|etmiy)',
        r'şikayet',
        r'dava\s*(?:açıl|hakkı)',
    ]
    
    # Diğer pattern'ler
    IBAN_PATTERN = r'TR\d{2}\s*\d{4}\s*\d{4}\s*\d{4}\s*\d{4}\s*\d{4}\s*\d{2}'
    VKN_PATTERN = r'\b(\d{10})\b'  # 10 haneli VKN
    TCKN_PATTERN = r'\b(\d{11})\b'  # 11 haneli TCKN
    
    IHBAR_PATTERNS = {
        IhbarTuru.IHBAR_89_1: [r'89/1', r'89\s*/\s*1', r'birinci\s*haciz\s*ihbar', r'1\.\s*haciz\s*ihbar'],
        IhbarTuru.IHBAR_89_2: [r'89/2', r'89\s*/\s*2', r'ikinci\s*haciz\s*ihbar', r'2\.\s*haciz\s*ihbar'],
        IhbarTuru.IHBAR_89_3: [r'89/3', r'89\s*/\s*3', r'üçüncü\s*haciz\s*ihbar', r'3\.\s*haciz\s*ihbar'],
    }
    
    def __init__(self):
        self.bugun = datetime.now()
        self.temp_dirs = []  # Batch için birden fazla temp dir
    
    def _turkce_lower(self, metin: str) -> str:
        """Türkçe karakterleri düzgün lowercase yap"""
        if not metin:
            return ""
        # Türkçe özel karakterler
        tr_map = {
            'İ': 'i', 'I': 'ı',
            'Ğ': 'ğ', 'Ü': 'ü', 'Ş': 'ş', 'Ö': 'ö', 'Ç': 'ç'
        }
        for k, v in tr_map.items():
            metin = metin.replace(k, v)
        return metin.lower()
    
    # ========================================================================
    # YARDIMCI METODLAR
    # ========================================================================
    
    def pattern_ara(self, metin: str, patterns: List[str]) -> bool:
        """Pattern listesinden herhangi biri var mı?"""
        if not metin:
            return False
        metin_lower = metin.lower()
        for p in patterns:
            if re.search(p, metin_lower):
                return True
        return False
    
    def tutar_bul(self, metin: str, patterns: List[str] = None) -> Optional[float]:
        """Metinden para tutarı çıkar"""
        if not metin:
            return None
        
        # IBAN'ları temizle (yanlış tutar tespitini önle)
        metin_temiz = re.sub(self.IBAN_PATTERN, '', metin)
        
        # Önce TL/₺ ile biten tutarları ara (en güvenilir)
        tl_pattern = r'(\d{1,3}(?:\.\d{3})*(?:,\d{2})?)\s*(?:TL|₺|TRY)'
        matches = re.findall(tl_pattern, metin_temiz)
        if matches:
            for m in matches:
                # Türkçe format: 45.678,90 → 45678.90
                tutar_str = m.replace('.', '').replace(',', '.')
                try:
                    tutar = float(tutar_str)
                    if tutar > 0:
                        return tutar
                except:
                    continue
        
        # Pattern'lerle ara
        if patterns:
            for p in patterns:
                match = re.search(p, metin_temiz.lower())
                if match:
                    tutar_str = match.group(1)
                    tutar_str = tutar_str.replace('.', '').replace(',', '.')
                    try:
                        return float(tutar_str)
                    except:
                        continue
        
        return None
    
    def tarih_bul(self, metin: str) -> Optional[datetime]:
        """Metinden tarih çıkar"""
        if not metin:
            return None
        
        for match in re.finditer(r'(\d{2})[./](\d{2})[./](\d{4})', metin):
            try:
                g, a, y = int(match.group(1)), int(match.group(2)), int(match.group(3))
                if 1 <= g <= 31 and 1 <= a <= 12 and 2020 <= y <= 2030:
                    return datetime(y, a, g)
            except:
                continue
        return None
    
    def iban_bul(self, metin: str) -> List[str]:
        """IBAN numaralarını bul"""
        if not metin:
            return []
        ibanlar = re.findall(self.IBAN_PATTERN, metin.upper())
        return list(set([iban.replace(' ', '') for iban in ibanlar]))
    
    def vkn_bul(self, metin: str) -> Optional[str]:
        """10 haneli VKN bul"""
        if not metin:
            return None
        match = re.search(self.VKN_PATTERN, metin)
        return match.group(1) if match else None
    
    def tckn_bul(self, metin: str) -> Optional[str]:
        """11 haneli TCKN bul"""
        if not metin:
            return None
        match = re.search(self.TCKN_PATTERN, metin)
        return match.group(1) if match else None
    
    # ========================================================================
    # MUHATAP TESPİTİ
    # ========================================================================
    
    def muhatap_turu_tespit(self, metin: str, dosya_adi: str = "") -> Tuple[MuhatapTuru, str]:
        """
        Muhatabın türünü ve adını tespit et
        Returns: (muhatap_turu, muhatap_adi)
        """
        metin_lower = self._turkce_lower(metin + " " + dosya_adi)
        
        # 1. BANKA MI? (En önce kontrol - A.Ş. içerse bile banka olabilir)
        for banka_key, patterns in self.BANKALAR.items():
            for p in patterns:
                if p in metin_lower:
                    return MuhatapTuru.BANKA, self.BANKA_ISIMLERI.get(banka_key, banka_key.title())
        
        # 2. Kamu kurumu mu?
        for kurum in self.KAMU_KURUMLARI:
            if kurum in metin_lower:
                kurum_match = re.search(rf'({kurum}[^\n,;]*)', metin_lower)
                kurum_adi = kurum_match.group(1).strip().title() if kurum_match else kurum.title()
                return MuhatapTuru.KAMU_KURUMU, kurum_adi
        
        # 3. Tüzel kişi mi? (şirket)
        for sirket_pattern in self.SIRKET_TURLERI:
            if re.search(sirket_pattern, metin_lower):
                # Şirket adını bul
                sirket_match = re.search(r'([A-ZÇĞİÖŞÜa-zçğıöşü\s\.\-]+(?:A\.?\s*Ş\.?|LTD\.?\s*ŞTİ\.?|HOLDİNG|TİCARET|SANAYİ))', metin, re.IGNORECASE)
                if sirket_match:
                    return MuhatapTuru.TUZEL_KISI, sirket_match.group(1).strip()
                
                vkn = self.vkn_bul(metin)
                if vkn:
                    return MuhatapTuru.TUZEL_KISI, f"Tüzel Kişi (VKN: {vkn})"
                
                return MuhatapTuru.TUZEL_KISI, "Bilinmeyen Şirket"
        
        # 4. Gerçek kişi mi?
        tckn = self.tckn_bul(metin)
        if tckn:
            isim_match = re.search(r'([A-ZÇĞİÖŞÜ][a-zçğıöşü]+\s+[A-ZÇĞİÖŞÜ][a-zçğıöşü]+)', metin)
            if isim_match:
                return MuhatapTuru.GERCEK_KISI, isim_match.group(1)
            return MuhatapTuru.GERCEK_KISI, f"Gerçek Kişi (TCKN: {tckn})"
        
        # Dosya adından çıkar
        if dosya_adi:
            if re.search(r'(?:as|ltd|sti|holding)', dosya_adi.lower()):
                return MuhatapTuru.TUZEL_KISI, dosya_adi.split('.')[0]
        
        return MuhatapTuru.BILINMIYOR, "Bilinmeyen Muhatap"
    
    def ihbar_turu_tespit(self, metin: str) -> IhbarTuru:
        """89/1, 89/2 veya 89/3 tespit et"""
        if not metin:
            return IhbarTuru.BILINMIYOR
        
        metin_lower = metin.lower()
        
        for ihbar_turu, patterns in self.IHBAR_PATTERNS.items():
            for p in patterns:
                if re.search(p, metin_lower):
                    return ihbar_turu
        
        return IhbarTuru.BILINMIYOR
    
    # ========================================================================
    # CEVAP DURUMU TESPİTİ
    # ========================================================================
    
    def cevap_durumu_tespit(self, metin: str, muhatap_turu: MuhatapTuru) -> Tuple[CevapDurumu, Optional[float], str]:
        """
        Cevap durumunu tespit et
        Returns: (durum, tutar, aciklama)
        """
        if not metin:
            return CevapDurumu.PARSE_HATASI, None, "Metin okunamadı"
        
        metin_lower = self._turkce_lower(metin)
        
        # ============ BANKA İÇİN ============
        if muhatap_turu == MuhatapTuru.BANKA:
            # Bloke var mı?
            if 'bloke' in metin_lower or 'haciz' in metin_lower:
                bloke_tutari = self.tutar_bul(metin, self.BLOKE_PATTERNS)
                if bloke_tutari and bloke_tutari > 0:
                    return CevapDurumu.BLOKE_VAR, bloke_tutari, f"💰 {bloke_tutari:,.2f} TL bloke edildi"
                
                # Genel tutar ara
                genel_tutar = self.tutar_bul(metin)
                if genel_tutar and genel_tutar > 0:
                    return CevapDurumu.BLOKE_VAR, genel_tutar, f"💰 {genel_tutar:,.2f} TL bloke edildi"
            
            # Hesap yok mu?
            if any(p in metin_lower for p in ['hesap bulunamadı', 'hesabı yok', 'kayıtlı değil', 'müşteri kaydı yok', 'hesap kaydı bulunama']):
                return CevapDurumu.HESAP_YOK, None, "❌ Bankada hesap bulunamadı"
            
            # Bakiye yok mu?
            if any(p in metin_lower for p in ['bakiye yok', 'bakiyesi yok', 'müsait bakiye', 'bloke edilebilir bakiye yok', 'bakiye: 0']):
                return CevapDurumu.HESAP_VAR_BAKIYE_YOK, 0, "📋 Hesap var ancak bakiye yok/yetersiz"
        
        # ============ 3. ŞAHIS İÇİN ============
        elif muhatap_turu in [MuhatapTuru.TUZEL_KISI, MuhatapTuru.GERCEK_KISI, MuhatapTuru.KAMU_KURUMU]:
            # Ödeme yapıldı mı?
            if any(p in metin_lower for p in ['ödeme yapıl', 'havale edil', 'yatırıl', 'gönderil']):
                tutar = self.tutar_bul(metin)
                return CevapDurumu.ODEME_YAPILDI, tutar, f"✅ Ödeme yapıldı" + (f": {tutar:,.2f} TL" if tutar else "")
            
            # Alacak var mı?
            if any(p in metin_lower for p in ['alacak mevcut', 'alacak var', 'borçlu bulun', 'hak sahip', 'alacak ilişkisi mevcut']):
                tutar = self.tutar_bul(metin)
                return CevapDurumu.ALACAK_VAR, tutar, f"💵 Alacak/hak mevcut" + (f": {tutar:,.2f} TL" if tutar else "")
            
            # Alacak yok mu?
            if any(p in metin_lower for p in ['alacak yok', 'alacak bulunma', 'borç yok', 'borç bulunma', 'borcum bulunma', 'borcum yok', 'ilişki bulunma', 'kayıtlarımızda yok']):
                return CevapDurumu.ALACAK_YOK, None, "❌ Alacak/hak bulunamadı"
        
        # ============ ORTAK ============
        # İtiraz var mı?
        if any(p in metin_lower for p in ['itiraz ed', 'kabul etmiy', 'şikayet']):
            return CevapDurumu.ITIRAZ, None, "⚖️ İtiraz edilmiş"
        
        # Herhangi bir tutar varsa ve banka ise bloke kabul et
        if muhatap_turu == MuhatapTuru.BANKA:
            genel_tutar = self.tutar_bul(metin)
            if genel_tutar and genel_tutar > 0:
                return CevapDurumu.BLOKE_VAR, genel_tutar, f"💰 {genel_tutar:,.2f} TL (tahmini bloke)"
        
        return CevapDurumu.PARSE_HATASI, None, "❓ Cevap içeriği net tespit edilemedi"
    
    # ========================================================================
    # DOSYA OKUMA
    # ========================================================================
    
    def pdf_oku(self, dosya_yolu: str) -> str:
        """PDF'den metin çıkar"""
        metin = ""
        try:
            if PDF_SUPPORT:
                with pdfplumber.open(dosya_yolu) as pdf:
                    for page in pdf.pages:
                        text = page.extract_text()
                        if text:
                            metin += text + "\n"
        except Exception as e:
            metin = f"[PDF okuma hatası: {str(e)}]"
        return metin.strip()
    
    def dosya_oku(self, dosya_yolu: str) -> str:
        """Herhangi bir dosyadan metin çıkar"""
        ext = os.path.splitext(dosya_yolu)[1].lower()
        
        if ext == '.pdf':
            return self.pdf_oku(dosya_yolu)
        elif ext in ['.txt', '.html', '.htm', '.xml']:
            try:
                with open(dosya_yolu, 'r', encoding='utf-8', errors='ignore') as f:
                    return f.read()
            except:
                return ""
        
        return ""
    
    # ========================================================================
    # TEK DOSYA ANALİZİ
    # ========================================================================
    
    def dosya_analiz(self, dosya_yolu: str, kaynak_zip: str = "") -> Optional[HacizIhbarCevabi]:
        """Tek bir dosyayı analiz et"""
        dosya_adi = os.path.basename(dosya_yolu)
        
        metin = self.dosya_oku(dosya_yolu)
        if not metin or len(metin) < 30:
            return None
        
        # Muhatap tespiti
        muhatap_turu, muhatap_adi = self.muhatap_turu_tespit(metin, dosya_adi)
        
        # İhbar türü
        ihbar_turu = self.ihbar_turu_tespit(metin)
        
        # Cevap durumu
        cevap_durumu, tutar, aciklama = self.cevap_durumu_tespit(metin, muhatap_turu)
        
        # Detaylar
        tarih = self.tarih_bul(metin)
        ibanlar = self.iban_bul(metin)
        vkn = self.vkn_bul(metin)
        tckn = self.tckn_bul(metin)
        
        # Tutar atama
        bloke_tutari = None
        alacak_tutari = None
        odenen_tutar = None
        
        if cevap_durumu == CevapDurumu.BLOKE_VAR:
            bloke_tutari = tutar
        elif cevap_durumu in [CevapDurumu.ALACAK_VAR]:
            alacak_tutari = tutar
        elif cevap_durumu == CevapDurumu.ODEME_YAPILDI:
            odenen_tutar = tutar
        
        # Sonraki adım
        sonraki = self._sonraki_adim_belirle(ihbar_turu, cevap_durumu, muhatap_turu)
        
        return HacizIhbarCevabi(
            muhatap_adi=muhatap_adi,
            muhatap_turu=muhatap_turu,
            ihbar_turu=ihbar_turu,
            cevap_durumu=cevap_durumu,
            cevap_tarihi=tarih,
            bloke_tutari=bloke_tutari,
            alacak_tutari=alacak_tutari,
            odenen_tutar=odenen_tutar,
            hesap_sayisi=len(ibanlar),
            iban_listesi=ibanlar,
            vkn=vkn,
            tckn=tckn,
            aciklama=aciklama,
            dosya_adi=dosya_adi,
            kaynak_zip=kaynak_zip,
            ham_metin=metin[:2000],
            sonraki_adim=sonraki
        )
    
    def _sonraki_adim_belirle(self, ihbar: IhbarTuru, durum: CevapDurumu, muhatap: MuhatapTuru) -> str:
        """Sonraki adımı belirle"""
        
        # Olumlu durumlar
        if durum == CevapDurumu.BLOKE_VAR:
            return "✅ Bloke var - Tahsilat bekle veya satış talep et"
        if durum == CevapDurumu.ODEME_YAPILDI:
            return "✅ Ödeme yapılmış - Dosyaya yansımasını kontrol et"
        if durum == CevapDurumu.ALACAK_VAR:
            return "✅ Alacak var - Ödeme/tahsilat takibi yap"
        
        # Olumsuz durumlar
        if durum == CevapDurumu.HESAP_YOK:
            return "ℹ️ Hesap yok - 89/2 göndermeye gerek yok"
        if durum == CevapDurumu.ALACAK_YOK:
            return "ℹ️ Alacak yok - Diğer muhataплара yoğunlaş"
        
        # Ara durumlar - 89/2, 89/3 gönder
        if durum in [CevapDurumu.HESAP_VAR_BAKIYE_YOK, CevapDurumu.CEVAP_YOK, CevapDurumu.PARSE_HATASI]:
            if ihbar == IhbarTuru.IHBAR_89_1:
                return f"📤 89/2 GÖNDER! ({muhatap.value})"
            elif ihbar == IhbarTuru.IHBAR_89_2:
                return f"📤 89/3 GÖNDER! ({muhatap.value})"
            else:
                return "⏳ Son aşama - Sonuç bekle"
        
        if durum == CevapDurumu.ITIRAZ:
            return "⚖️ İtiraz var - İcra Hukuk Mahkemesi'ne başvur"
        
        return "❓ Manuel kontrol et"
    
    # ========================================================================
    # BATCH ANALİZ (BİRDEN FAZLA DOSYA/ZIP)
    # ========================================================================
    
    def batch_analiz(self, dosya_yollari: List[str]) -> HacizIhbarAnalizSonucu:
        """
        Birden fazla dosya/ZIP'i analiz et
        dosya_yollari: ZIP dosyaları veya klasör yolları listesi
        """
        tum_cevaplar = []
        yuklenen_dosyalar = []
        
        for dosya_yolu in dosya_yollari:
            yuklenen_dosyalar.append(os.path.basename(dosya_yolu))
            
            if dosya_yolu.lower().endswith('.zip'):
                cevaplar = self._zip_analiz(dosya_yolu)
                tum_cevaplar.extend(cevaplar)
            elif os.path.isdir(dosya_yolu):
                cevaplar = self._klasor_analiz(dosya_yolu)
                tum_cevaplar.extend(cevaplar)
            else:
                # Tek dosya
                cevap = self.dosya_analiz(dosya_yolu, kaynak_zip=os.path.basename(dosya_yolu))
                if cevap:
                    tum_cevaplar.append(cevap)
        
        return self._sonuc_olustur(tum_cevaplar, yuklenen_dosyalar)
    
    def _zip_analiz(self, zip_yolu: str) -> List[HacizIhbarCevabi]:
        """Tek bir ZIP'i analiz et"""
        cevaplar = []
        temp_dir = tempfile.mkdtemp(prefix="haciz_ihbar_")
        self.temp_dirs.append(temp_dir)
        
        try:
            with zipfile.ZipFile(zip_yolu, 'r') as zf:
                zf.extractall(temp_dir)
            
            kaynak = os.path.basename(zip_yolu)
            
            for root, dirs, files in os.walk(temp_dir):
                for dosya in files:
                    dosya_yolu = os.path.join(root, dosya)
                    ext = os.path.splitext(dosya)[1].lower()
                    
                    if ext in ['.pdf', '.txt', '.html', '.htm', '.xml']:
                        cevap = self.dosya_analiz(dosya_yolu, kaynak_zip=kaynak)
                        if cevap:
                            cevaplar.append(cevap)
        except Exception as e:
            print(f"ZIP okuma hatası: {e}")
        
        return cevaplar
    
    def _klasor_analiz(self, klasor_yolu: str) -> List[HacizIhbarCevabi]:
        """Klasördeki dosyaları analiz et"""
        cevaplar = []
        kaynak = os.path.basename(klasor_yolu)
        
        for root, dirs, files in os.walk(klasor_yolu):
            for dosya in files:
                dosya_yolu = os.path.join(root, dosya)
                ext = os.path.splitext(dosya)[1].lower()
                
                if ext in ['.pdf', '.txt', '.html', '.htm', '.xml']:
                    cevap = self.dosya_analiz(dosya_yolu, kaynak_zip=kaynak)
                    if cevap:
                        cevaplar.append(cevap)
        
        return cevaplar
    
    # ========================================================================
    # SONUÇ OLUŞTURMA
    # ========================================================================
    
    def _sonuc_olustur(self, cevaplar: List[HacizIhbarCevabi], yuklenen_dosyalar: List[str]) -> HacizIhbarAnalizSonucu:
        """Analiz sonucunu oluştur"""
        
        # Sayılar
        banka = [c for c in cevaplar if c.muhatap_turu == MuhatapTuru.BANKA]
        tuzel = [c for c in cevaplar if c.muhatap_turu == MuhatapTuru.TUZEL_KISI]
        gercek = [c for c in cevaplar if c.muhatap_turu == MuhatapTuru.GERCEK_KISI]
        
        # Tutarlar
        toplam_bloke = sum(c.bloke_tutari or 0 for c in cevaplar)
        toplam_alacak = sum(c.alacak_tutari or 0 for c in cevaplar)
        toplam_odenen = sum(c.odenen_tutar or 0 for c in cevaplar)
        
        # Muhatap bazlı grupla (89/1 → 89/2 → 89/3 takibi için)
        muhatap_durumu = {}
        for c in cevaplar:
            key = c.muhatap_adi
            if key not in muhatap_durumu:
                muhatap_durumu[key] = {'89_1': None, '89_2': None, '89_3': None, 'tur': c.muhatap_turu}
            
            if c.ihbar_turu == IhbarTuru.IHBAR_89_1:
                muhatap_durumu[key]['89_1'] = c
            elif c.ihbar_turu == IhbarTuru.IHBAR_89_2:
                muhatap_durumu[key]['89_2'] = c
            elif c.ihbar_turu == IhbarTuru.IHBAR_89_3:
                muhatap_durumu[key]['89_3'] = c
        
        # Eksik ihbarları tespit et
        eksik_ihbarlar = []
        olumsuz_durumlar = [CevapDurumu.HESAP_VAR_BAKIYE_YOK, CevapDurumu.CEVAP_YOK, CevapDurumu.PARSE_HATASI]
        
        for muhatap, durumlar in muhatap_durumu.items():
            c1 = durumlar.get('89_1')
            c2 = durumlar.get('89_2')
            c3 = durumlar.get('89_3')
            tur = durumlar.get('tur')
            
            # 89/1 var ama olumsuz, 89/2 yok → 89/2 gönder
            if c1 and not c2 and c1.cevap_durumu in olumsuz_durumlar:
                eksik_ihbarlar.append({
                    'muhatap': muhatap,
                    'tur': tur.value if tur else '',
                    'gonderilecek': '89/2',
                    'neden': f"89/1 cevabı: {c1.cevap_durumu.value}"
                })
            
            # 89/2 var ama olumsuz, 89/3 yok → 89/3 gönder
            if c2 and not c3 and c2.cevap_durumu in olumsuz_durumlar:
                eksik_ihbarlar.append({
                    'muhatap': muhatap,
                    'tur': tur.value if tur else '',
                    'gonderilecek': '89/3',
                    'neden': f"89/2 cevabı: {c2.cevap_durumu.value}"
                })
        
        # Kritik uyarılar
        kritik = []
        
        bloke_olanlar = [c for c in cevaplar if c.cevap_durumu == CevapDurumu.BLOKE_VAR]
        if bloke_olanlar:
            kritik.append(f"💰 {len(bloke_olanlar)} muhatapda BLOKE VAR - Toplam: {toplam_bloke:,.2f} TL")
        
        alacak_olanlar = [c for c in cevaplar if c.cevap_durumu == CevapDurumu.ALACAK_VAR]
        if alacak_olanlar:
            kritik.append(f"💵 {len(alacak_olanlar)} 3. şahısta ALACAK VAR - Toplam: {toplam_alacak:,.2f} TL")
        
        if eksik_ihbarlar:
            kritik.append(f"📤 {len(eksik_ihbarlar)} muhataba ek ihbar gönderilmeli!")
        
        # Cevap sayıları
        cevap_gelen = len([c for c in cevaplar if c.cevap_durumu not in [CevapDurumu.CEVAP_YOK, CevapDurumu.CEVAP_BEKLENIYOR]])
        
        # Özet rapor
        ozet = self._ozet_rapor_olustur(cevaplar, muhatap_durumu, toplam_bloke, toplam_alacak, eksik_ihbarlar)
        
        return HacizIhbarAnalizSonucu(
            toplam_muhatap=len(muhatap_durumu),
            banka_sayisi=len(banka),
            tuzel_kisi_sayisi=len(tuzel),
            gercek_kisi_sayisi=len(gercek),
            cevap_gelen=cevap_gelen,
            cevap_gelmeyen=len(cevaplar) - cevap_gelen,
            toplam_bloke=toplam_bloke,
            toplam_alacak=toplam_alacak,
            toplam_odenen=toplam_odenen,
            cevaplar=cevaplar,
            eksik_ihbarlar=eksik_ihbarlar,
            kritik_uyarilar=kritik,
            yuklenen_dosyalar=yuklenen_dosyalar,
            ozet_rapor=ozet
        )
    
    def _ozet_rapor_olustur(self, cevaplar, muhatap_durumu, toplam_bloke, toplam_alacak, eksik_ihbarlar) -> str:
        """Özet rapor oluştur"""
        rapor = []
        
        rapor.append("=" * 60)
        rapor.append("📋 89/1-2-3 HACİZ İHBAR ANALİZ RAPORU")
        rapor.append(f"Tarih: {self.bugun.strftime('%d.%m.%Y %H:%M')}")
        rapor.append("=" * 60)
        
        # Muhatap dağılımı
        banka = [c for c in cevaplar if c.muhatap_turu == MuhatapTuru.BANKA]
        tuzel = [c for c in cevaplar if c.muhatap_turu == MuhatapTuru.TUZEL_KISI]
        gercek = [c for c in cevaplar if c.muhatap_turu == MuhatapTuru.GERCEK_KISI]
        kamu = [c for c in cevaplar if c.muhatap_turu == MuhatapTuru.KAMU_KURUMU]
        
        rapor.append("\n📊 GENEL ÖZET")
        rapor.append("-" * 40)
        rapor.append(f"  Toplam Muhatap: {len(muhatap_durumu)}")
        rapor.append(f"    🏦 Banka: {len(set(c.muhatap_adi for c in banka))}")
        rapor.append(f"    🏢 Tüzel Kişi: {len(set(c.muhatap_adi for c in tuzel))}")
        rapor.append(f"    👤 Gerçek Kişi: {len(set(c.muhatap_adi for c in gercek))}")
        rapor.append(f"    🏛️ Kamu Kurumu: {len(set(c.muhatap_adi for c in kamu))}")
        rapor.append(f"  Toplam Cevap: {len(cevaplar)}")
        rapor.append(f"  💰 TOPLAM BLOKE: {toplam_bloke:,.2f} TL")
        rapor.append(f"  💵 TOPLAM ALACAK (3. Şahıs): {toplam_alacak:,.2f} TL")
        
        # Bloke/Alacak olanlar
        bloke_olanlar = [c for c in cevaplar if c.cevap_durumu == CevapDurumu.BLOKE_VAR]
        if bloke_olanlar:
            rapor.append("\n💰 BLOKE OLAN MUHATAPLAR")
            rapor.append("-" * 40)
            for c in bloke_olanlar:
                rapor.append(f"  ✅ {c.muhatap_adi} ({c.muhatap_turu.value}): {c.bloke_tutari:,.2f} TL")
        
        alacak_olanlar = [c for c in cevaplar if c.cevap_durumu == CevapDurumu.ALACAK_VAR]
        if alacak_olanlar:
            rapor.append("\n💵 ALACAK OLAN 3. ŞAHISLAR")
            rapor.append("-" * 40)
            for c in alacak_olanlar:
                tutar_str = f": {c.alacak_tutari:,.2f} TL" if c.alacak_tutari else ""
                rapor.append(f"  ✅ {c.muhatap_adi} ({c.muhatap_turu.value}){tutar_str}")
        
        # Eksik ihbarlar
        if eksik_ihbarlar:
            rapor.append("\n📤 GÖNDERİLMESİ GEREKEN İHBARLAR")
            rapor.append("-" * 40)
            for e in eksik_ihbarlar:
                rapor.append(f"  ⚠️ {e['muhatap']} ({e['tur']})")
                rapor.append(f"     {e['gonderilecek']} GÖNDER! - {e['neden']}")
        
        rapor.append("\n" + "=" * 60)
        rapor.append("Bu rapor otomatik oluşturulmuştur.")
        rapor.append("=" * 60)
        
        return "\n".join(rapor)
    
    # ========================================================================
    # TEMİZLİK
    # ========================================================================
    
    def temizle(self):
        """Geçici dizinleri temizle"""
        for temp_dir in self.temp_dirs:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)
        self.temp_dirs = []
    
    # ========================================================================
    # KOLAY KULLANIM
    # ========================================================================
    
    def analiz_et(self, *dosyalar) -> HacizIhbarAnalizSonucu:
        """
        Kolay kullanım için wrapper
        Tek dosya veya birden fazla dosya kabul eder
        """
        dosya_listesi = list(dosyalar)
        try:
            return self.batch_analiz(dosya_listesi)
        finally:
            self.temizle()


# Geriye uyumluluk için alias
BankaCevapAnalyzer = HacizIhbarAnalyzer
BankaAnalizSonucu = HacizIhbarAnalizSonucu
BankaCevabi = HacizIhbarCevabi


# ============================================================================
# TEST
# ============================================================================

if __name__ == "__main__":
    analyzer = HacizIhbarAnalyzer()
    
    # Test 1: Banka cevabı
    test_banka = """
    T.C. ZİRAAT BANKASI A.Ş.
    89/1 Haciz İhbarnamesi Cevabı
    Borçlu hesabında 45.678,90 TL bloke edilmiştir.
    IBAN: TR12 0001 0012 3456 7890 1234 56
    Tarih: 15.12.2024
    """
    
    print("=== Test 1: Banka ===")
    muhatap_turu, muhatap_adi = analyzer.muhatap_turu_tespit(test_banka)
    print(f"Muhatap: {muhatap_adi} ({muhatap_turu.value})")
    durum, tutar, aciklama = analyzer.cevap_durumu_tespit(test_banka, muhatap_turu)
    print(f"Durum: {durum.value}")
    print(f"Tutar: {tutar}")
    
    # Test 2: 3. Şahıs Tüzel Kişi
    test_sirket = """
    ABC İNŞAAT SANAYİ VE TİCARET A.Ş.
    VKN: 1234567890
    
    89/1 Haciz İhbarnamesi Cevabı
    
    Şirketimiz kayıtlarına göre borçlu ile aramızda 
    125.000,00 TL tutarında alacak ilişkisi mevcuttur.
    """
    
    print("\n=== Test 2: Şirket (3. Şahıs) ===")
    muhatap_turu, muhatap_adi = analyzer.muhatap_turu_tespit(test_sirket)
    print(f"Muhatap: {muhatap_adi} ({muhatap_turu.value})")
    durum, tutar, aciklama = analyzer.cevap_durumu_tespit(test_sirket, muhatap_turu)
    print(f"Durum: {durum.value}")
    print(f"Tutar: {tutar}")
    
    # Test 3: 3. Şahıs Gerçek Kişi
    test_gercek = """
    Mehmet YILMAZ
    TCKN: 12345678901
    
    Haciz ihbarnamenize cevaben;
    Adı geçen şahısa herhangi bir borcum bulunmamaktadır.
    """
    
    print("\n=== Test 3: Gerçek Kişi (3. Şahıs) ===")
    muhatap_turu, muhatap_adi = analyzer.muhatap_turu_tespit(test_gercek)
    print(f"Muhatap: {muhatap_adi} ({muhatap_turu.value})")
    durum, tutar, aciklama = analyzer.cevap_durumu_tespit(test_gercek, muhatap_turu)
    print(f"Durum: {durum.value}")
