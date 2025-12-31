#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BANKA CEVAPLARI ANALİZ MODÜLÜ
=============================
89/1, 89/2, 89/3 haciz ihbarnamelerine gelen banka cevaplarını analiz eder.

Özellikler:
- ZIP/klasör içindeki tüm banka cevaplarını aç
- Her bankadan gelen cevabı parse et
- Bloke var mı? Ne kadar? Hesap bilgisi?
- Cevap yoksa → "89/2 gönder" önerisi
- 89/2 gitmiş cevap yoksa → "89/3 gönder" önerisi
- Düzgün PDF + Excel rapor
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

# Excel
try:
    import pandas as pd
    PANDAS_SUPPORT = True
except ImportError:
    PANDAS_SUPPORT = False


class IhbarTuru(Enum):
    IHBAR_89_1 = "89/1 - Birinci Haciz İhbarnamesi"
    IHBAR_89_2 = "89/2 - İkinci Haciz İhbarnamesi"
    IHBAR_89_3 = "89/3 - Üçüncü Haciz İhbarnamesi"
    BILINMIYOR = "Tespit Edilemedi"


class CevapDurumu(Enum):
    BLOKE_VAR = "💰 BLOKE VAR"
    HESAP_VAR_BAKIYE_YOK = "📋 Hesap Var - Bakiye Yok"
    HESAP_YOK = "❌ Hesap Bulunamadı"
    CEVAP_YOK = "⚠️ Cevap Gelmedi"
    CEVAP_BEKLENIYOR = "⏳ Cevap Bekleniyor"
    ITIRAZ = "⚖️ İtiraz Edildi"
    KISMI_BLOKE = "💵 Kısmi Bloke"
    PARSE_HATASI = "❓ Parse Edilemedi"


@dataclass
class BankaCevabi:
    """Tek bir banka cevabı"""
    banka_adi: str
    ihbar_turu: IhbarTuru
    cevap_durumu: CevapDurumu
    cevap_tarihi: Optional[datetime]
    bloke_tutari: Optional[float] = None
    hesap_bakiyesi: Optional[float] = None
    hesap_sayisi: int = 0
    iban_listesi: List[str] = field(default_factory=list)
    aciklama: str = ""
    dosya_adi: str = ""
    ham_metin: str = ""
    
    # Aksiyon önerisi
    sonraki_adim: str = ""


@dataclass
class BankaAnalizSonucu:
    """Tüm banka cevapları analiz sonucu"""
    dosya_no: Optional[str]
    toplam_banka: int
    cevap_gelen: int
    cevap_gelmeyen: int
    toplam_bloke: float
    cevaplar: List[BankaCevabi]
    eksik_ihbarlar: List[Dict]  # Hangi bankaya 89/2 veya 89/3 gönderilmeli
    kritik_uyarilar: List[str]
    ozet_rapor: str


