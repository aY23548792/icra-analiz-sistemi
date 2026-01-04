#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
UYAP DOSYA ANALİZ MOTORU v3.0
=============================
UYAP ZIP'ten otomatik analiz → Excel + PDF + Rapor ÇIKTI

VİZYON:
- GİRDİ: Sadece UYAP ZIP (kullanıcı hiçbir şey doldurmaz)
- ÇIKTI: Excel, PDF, Rapor (sistem her şeyi üretir)

Analiz Edilen Evrak Türleri:
- Ödeme emri / İcra emri
- Tebligat mazbataları (21/35)
- 89/1-2-3 haciz ihbarnameleri
- Haciz tutanakları
- Kıymet takdiri raporları
- 103 davetiyeler
- Satış ilanları
- Mahkeme yazışmaları
"""

import os
import re
import zipfile
import tempfile
import shutil
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Any
from enum import Enum
import xml.etree.ElementTree as ET

# PDF okuma
try:
    import pdfplumber
    PDF_OK = True
except ImportError:
    PDF_OK = False

# Excel yazma
try:
    import pandas as pd
    PANDAS_OK = True
except ImportError:
    PANDAS_OK = False


# ============================================================================
# ENUM'LAR
# ============================================================================

class EvrakTuru(Enum):
    """UYAP evrak türleri"""
    ODEME_EMRI = "Ödeme Emri"
    ICRA_EMRI = "İcra Emri"
    TEBLIGAT_MAZBATASI = "Tebligat Mazbatası"
    HACIZ_IHBARNAMESI_89_1 = "89/1 Haciz İhbarnamesi"
    HACIZ_IHBARNAMESI_89_2 = "89/2 Haciz İhbarnamesi"
    HACIZ_IHBARNAMESI_89_3 = "89/3 Haciz İhbarnamesi"
    HACIZ_TUTANAGI = "Haciz Tutanağı"
    HACIZ_MUZEKKERESI = "Haciz Müzekkeresi"
    KIYMET_TAKDIRI = "Kıymet Takdiri"
    DAVETIYE_103 = "103 Davetiyesi"
    SATIS_ILANI = "Satış İlanı"
    MAHKEME_YAZISI = "Mahkeme Yazısı"
    BANKA_CEVABI = "Banka Cevabı"
    VEKALETNAME = "Vekaletname"
    TALEP_DILEKCESI = "Talep Dilekçesi"
    KARAR = "Karar"
    DIGER = "Diğer Evrak"


class TebligatDurumu(Enum):
    """Tebligat durumları"""
    TEBLIG_EDILDI = "✅ Tebliğ Edildi"
    BILA = "❌ Bila (İade)"
    TEBLIGAT_21 = "📬 21. Madde Tebligatı"
    TEBLIGAT_35 = "📬 35. Madde Tebligatı"
    BEKLENIYOR = "⏳ Bekleniyor"
    BILINMIYOR = "❓ Bilinmiyor"


class IslemDurumu(Enum):
    """İşlem durumları"""
    TAMAMLANDI = "✅ Tamamlandı"
    BEKLEMEDE = "⏳ Beklemede"
    KRITIK = "🔴 KRİTİK"
    UYARI = "⚠️ Uyarı"
    BILGI = "ℹ️ Bilgi"


# ============================================================================
# VERİ YAPILARI
# ============================================================================

@dataclass
class EvrakBilgisi:
    """Tek bir evrak bilgisi"""
    dosya_adi: str
    evrak_turu: EvrakTuru
    tarih: Optional[datetime] = None
    ozet: str = ""
    metin: str = ""
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TebligatBilgisi:
    """Tebligat bilgisi"""
    evrak_adi: str
    tarih: Optional[datetime] = None
    durum: TebligatDurumu = TebligatDurumu.BILINMIYOR
    kime: str = ""
    adres: str = ""
    aciklama: str = ""


@dataclass
class HacizBilgisi:
    """Haciz bilgisi"""
    tur: str  # Araç, Taşınmaz, Banka, Maaş
    tarih: Optional[datetime] = None
    hedef: str = ""  # Plaka, Ada/Parsel, Banka adı
    tutar: Optional[float] = None
    durum: str = ""
    sure_106_110: Optional[int] = None  # Kalan gün (sadece araç/taşınmaz)


@dataclass
class AksiyonOnerisi:
    """Yapılması gereken aksiyon"""
    oncelik: IslemDurumu
    baslik: str
    aciklama: str
    son_tarih: Optional[datetime] = None
    ilgili_evrak: str = ""


@dataclass
class DosyaAnalizSonucu:
    """Tam dosya analiz sonucu"""
    # Genel bilgiler
    analiz_tarihi: datetime = field(default_factory=datetime.now)
    toplam_evrak: int = 0
    
    # Evraklar
    evraklar: List[EvrakBilgisi] = field(default_factory=list)
    
    # Tebligatlar
    tebligatlar: List[TebligatBilgisi] = field(default_factory=list)
    tebligat_durumu: TebligatDurumu = TebligatDurumu.BILINMIYOR
    
    # Hacizler
    hacizler: List[HacizBilgisi] = field(default_factory=list)
    toplam_bloke: float = 0.0
    
    # Süreler
    kritik_tarihler: List[Dict] = field(default_factory=list)
    
    # Aksiyonlar
    aksiyonlar: List[AksiyonOnerisi] = field(default_factory=list)
    
    # İstatistikler
    evrak_dagilimi: Dict[str, int] = field(default_factory=dict)
    
    # Özet
    ozet_rapor: str = ""


# ============================================================================
# ANA ANALİZ SINIFI
# ============================================================================

class UYAPDosyaAnalyzer:
    """UYAP ZIP dosyasını analiz eder"""
    
    # Evrak türü pattern'leri
    EVRAK_PATTERNS = {
        EvrakTuru.ODEME_EMRI: [
            r'ödeme\s*emr', r'odeme\s*emr', r'7\s*örnek', r'örnek\s*7'
        ],
        EvrakTuru.ICRA_EMRI: [
            r'icra\s*emr', r'İcra\s*emr'
        ],
        EvrakTuru.TEBLIGAT_MAZBATASI: [
            r'tebli[gğ]\s*mazbata', r'mazbata', r'tebli[gğ]at'
        ],
        EvrakTuru.HACIZ_IHBARNAMESI_89_1: [
            r'89/1', r'89\s*/\s*1', r'birinci\s*haciz\s*ihbar'
        ],
        EvrakTuru.HACIZ_IHBARNAMESI_89_2: [
            r'89/2', r'89\s*/\s*2', r'ikinci\s*haciz\s*ihbar'
        ],
        EvrakTuru.HACIZ_IHBARNAMESI_89_3: [
            r'89/3', r'89\s*/\s*3', r'üçüncü\s*haciz\s*ihbar'
        ],
        EvrakTuru.HACIZ_TUTANAGI: [
            r'haciz\s*tutana[gğ]', r'haciz\s*zab[ıi]t'
        ],
        EvrakTuru.HACIZ_MUZEKKERESI: [
            r'haciz\s*müzekkere', r'haciz\s*yazı'
        ],
        EvrakTuru.KIYMET_TAKDIRI: [
            r'k[ıi]ymet\s*takdir', r'değer\s*tespit', r'bilirkişi\s*rapor'
        ],
        EvrakTuru.DAVETIYE_103: [
            r'103', r'davetiye', r'sat[ıi]ş\s*günü'
        ],
        EvrakTuru.SATIS_ILANI: [
            r'sat[ıi]ş\s*ilan', r'ihale', r'açık\s*art[ıi]rma'
        ],
        EvrakTuru.MAHKEME_YAZISI: [
            r'mahkeme', r'icra\s*hukuk', r'dava', r'karar'
        ],
        EvrakTuru.BANKA_CEVABI: [
            r'banka', r'bloke', r'hesap', r'bakiye'
        ],
        EvrakTuru.VEKALETNAME: [
            r'vekaletname', r'vekalet', r'temsil'
        ],
    }
    
    # Tebligat pattern'leri
    TEBLIGAT_PATTERNS = {
        TebligatDurumu.TEBLIG_EDILDI: [
            r'tebli[gğ]\s*edildi', r'tebli[gğ]\s*edilmiş', r'teslim\s*edildi',
            r'imza\s*karşılığı', r'bizzat'
        ],
        TebligatDurumu.BILA: [
            r'bila', r'iade', r'tebli[gğ]\s*edilemedi', r'adres\s*yok',
            r'taşınmış', r'tanınmıyor', r'adreste\s*yok'
        ],
        TebligatDurumu.TEBLIGAT_21: [
            r'21\.?\s*madde', r'21/1', r'21/2', r'komşu', r'muhtar', r'kapıya\s*yapıştır'
        ],
        TebligatDurumu.TEBLIGAT_35: [
            r'35\.?\s*madde', r'35/1', r'35/2', r'mernis', r'adrese\s*dayalı'
        ],
    }
    
    # Haciz türü pattern'leri
    HACIZ_TURLERI = {
        'ARAC': [r'araç', r'plaka', r'taşıt', r'otomobil', r'motosiklet'],
        'TASINMAZ': [r'taşınmaz', r'gayrimenkul', r'ada', r'parsel', r'tapu'],
        'BANKA': [r'banka', r'hesap', r'mevduat', r'bloke'],
        'MAAS': [r'maaş', r'ücret', r'sgk', r'emekli'],
        'DIGER': [r'haciz'],
    }
    
    def __init__(self):
        self.temp_dir = None
        self.bugun = datetime.now()
    
    # ========================================================================
    # YARDIMCI METODLAR
    # ========================================================================
    
    def _turkce_lower(self, metin: str) -> str:
        """Türkçe karakterleri düzgün lowercase yap"""
        if not metin:
            return ""
        tr_map = {'İ': 'i', 'I': 'ı', 'Ğ': 'ğ', 'Ü': 'ü', 'Ş': 'ş', 'Ö': 'ö', 'Ç': 'ç'}
        for k, v in tr_map.items():
            metin = metin.replace(k, v)
        return metin.lower()
    
    def _tarih_bul(self, metin: str) -> Optional[datetime]:
        """Metinden tarih çıkar"""
        if not metin:
            return None
        
        patterns = [
            r'(\d{2})[./](\d{2})[./](\d{4})',  # 31.12.2024
            r'(\d{4})[./\-](\d{2})[./\-](\d{2})',  # 2024-12-31
        ]
        
        for pattern in patterns:
            for match in re.finditer(pattern, metin):
                try:
                    groups = match.groups()
                    if len(groups[0]) == 4:  # YYYY-MM-DD
                        y, a, g = int(groups[0]), int(groups[1]), int(groups[2])
                    else:  # DD.MM.YYYY
                        g, a, y = int(groups[0]), int(groups[1]), int(groups[2])
                    
                    if 1 <= g <= 31 and 1 <= a <= 12 and 2000 <= y <= 2030:
                        return datetime(y, a, g)
                except:
                    continue
        return None
    
    def _tutar_bul(self, metin: str) -> Optional[float]:
        """Metinden tutar çıkar"""
        if not metin:
            return None
        
        # IBAN'ları temizle
        metin = re.sub(r'TR\d{2}\s*\d{4}\s*\d{4}\s*\d{4}\s*\d{4}\s*\d{4}\s*\d{2}', '', metin)
        
        # TL ile biten tutarları ara
        pattern = r'(\d{1,3}(?:\.\d{3})*(?:,\d{2})?)\s*(?:TL|₺|TRY)'
        matches = re.findall(pattern, metin)
        
        for m in matches:
            try:
                tutar_str = m.replace('.', '').replace(',', '.')
                tutar = float(tutar_str)
                if tutar > 0:
                    return tutar
            except:
                continue
        
        return None
    
    def _bloke_tutar_bul(self, metin: str) -> Optional[float]:
        """SADECE bloke tutarlarını bul - talep tutarlarını ALMA"""
        if not metin:
            return None
        
        # IBAN'ları temizle
        metin = re.sub(r'TR\d{2}\s*\d{4}\s*\d{4}\s*\d{4}\s*\d{4}\s*\d{4}\s*\d{2}', '', metin)
        
        toplam_bloke = 0.0
        satirlar = metin.split('\n')
        
        for satir in satirlar:
            satir_lower = satir.lower()
            # Sadece "bloke" veya "hacz" veya "tedbir" geçen satırlardan tutar al
            if any(k in satir_lower for k in ['bloke', 'hacz', 'tedbir', 'kısıtlı', 'dondur']):
                # "borç" veya "talep" veya "alacak" geçiyorsa ATLA - bunlar bloke değil
                if any(k in satir_lower for k in ['borç yok', 'alacak yok', 'bulunmamakta', 'yoktur']):
                    continue
                
                # Bu satırdan tutar çıkar
                pattern = r'(\d{1,3}(?:\.\d{3})*(?:,\d{2})?)\s*(?:TL|₺|TRY)?'
                matches = re.findall(pattern, satir)
                
                for m in matches:
                    try:
                        tutar_str = m.replace('.', '').replace(',', '.')
                        tutar = float(tutar_str)
                        if tutar > 1:  # 0 ve 1'i atla
                            toplam_bloke += tutar
                    except:
                        continue
        
        return toplam_bloke if toplam_bloke > 0 else None
    
    def _pattern_ara(self, metin: str, patterns: List[str]) -> bool:
        """Pattern listesinde ara"""
        if not metin:
            return False
        metin_lower = self._turkce_lower(metin)
        for p in patterns:
            if re.search(p, metin_lower):
                return True
        return False
    
    # ========================================================================
    # DOSYA OKUMA
    # ========================================================================
    
    def _dosya_oku(self, dosya_yolu: str) -> str:
        """Dosyadan metin çıkar"""
        ext = os.path.splitext(dosya_yolu)[1].lower()
        
        if ext == '.pdf':
            return self._pdf_oku(dosya_yolu)
        elif ext == '.udf':
            return self._udf_oku(dosya_yolu)
        elif ext in ['.txt', '.html', '.htm', '.xml']:
            try:
                with open(dosya_yolu, 'r', encoding='utf-8', errors='ignore') as f:
                    return f.read()
            except:
                return ""
        return ""
    
    def _pdf_oku(self, dosya_yolu: str) -> str:
        """PDF'den metin çıkar"""
        if not PDF_OK:
            return ""
        
        metin = ""
        try:
            with pdfplumber.open(dosya_yolu) as pdf:
                for page in pdf.pages:
                    text = page.extract_text()
                    if text:
                        metin += text + "\n"
        except:
            pass
        return metin.strip()
    
    def _udf_oku(self, dosya_yolu: str) -> str:
        """UDF'den metin çıkar"""
        metin = ""
        try:
            with zipfile.ZipFile(dosya_yolu, 'r') as zf:
                for name in zf.namelist():
                    if name.endswith('.xml'):
                        with zf.open(name) as f:
                            content = f.read().decode('utf-8', errors='ignore')
                            try:
                                root = ET.fromstring(content)
                                for elem in root.iter():
                                    if elem.text and elem.text.strip():
                                        metin += elem.text.strip() + "\n"
                            except:
                                metin += content
                    elif name.endswith('.txt'):
                        with zf.open(name) as f:
                            metin += f.read().decode('utf-8', errors='ignore')
        except:
            pass
        return metin.strip()
    
    # ========================================================================
    # EVRAK TESPİTİ
    # ========================================================================
    
    def _evrak_turu_tespit(self, metin: str, dosya_adi: str) -> EvrakTuru:
        """Evrak türünü tespit et"""
        kontrol_metin = self._turkce_lower(metin + " " + dosya_adi)
        
        for evrak_turu, patterns in self.EVRAK_PATTERNS.items():
            for p in patterns:
                if re.search(p, kontrol_metin):
                    return evrak_turu
        
        return EvrakTuru.DIGER
    
    def _tebligat_durumu_tespit(self, metin: str) -> TebligatDurumu:
        """Tebligat durumunu tespit et"""
        metin_lower = self._turkce_lower(metin)
        
        for durum, patterns in self.TEBLIGAT_PATTERNS.items():
            for p in patterns:
                if re.search(p, metin_lower):
                    return durum
        
        return TebligatDurumu.BILINMIYOR
    
    def _haciz_turu_tespit(self, metin: str) -> str:
        """Haciz türünü tespit et"""
        metin_lower = self._turkce_lower(metin)
        
        for haciz_turu, patterns in self.HACIZ_TURLERI.items():
            for p in patterns:
                if re.search(p, metin_lower):
                    return haciz_turu
        
        return "DIGER"
    
    # ========================================================================
    # ANA ANALİZ
    # ========================================================================
    
    def analiz_et(self, zip_yolu: str) -> DosyaAnalizSonucu:
        """
        UYAP ZIP dosyasını analiz et
        
        Args:
            zip_yolu: ZIP dosya yolu
        
        Returns:
            DosyaAnalizSonucu
        """
        sonuc = DosyaAnalizSonucu()
        
        # Temp dizin oluştur
        self.temp_dir = tempfile.mkdtemp(prefix="uyap_analiz_")
        
        try:
            # ZIP'i aç
            dosya_listesi = self._zip_ac(zip_yolu)
            sonuc.toplam_evrak = len(dosya_listesi)
            
            # Her dosyayı analiz et
            for dosya_yolu in dosya_listesi:
                evrak = self._dosya_analiz(dosya_yolu)
                if evrak:
                    sonuc.evraklar.append(evrak)
                    
                    # Evrak dağılımı
                    tur_adi = evrak.evrak_turu.value
                    sonuc.evrak_dagilimi[tur_adi] = sonuc.evrak_dagilimi.get(tur_adi, 0) + 1
                    
                    # Tebligat mı?
                    if evrak.evrak_turu == EvrakTuru.TEBLIGAT_MAZBATASI:
                        tebligat = self._tebligat_analiz(evrak)
                        sonuc.tebligatlar.append(tebligat)
                    
                    # Haciz mi?
                    if evrak.evrak_turu in [
                        EvrakTuru.HACIZ_IHBARNAMESI_89_1,
                        EvrakTuru.HACIZ_IHBARNAMESI_89_2,
                        EvrakTuru.HACIZ_IHBARNAMESI_89_3,
                        EvrakTuru.HACIZ_TUTANAGI,
                        EvrakTuru.HACIZ_MUZEKKERESI,
                        EvrakTuru.BANKA_CEVABI
                    ]:
                        haciz = self._haciz_analiz(evrak)
                        if haciz:
                            sonuc.hacizler.append(haciz)
                            # NOT: Bloke tutarı BURADA toplanmıyor!
                            # Bloke hesaplaması haciz_ihbar_analyzer'da yapılıyor.
                            # Çift sayım ve yanlış pozitif önlemek için
                            # tek kaynak prensibi (single source of truth) uygulanıyor.
            
            # Genel tebligat durumunu belirle
            sonuc.tebligat_durumu = self._genel_tebligat_durumu(sonuc.tebligatlar)
            
            # Kritik tarihleri hesapla
            sonuc.kritik_tarihler = self._kritik_tarihler_hesapla(sonuc)
            
            # Aksiyonları belirle
            sonuc.aksiyonlar = self._aksiyonlar_belirle(sonuc)
            
            # Özet rapor oluştur
            sonuc.ozet_rapor = self._ozet_rapor_olustur(sonuc)
        
        finally:
            # Temizlik
            if self.temp_dir and os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir, ignore_errors=True)
                self.temp_dir = None
        
        return sonuc
    
    def _zip_ac(self, zip_yolu: str) -> List[str]:
        """ZIP'i aç ve dosya listesi döndür"""
        dosyalar = []
        
        try:
            # RAR desteği için rarfile kontrolü
            if zip_yolu.lower().endswith('.rar'):
                try:
                    import rarfile
                    with rarfile.RarFile(zip_yolu, 'r') as rf:
                        rf.extractall(self.temp_dir)
                except ImportError:
                    print("RAR desteği için: pip install rarfile")
                    return []
            else:
                with zipfile.ZipFile(zip_yolu, 'r') as zf:
                    zf.extractall(self.temp_dir)
            
            # Dosyaları topla
            for root, dirs, files in os.walk(self.temp_dir):
                for f in files:
                    ext = os.path.splitext(f)[1].lower()
                    if ext in ['.pdf', '.udf', '.txt', '.html', '.xml', '.tiff', '.tif', '.jpg', '.png']:
                        dosyalar.append(os.path.join(root, f))
        
        except Exception as e:
            print(f"ZIP açma hatası: {e}")
        
        return dosyalar
    
    def _dosya_analiz(self, dosya_yolu: str) -> Optional[EvrakBilgisi]:
        """Tek dosyayı analiz et"""
        dosya_adi = os.path.basename(dosya_yolu)
        
        # Metin çıkar
        metin = self._dosya_oku(dosya_yolu)
        
        # Görüntü dosyaları için sadece dosya adından analiz
        ext = os.path.splitext(dosya_yolu)[1].lower()
        if ext in ['.tiff', '.tif', '.jpg', '.png'] and not metin:
            metin = dosya_adi
        
        if not metin:
            return None
        
        # Evrak türü
        evrak_turu = self._evrak_turu_tespit(metin, dosya_adi)
        
        # Tarih
        tarih = self._tarih_bul(metin)
        
        # Özet (ilk 200 karakter)
        ozet = metin[:200].replace('\n', ' ').strip()
        if len(metin) > 200:
            ozet += "..."
        
        return EvrakBilgisi(
            dosya_adi=dosya_adi,
            evrak_turu=evrak_turu,
            tarih=tarih,
            ozet=ozet,
            metin=metin
        )
    
    def _tebligat_analiz(self, evrak: EvrakBilgisi) -> TebligatBilgisi:
        """Tebligat evrakını analiz et"""
        durum = self._tebligat_durumu_tespit(evrak.metin)
        
        return TebligatBilgisi(
            evrak_adi=evrak.dosya_adi,
            tarih=evrak.tarih,
            durum=durum,
            aciklama=evrak.ozet
        )
    
    def _haciz_analiz(self, evrak: EvrakBilgisi) -> Optional[HacizBilgisi]:
        """Haciz evrakını analiz et"""
        haciz_turu = self._haciz_turu_tespit(evrak.metin)
        
        # SADECE banka cevabından ve "bloke" geçen satırlardan tutar al
        tutar = None
        if evrak.evrak_turu == EvrakTuru.BANKA_CEVABI:
            tutar = self._bloke_tutar_bul(evrak.metin)
        # Diğer haciz türlerinden tutar ALMA - bunlar talep tutarları, bloke değil!
        
        # 106/110 süresi sadece araç ve taşınmaz için
        sure = None
        if haciz_turu in ['ARAC', 'TASINMAZ'] and evrak.tarih:
            gecen_gun = (self.bugun - evrak.tarih).days
            sure = max(0, 365 - gecen_gun)  # 1 yıl satış talep süresi
        
        return HacizBilgisi(
            tur=haciz_turu,
            tarih=evrak.tarih,
            tutar=tutar,
            durum="Tespit Edildi",
            sure_106_110=sure
        )
    
    def _genel_tebligat_durumu(self, tebligatlar: List[TebligatBilgisi]) -> TebligatDurumu:
        """Genel tebligat durumunu belirle"""
        if not tebligatlar:
            return TebligatDurumu.BILINMIYOR
        
        # En son tebligata bak
        son_tebligat = max(tebligatlar, key=lambda t: t.tarih or datetime.min)
        return son_tebligat.durum
    
    def _kritik_tarihler_hesapla(self, sonuc: DosyaAnalizSonucu) -> List[Dict]:
        """Kritik tarihleri hesapla"""
        tarihler = []
        
        for haciz in sonuc.hacizler:
            if haciz.sure_106_110 is not None and haciz.sure_106_110 <= 90:
                oncelik = "KRİTİK" if haciz.sure_106_110 <= 30 else "UYARI"
                tarihler.append({
                    'tur': f"{haciz.tur} Haczi",
                    'aciklama': f"Satış talep süresi: {haciz.sure_106_110} gün kaldı",
                    'son_tarih': haciz.tarih + timedelta(days=365) if haciz.tarih else None,
                    'oncelik': oncelik
                })
        
        return tarihler
    
    def _aksiyonlar_belirle(self, sonuc: DosyaAnalizSonucu) -> List[AksiyonOnerisi]:
        """Yapılması gereken aksiyonları belirle"""
        aksiyonlar = []
        
        # Tebligat aksiyonları
        bila_tebligatlar = [t for t in sonuc.tebligatlar if t.durum == TebligatDurumu.BILA]
        if bila_tebligatlar:
            aksiyonlar.append(AksiyonOnerisi(
                oncelik=IslemDurumu.KRITIK,
                baslik="Bila Tebligat - Yeniden Tebligat Gerekli",
                aciklama=f"{len(bila_tebligatlar)} adet bila tebligat var. MERNİS/MERSİS adresi kontrol edilmeli.",
            ))
        
        # 21/35 tebligat kontrolü
        tebligat_21_35 = [t for t in sonuc.tebligatlar if t.durum in [TebligatDurumu.TEBLIGAT_21, TebligatDurumu.TEBLIGAT_35]]
        if tebligat_21_35:
            aksiyonlar.append(AksiyonOnerisi(
                oncelik=IslemDurumu.BILGI,
                baslik="21/35 Tebligat Yapılmış",
                aciklama=f"{len(tebligat_21_35)} adet 21/35 madde tebligatı mevcut.",
            ))
        
        # Haciz süre aksiyonları
        for haciz in sonuc.hacizler:
            if haciz.sure_106_110 is not None:
                if haciz.sure_106_110 <= 30:
                    aksiyonlar.append(AksiyonOnerisi(
                        oncelik=IslemDurumu.KRITIK,
                        baslik=f"{haciz.tur} - SATIŞ TALEP SÜRESİ KRİTİK!",
                        aciklama=f"Kalan süre: {haciz.sure_106_110} gün. ACİL satış talep edilmeli!",
                        son_tarih=haciz.tarih + timedelta(days=365) if haciz.tarih else None
                    ))
                elif haciz.sure_106_110 <= 90:
                    aksiyonlar.append(AksiyonOnerisi(
                        oncelik=IslemDurumu.UYARI,
                        baslik=f"{haciz.tur} - Satış Talep Süresi Yaklaşıyor",
                        aciklama=f"Kalan süre: {haciz.sure_106_110} gün.",
                        son_tarih=haciz.tarih + timedelta(days=365) if haciz.tarih else None
                    ))
        
        # Banka cevabı varsa kullanıcıyı yönlendir
        banka_cevaplari = [e for e in sonuc.evraklar if e.evrak_turu == EvrakTuru.BANKA_CEVABI]
        if banka_cevaplari:
            aksiyonlar.append(AksiyonOnerisi(
                oncelik=IslemDurumu.BILGI,
                baslik="Banka Cevapları Mevcut",
                aciklama=f"{len(banka_cevaplari)} adet banka cevabı var. Detaylı bloke analizi için '89/1-2-3 Haciz İhbar Analizi' modülünü kullanın.",
            ))
        
        # Önceliğe göre sırala
        oncelik_sirasi = {
            IslemDurumu.KRITIK: 0,
            IslemDurumu.UYARI: 1,
            IslemDurumu.BEKLEMEDE: 2,
            IslemDurumu.BILGI: 3,
            IslemDurumu.TAMAMLANDI: 4
        }
        aksiyonlar.sort(key=lambda a: oncelik_sirasi.get(a.oncelik, 99))
        
        return aksiyonlar
    
    def _ozet_rapor_olustur(self, sonuc: DosyaAnalizSonucu) -> str:
        """Özet rapor oluştur"""
        rapor = []
        
        rapor.append("=" * 60)
        rapor.append("📋 UYAP DOSYA ANALİZ RAPORU")
        rapor.append(f"Tarih: {self.bugun.strftime('%d.%m.%Y %H:%M')}")
        rapor.append("=" * 60)
        
        # Genel özet
        rapor.append("\n📊 GENEL ÖZET")
        rapor.append("-" * 40)
        rapor.append(f"  Toplam Evrak: {sonuc.toplam_evrak}")
        rapor.append(f"  Analiz Edilen: {len(sonuc.evraklar)}")
        rapor.append(f"  Tebligat Sayısı: {len(sonuc.tebligatlar)}")
        rapor.append(f"  Haciz Sayısı: {len(sonuc.hacizler)}")
        banka_cevap_sayisi = sonuc.evrak_dagilimi.get('Banka Cevabı', 0)
        if banka_cevap_sayisi > 0:
            rapor.append(f"  🏦 Banka Cevabı: {banka_cevap_sayisi} (detay için Haciz İhbar modülü)")
        
        # Evrak dağılımı
        if sonuc.evrak_dagilimi:
            rapor.append("\n📁 EVRAK DAĞILIMI")
            rapor.append("-" * 40)
            for tur, sayi in sorted(sonuc.evrak_dagilimi.items(), key=lambda x: -x[1]):
                rapor.append(f"  {tur}: {sayi}")
        
        # Tebligat durumu
        rapor.append(f"\n📬 TEBLİGAT DURUMU: {sonuc.tebligat_durumu.value}")
        
        # Kritik tarihler
        if sonuc.kritik_tarihler:
            rapor.append("\n⏰ KRİTİK TARİHLER")
            rapor.append("-" * 40)
            for t in sonuc.kritik_tarihler:
                rapor.append(f"  🔴 {t['tur']}: {t['aciklama']}")
        
        # Aksiyonlar
        if sonuc.aksiyonlar:
            rapor.append("\n✅ YAPILACAKLAR")
            rapor.append("-" * 40)
            for a in sonuc.aksiyonlar:
                rapor.append(f"  {a.oncelik.value} {a.baslik}")
                rapor.append(f"     → {a.aciklama}")
        
        rapor.append("\n" + "=" * 60)
        rapor.append("Bu rapor otomatik oluşturulmuştur.")
        
        return "\n".join(rapor)
    
    # ========================================================================
    # EXCEL ÇIKTI
    # ========================================================================
    
    def excel_olustur(self, sonuc: DosyaAnalizSonucu, cikti_yolu: str) -> str:
        """Analiz sonucundan Excel oluştur"""
        if not PANDAS_OK:
            return ""
        
        with pd.ExcelWriter(cikti_yolu, engine='openpyxl') as writer:
            # Sayfa 1: Özet
            banka_cevap_sayisi = sonuc.evrak_dagilimi.get('Banka Cevabı', 0)
            ozet_data = {
                'Metrik': ['Toplam Evrak', 'Analiz Edilen', 'Tebligat', 'Haciz', 'Banka Cevabı'],
                'Değer': [sonuc.toplam_evrak, len(sonuc.evraklar), len(sonuc.tebligatlar), 
                         len(sonuc.hacizler), f"{banka_cevap_sayisi} (detay için Haciz İhbar modülü)"]
            }
            pd.DataFrame(ozet_data).to_excel(writer, sheet_name='Özet', index=False)
            
            # Sayfa 2: Evraklar
            evrak_data = [{
                'Dosya Adı': e.dosya_adi,
                'Evrak Türü': e.evrak_turu.value,
                'Tarih': e.tarih.strftime('%d.%m.%Y') if e.tarih else '',
                'Özet': e.ozet[:100]
            } for e in sonuc.evraklar]
            pd.DataFrame(evrak_data).to_excel(writer, sheet_name='Evraklar', index=False)
            
            # Sayfa 3: Tebligatlar
            if sonuc.tebligatlar:
                tebligat_data = [{
                    'Evrak': t.evrak_adi,
                    'Tarih': t.tarih.strftime('%d.%m.%Y') if t.tarih else '',
                    'Durum': t.durum.value,
                    'Açıklama': t.aciklama[:100]
                } for t in sonuc.tebligatlar]
                pd.DataFrame(tebligat_data).to_excel(writer, sheet_name='Tebligatlar', index=False)
            
            # Sayfa 4: Hacizler
            if sonuc.hacizler:
                haciz_data = [{
                    'Tür': h.tur,
                    'Tarih': h.tarih.strftime('%d.%m.%Y') if h.tarih else '',
                    'Tutar': f"{h.tutar:,.2f} TL" if h.tutar else '',
                    'Kalan Süre (gün)': h.sure_106_110 if h.sure_106_110 else '-'
                } for h in sonuc.hacizler]
                pd.DataFrame(haciz_data).to_excel(writer, sheet_name='Hacizler', index=False)
            
            # Sayfa 5: Aksiyonlar
            if sonuc.aksiyonlar:
                aksiyon_data = [{
                    'Öncelik': a.oncelik.value,
                    'Başlık': a.baslik,
                    'Açıklama': a.aciklama,
                    'Son Tarih': a.son_tarih.strftime('%d.%m.%Y') if a.son_tarih else ''
                } for a in sonuc.aksiyonlar]
                pd.DataFrame(aksiyon_data).to_excel(writer, sheet_name='Aksiyonlar', index=False)
        
        return cikti_yolu


# ============================================================================
# TEST
# ============================================================================

if __name__ == "__main__":
    print("=" * 50)
    print("UYAP DOSYA ANALİZ MOTORU TEST")
    print("=" * 50)
    
    print(f"\n📦 Kütüphane Durumu:")
    print(f"  pdfplumber: {'✅' if PDF_OK else '❌'}")
    print(f"  pandas: {'✅' if PANDAS_OK else '❌'}")
    
    print("\n✅ Analyzer kullanılabilir!")
    print("\nKullanım:")
    print("  analyzer = UYAPDosyaAnalyzer()")
    print("  sonuc = analyzer.analiz_et('dosya.zip')")
    print("  analyzer.excel_olustur(sonuc, 'rapor.xlsx')")