class BankaCevapAnalyzer:
    """Banka cevaplarını analiz eden sınıf"""
    
    # Türkiye'deki bankalar
    BANKALAR = {
        'ziraat': ['ziraat', 't.c. ziraat', 'ziraatbank', 'ziraat bank'],
        'halk': ['halk', 'halkbank', 'türkiye halk'],
        'vakif': ['vakıf', 'vakıfbank', 'vakifbank'],
        'is': ['iş bank', 'işbank', 'türkiye iş'],
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
        'emlak': ['emlak', 'emlakbank'],
        'vakif_katilim': ['vakıf katılım'],
        'ziraat_katilim': ['ziraat katılım'],
    }
    
    # Cevap pattern'leri
    BLOKE_PATTERNS = [
        r'bloke\s*(?:edil|konul)[^\d]*(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?)',
        r'bloke\s*tutar[ıi]?\s*:?\s*(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?)',
        r'(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?)\s*(?:TL|₺)?\s*bloke',
        r'haciz\s*(?:uygulan|konul)[^\d]*(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?)',
    ]
    
    HESAP_YOK_PATTERNS = [
        r'hesab[ıi]\s*(?:bulun|mevcut\s*değil|yok)',
        r'kayıtl[ıi]\s*(?:hesab[ıi]?\s*)?(?:bulun|yok)',
        r'müşteri\s*kayd[ıi]\s*(?:bulun|yok|mevcut\s*değil)',
        r'herhangi\s*bir\s*hesap',
        r'hesap\s*kayd[ıi]\s*(?:bulun|tespit\s*edil)eme',
    ]
    
    BAKIYE_YOK_PATTERNS = [
        r'bakiye(?:si)?\s*(?:bulun|yok|mevcut\s*değil)',
        r'bakiye\s*:?\s*0[,.]?0{0,2}',
        r'müsait\s*bakiye(?:si)?\s*(?:bulun|yok)',
        r'bloke\s*(?:edilebilir|konulabilir)\s*(?:tutar|bakiye)\s*(?:bulun|yok)',
    ]
    
    IBAN_PATTERN = r'TR\d{2}\s*\d{4}\s*\d{4}\s*\d{4}\s*\d{4}\s*\d{4}\s*\d{2}'
    
    IHBAR_PATTERNS = {
        IhbarTuru.IHBAR_89_1: [r'89/1', r'89\s*/\s*1', r'birinci\s*haciz\s*ihbar', r'1\.\s*haciz\s*ihbar'],
        IhbarTuru.IHBAR_89_2: [r'89/2', r'89\s*/\s*2', r'ikinci\s*haciz\s*ihbar', r'2\.\s*haciz\s*ihbar'],
        IhbarTuru.IHBAR_89_3: [r'89/3', r'89\s*/\s*3', r'üçüncü\s*haciz\s*ihbar', r'3\.\s*haciz\s*ihbar'],
    }
    
    def __init__(self):
        self.bugun = datetime.now()
        self.temp_dir = None
        
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
        
        if patterns is None:
            patterns = self.BLOKE_PATTERNS
        
        for p in patterns:
            match = re.search(p, metin.lower())
            if match:
                tutar_str = match.group(1)
                # Türkçe format: 1.234,56 → 1234.56
                tutar_str = tutar_str.replace('.', '').replace(',', '.')
                try:
                    return float(tutar_str)
                except:
                    continue
        
        # Genel tutar pattern
        genel_pattern = r'(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?)\s*(?:TL|₺|TRY)'
        matches = re.findall(genel_pattern, metin)
        if matches:
            for m in matches:
                tutar_str = m.replace('.', '').replace(',', '.')
                try:
                    tutar = float(tutar_str)
                    if tutar > 0:
                        return tutar
                except:
                    continue
        
        return None
    
    def tarih_bul(self, metin: str) -> Optional[datetime]:
        """Metinden tarih çıkar"""
        if not metin:
            return None
        
        # DD.MM.YYYY veya DD/MM/YYYY
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
        # Temizle ve unique yap
        temiz = [iban.replace(' ', '') for iban in ibanlar]
        return list(set(temiz))
    
    def banka_tespit(self, metin: str, dosya_adi: str = "") -> str:
        """Banka adını tespit et"""
        metin_lower = (metin + " " + dosya_adi).lower()
        
        for banka_key, patterns in self.BANKALAR.items():
            for p in patterns:
                if p in metin_lower:
                    # Güzel isim döndür
                    isimler = {
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
                    return isimler.get(banka_key, banka_key.title())
        
        return "Bilinmeyen Banka"
    
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
    
    def cevap_durumu_tespit(self, metin: str) -> Tuple[CevapDurumu, Optional[float], str]:
        """
        Cevap durumunu tespit et
        Returns: (durum, bloke_tutari, aciklama)
        """
        if not metin:
            return CevapDurumu.PARSE_HATASI, None, "Metin okunamadı"
        
        metin_lower = metin.lower()
        
        # 1. Bloke var mı?
        bloke_tutari = self.tutar_bul(metin, self.BLOKE_PATTERNS)
        if bloke_tutari and bloke_tutari > 0:
            return CevapDurumu.BLOKE_VAR, bloke_tutari, f"💰 {bloke_tutari:,.2f} TL bloke edildi"
        
        # Bloke kelimesi var ama tutar yok - kısmi olabilir
        if self.pattern_ara(metin, ['bloke', 'haciz.*uygulan']):
            genel_tutar = self.tutar_bul(metin)
            if genel_tutar and genel_tutar > 0:
                return CevapDurumu.BLOKE_VAR, genel_tutar, f"💰 {genel_tutar:,.2f} TL bloke edildi"
        
        # 2. Hesap yok mu?
        if self.pattern_ara(metin, self.HESAP_YOK_PATTERNS):
            return CevapDurumu.HESAP_YOK, None, "❌ Bankada hesap bulunamadı"
        
        # 3. Hesap var ama bakiye yok mu?
        if self.pattern_ara(metin, self.BAKIYE_YOK_PATTERNS):
            return CevapDurumu.HESAP_VAR_BAKIYE_YOK, 0, "📋 Hesap var ancak bakiye yok/yetersiz"
        
        # 4. İtiraz var mı?
        if self.pattern_ara(metin, ['itiraz', 'şikayet', 'kabul\s*etm']):
            return CevapDurumu.ITIRAZ, None, "⚖️ Banka itiraz etmiş"
        
        # 5. Varsayılan - cevap gelmiş ama parse edilemedi
        return CevapDurumu.PARSE_HATASI, None, "❓ Cevap içeriği net tespit edilemedi"
    
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
    
    def dosya_analiz(self, dosya_yolu: str) -> Optional[BankaCevabi]:
        """Tek bir dosyayı analiz et"""
        dosya_adi = os.path.basename(dosya_yolu)
        ext = os.path.splitext(dosya_adi)[1].lower()
        
        # Metin çıkar
        metin = ""
        if ext == '.pdf':
            metin = self.pdf_oku(dosya_yolu)
        elif ext in ['.txt', '.html', '.htm', '.xml']:
            try:
                with open(dosya_yolu, 'r', encoding='utf-8', errors='ignore') as f:
                    metin = f.read()
            except:
                pass
        
        if not metin or len(metin) < 50:
            return None
        
        # Banka tespit
        banka = self.banka_tespit(metin, dosya_adi)
        
        # İhbar türü
        ihbar = self.ihbar_turu_tespit(metin)
        
        # Cevap durumu
        durum, bloke, aciklama = self.cevap_durumu_tespit(metin)
        
        # Tarih
        tarih = self.tarih_bul(metin)
        
        # IBAN'lar
        ibanlar = self.iban_bul(metin)
        
        # Sonraki adım önerisi
        sonraki = self._sonraki_adim_belirle(ihbar, durum)
        
        return BankaCevabi(
            banka_adi=banka,
            ihbar_turu=ihbar,
            cevap_durumu=durum,
            cevap_tarihi=tarih,
            bloke_tutari=bloke,
            hesap_sayisi=len(ibanlar),
            iban_listesi=ibanlar,
            aciklama=aciklama,
            dosya_adi=dosya_adi,
            ham_metin=metin[:2000],
            sonraki_adim=sonraki
        )
    
    def _sonraki_adim_belirle(self, ihbar: IhbarTuru, durum: CevapDurumu) -> str:
        """Sonraki adımı belirle"""
        if durum == CevapDurumu.BLOKE_VAR:
            return "✅ Bloke var - Tahsilat bekle veya satış talep et"
        
        if durum == CevapDurumu.HESAP_YOK:
            if ihbar == IhbarTuru.IHBAR_89_1:
                return "ℹ️ Hesap yok - 89/2 göndermeye gerek yok"
            return "ℹ️ Hesap yok - Diğer bankalara yoğunlaş"
        
        if durum == CevapDurumu.HESAP_VAR_BAKIYE_YOK:
            if ihbar == IhbarTuru.IHBAR_89_1:
                return "📤 89/2 GÖNDER! (Hesap var, bloke edilebilir bakiye bekleniyor olabilir)"
            elif ihbar == IhbarTuru.IHBAR_89_2:
                return "📤 89/3 GÖNDER! (Son ihbar)"
            else:
                return "⏳ Bekle veya takibi değerlendir"
        
        if durum == CevapDurumu.CEVAP_YOK:
            if ihbar == IhbarTuru.IHBAR_89_1:
                return "⚠️ 89/1 Cevap gelmedi - 89/2 GÖNDER!"
            elif ihbar == IhbarTuru.IHBAR_89_2:
                return "⚠️ 89/2 Cevap gelmedi - 89/3 GÖNDER!"
            else:
                return "⚠️ Cevap bekleniyor"
        
        if durum == CevapDurumu.ITIRAZ:
            return "⚖️ İtiraz var - İcra Hukuk Mahkemesi'ne başvur"
        
        return "❓ Durumu manuel kontrol et"
    
    def klasor_analiz(self, klasor_yolu: str) -> BankaAnalizSonucu:
        """Klasördeki tüm banka cevaplarını analiz et"""
        cevaplar = []
        toplam_bloke = 0.0
        banka_durumu = {}  # Her banka için son durum
        
        # Klasördeki dosyaları tara
        for root, dirs, files in os.walk(klasor_yolu):
            for dosya in files:
                dosya_yolu = os.path.join(root, dosya)
                ext = os.path.splitext(dosya)[1].lower()
                
                if ext in ['.pdf', '.txt', '.html', '.htm', '.xml']:
                    cevap = self.dosya_analiz(dosya_yolu)
                    if cevap:
                        cevaplar.append(cevap)
                        
                        # Bloke topla
                        if cevap.bloke_tutari:
                            toplam_bloke += cevap.bloke_tutari
                        
                        # Banka durumunu güncelle
                        banka = cevap.banka_adi
                        if banka not in banka_durumu:
                            banka_durumu[banka] = {'89_1': None, '89_2': None, '89_3': None}
                        
                        if cevap.ihbar_turu == IhbarTuru.IHBAR_89_1:
                            banka_durumu[banka]['89_1'] = cevap
                        elif cevap.ihbar_turu == IhbarTuru.IHBAR_89_2:
                            banka_durumu[banka]['89_2'] = cevap
                        elif cevap.ihbar_turu == IhbarTuru.IHBAR_89_3:
                            banka_durumu[banka]['89_3'] = cevap
        
        # Eksik ihbarları tespit et
        eksik_ihbarlar = []
        for banka, durumlar in banka_durumu.items():
            c1 = durumlar.get('89_1')
            c2 = durumlar.get('89_2')
            c3 = durumlar.get('89_3')
            
            # 89/1 var, cevap "hesap var bakiye yok" veya "cevap yok" → 89/2 gönder
            if c1 and not c2:
                if c1.cevap_durumu in [CevapDurumu.HESAP_VAR_BAKIYE_YOK, CevapDurumu.CEVAP_YOK, CevapDurumu.PARSE_HATASI]:
                    eksik_ihbarlar.append({
                        'banka': banka,
                        'gonderilecek': '89/2',
                        'neden': f"89/1 cevabı: {c1.cevap_durumu.value}"
                    })
            
            # 89/2 var, cevap olumsuz → 89/3 gönder
            if c2 and not c3:
                if c2.cevap_durumu in [CevapDurumu.HESAP_VAR_BAKIYE_YOK, CevapDurumu.CEVAP_YOK, CevapDurumu.PARSE_HATASI]:
                    eksik_ihbarlar.append({
                        'banka': banka,
                        'gonderilecek': '89/3',
                        'neden': f"89/2 cevabı: {c2.cevap_durumu.value}"
                    })
        
        # Kritik uyarılar
        kritik = []
        
        bloke_olanlar = [c for c in cevaplar if c.cevap_durumu == CevapDurumu.BLOKE_VAR]
        if bloke_olanlar:
            kritik.append(f"💰 {len(bloke_olanlar)} bankada BLOKE VAR - Toplam: {toplam_bloke:,.2f} TL")
        
        if eksik_ihbarlar:
            kritik.append(f"📤 {len(eksik_ihbarlar)} bankaya ek ihbar gönderilmeli!")
        
        cevap_gelen = len([c for c in cevaplar if c.cevap_durumu != CevapDurumu.CEVAP_YOK])
        
        # Özet rapor
        ozet = self._ozet_rapor_olustur(cevaplar, banka_durumu, toplam_bloke, eksik_ihbarlar)
        
        return BankaAnalizSonucu(
            dosya_no=None,
            toplam_banka=len(banka_durumu),
            cevap_gelen=cevap_gelen,
            cevap_gelmeyen=len(cevaplar) - cevap_gelen,
            toplam_bloke=toplam_bloke,
            cevaplar=cevaplar,
            eksik_ihbarlar=eksik_ihbarlar,
            kritik_uyarilar=kritik,
            ozet_rapor=ozet
        )
    
    def arsiv_analiz(self, arsiv_yolu: str) -> BankaAnalizSonucu:
        """ZIP arşivini analiz et"""
        self.temp_dir = tempfile.mkdtemp(prefix="banka_cevap_")
        
        try:
            # ZIP aç
            with zipfile.ZipFile(arsiv_yolu, 'r') as zf:
                zf.extractall(self.temp_dir)
            
            # Klasörü analiz et
            return self.klasor_analiz(self.temp_dir)
        
        finally:
            # Temizlik
            if self.temp_dir and os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir, ignore_errors=True)
                self.temp_dir = None
    
    def _ozet_rapor_olustur(self, cevaplar: List[BankaCevabi], banka_durumu: Dict, 
                            toplam_bloke: float, eksik_ihbarlar: List[Dict]) -> str:
        """Özet rapor oluştur"""
        rapor = []
        
        rapor.append("=" * 60)
        rapor.append("🏦 BANKA CEVAPLARI ANALİZ RAPORU")
        rapor.append(f"Tarih: {self.bugun.strftime('%d.%m.%Y %H:%M')}")
        rapor.append("=" * 60)
        
        # Genel özet
        rapor.append("\n📊 GENEL ÖZET")
        rapor.append("-" * 40)
        rapor.append(f"  Toplam Banka: {len(banka_durumu)}")
        rapor.append(f"  Toplam Cevap: {len(cevaplar)}")
        rapor.append(f"  💰 TOPLAM BLOKE: {toplam_bloke:,.2f} TL")
        
        # Bloke olan bankalar
        bloke_olanlar = [c for c in cevaplar if c.cevap_durumu == CevapDurumu.BLOKE_VAR]
        if bloke_olanlar:
            rapor.append("\n💰 BLOKE OLAN BANKALAR")
            rapor.append("-" * 40)
            for c in bloke_olanlar:
                rapor.append(f"  ✅ {c.banka_adi}: {c.bloke_tutari:,.2f} TL")
        
        # Hesap yok
        hesap_yok = [c for c in cevaplar if c.cevap_durumu == CevapDurumu.HESAP_YOK]
        if hesap_yok:
            rapor.append("\n❌ HESAP BULUNAMAYAN BANKALAR")
            rapor.append("-" * 40)
            for c in hesap_yok:
                rapor.append(f"  • {c.banka_adi}")
        
        # Eksik ihbarlar (AKSİYON GEREKLİ)
        if eksik_ihbarlar:
            rapor.append("\n📤 GÖNDERİLMESİ GEREKEN İHBARLAR")
            rapor.append("-" * 40)
            for e in eksik_ihbarlar:
                rapor.append(f"  ⚠️ {e['banka']}: {e['gonderilecek']} GÖNDER!")
                rapor.append(f"     Neden: {e['neden']}")
        
        # Banka banka detay
        rapor.append("\n📋 BANKA BANKA DETAY")
        rapor.append("-" * 40)
        
        for banka, durumlar in sorted(banka_durumu.items()):
            rapor.append(f"\n  🏦 {banka}")
            
            c1 = durumlar.get('89_1')
            c2 = durumlar.get('89_2')
            c3 = durumlar.get('89_3')
            
            if c1:
                rapor.append(f"     89/1: {c1.cevap_durumu.value}")
                if c1.bloke_tutari:
                    rapor.append(f"           Bloke: {c1.bloke_tutari:,.2f} TL")
            else:
                rapor.append("     89/1: Cevap yok")
            
            if c2:
                rapor.append(f"     89/2: {c2.cevap_durumu.value}")
            
            if c3:
                rapor.append(f"     89/3: {c3.cevap_durumu.value}")
        
        rapor.append("\n" + "=" * 60)
        rapor.append("Bu rapor otomatik oluşturulmuştur.")
        rapor.append("=" * 60)
        
        return "\n".join(rapor)


# Test
if __name__ == "__main__":
    analyzer = BankaCevapAnalyzer()
    
    # Test metni - Ziraat cevabı
    test1 = """
    T.C. ZİRAAT BANKASI A.Ş.
    
    89/1 Haciz İhbarnamesi Cevabı
    
    Sayın İcra Müdürlüğü,
    
    Borçlu AHMET YILMAZ adına kayıtlı hesaplarda 
    toplam 45.678,90 TL bloke edilmiştir.
    
    IBAN: TR12 0001 0012 3456 7890 1234 56
    
    Tarih: 15.12.2024
    """
    
    print("=== Test 1: Ziraat Cevabı ===")
    print("Banka:", analyzer.banka_tespit(test1))
    print("İhbar:", analyzer.ihbar_turu_tespit(test1).value)
    durum, bloke, aciklama = analyzer.cevap_durumu_tespit(test1)
    print("Durum:", durum.value)
    print("Bloke:", bloke)
    print("Açıklama:", aciklama)
    print("IBAN:", analyzer.iban_bul(test1))
    
    # Test 2 - Hesap yok
    test2 = """
    GARANTİ BBVA
    
    Haciz İhbarnamesi Cevabı
    
    Bankamız nezdinde ilgili borçluya ait 
    herhangi bir hesap kaydı bulunamamıştır.
    """
    
    print("\n=== Test 2: Garanti - Hesap Yok ===")
    print("Banka:", analyzer.banka_tespit(test2))
    durum, bloke, aciklama = analyzer.cevap_durumu_tespit(test2)
    print("Durum:", durum.value)
    print("Açıklama:", aciklama)
    
    # Test 3 - Bakiye yok
    test3 = """
    AKBANK T.A.Ş.
    
    89/1 Haciz İhbarnamesi Cevabı
    
    Borçlu adına hesap mevcuttur ancak
    bloke edilebilir bakiye bulunmamaktadır.
    
    IBAN: TR99 0004 6000 1234 5678 9012 34
    """
    
    print("\n=== Test 3: Akbank - Bakiye Yok ===")
    print("Banka:", analyzer.banka_tespit(test3))
    durum, bloke, aciklama = analyzer.cevap_durumu_tespit(test3)
    print("Durum:", durum.value)
    print("Sonraki Adım:", analyzer._sonraki_adim_belirle(IhbarTuru.IHBAR_89_1, durum))
