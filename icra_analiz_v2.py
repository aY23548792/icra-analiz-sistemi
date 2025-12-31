#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
İCRA DOSYA ANALİZ SİSTEMİ v2.0
==============================
UYAP dosyalarından kapsamlı icra hukuku analizi

MODÜLLER:
1. Dosya Dönüştürücü (ZIP/RAR → Düzgün PDF + Rapor)
2. Takip Türü Tespiti (İlamsız/Kambiyo/İlamlı)
3. Tebligat Analizi (Bila/21/35/Mernis/Mersis)
4. Haciz Analizi (89/1, Araç, Taşınmaz, Menkul, SGK)
5. Takyidat Parser (Lien Tracking)
6. Süre Takibi (106/110, İtiraz süreleri)
7. Satış Süreci Kontrolü

ÖNEMLİ KURALLAR:
- 89/1 Banka hacizlerinde 106/110 süre takibi YOK
- Kambiyo'da itiraz (5 gün) takibi DURDURMAZ
- İlamsız'da itiraz (7 gün) takibi DURDURUR
- Ev adresine menkul hacizde İcra Hukuk Mahkemesi yetkisi gerekli
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
from pathlib import Path
import xml.etree.ElementTree as ET
import io

# PDF işleme
try:
    import pdfplumber
    PDF_READ_AVAILABLE = True
except ImportError:
    PDF_READ_AVAILABLE = False

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    PDF_WRITE_AVAILABLE = True
except ImportError:
    PDF_WRITE_AVAILABLE = False

try:
    from PyPDF2 import PdfMerger, PdfReader
    PDF_MERGE_AVAILABLE = True
except ImportError:
    PDF_MERGE_AVAILABLE = False

try:
    from PIL import Image
    TIFF_SUPPORT = True
except ImportError:
    TIFF_SUPPORT = False

# RAR desteği
try:
    import rarfile
    RAR_SUPPORT = True
except ImportError:
    RAR_SUPPORT = False


# ============================================================================
# ENUMLAR
# ============================================================================

class TakipTuru(Enum):
    ILAMSIZ = "İlamsız İcra (Örnek 7)"
    KAMBIYO = "Kambiyo Senetlerine Özgü (Örnek 10)"
    ILAMLI = "İlamlı İcra (Örnek 4-5)"
    REHIN = "Rehnin Paraya Çevrilmesi"
    IFLAS = "İflas Takibi"
    BILINMIYOR = "Tespit Edilemedi"


class TebligatDurumu(Enum):
    TEBLIG_EDILDI = "✅ Tebliğ Edildi"
    BILA = "⚠️ Bila (Tebliğ Edilemedi)"
    MADDE_21 = "📍 Madde 21 (Tebliğ İmkansızlığı)"
    MADDE_35 = "📍 Madde 35 (Adres Değişikliği)"
    MERNIS = "🏠 Mernis Adresine Tebliğ"
    MERSIS = "🏢 Mersis Adresine Tebliğ"
    ILANEN = "📰 İlanen Tebliğ"
    BEKLENIYOR = "⏳ Tebligat Bekleniyor"
    BILINMIYOR = "❓ Tespit Edilemedi"


class HacizTuru(Enum):
    BANKA_89_1 = "🏦 Banka Haczi (89/1)"
    BANKA_89_2 = "🏦 Banka 2. İhbar (89/2)"
    BANKA_89_3 = "🏦 Banka 3. İhbar (89/3)"
    SGK_MAAS = "💼 SGK Maaş Haczi"
    ARAC = "🚗 Araç Haczi"
    TASINMAZ = "🏠 Taşınmaz Haczi"
    MENKUL_ESASTAN = "📦 Menkul Haciz (Esastan)"
    MENKUL_TALIMAT = "📦 Menkul Haciz (Talimat)"
    POSTA_CEKI = "📮 Posta Çeki Haczi"
    ALACAKLI_DOSYA = "📁 Alacaklı Olduğu Dosya Haczi"
    E_HACIZ = "💻 E-Haciz"
    DIGER = "📋 Diğer Haciz"


class MulkiyetTipi(Enum):
    TAM = "Tam Mülkiyet"
    PAYLI_MUSTEREK = "Paylı (Müşterek) Mülkiyet"
    ISTIRAK_ELBIRLIGI = "İştirak (Elbirliği) - Miras"
    BILINMIYOR = "Tespit Edilemedi"


class EvrakKategorisi(Enum):
    ODEME_EMRI = "Ödeme Emri"
    ICRA_EMRI = "İcra Emri"
    TEBLIGAT_MAZBATA = "Tebligat Mazbatası"
    HACIZ_MUHTIRASI = "Haciz Müzekkeresi/Mühtırası"
    HACIZ_TUTANAGI = "Haciz Tutanağı"
    BANKA_89_IHBAR = "89 Haciz İhbarnamesi"
    BANKA_CEVAP = "Banka Cevabı"
    KIYMET_TAKDIRI = "Kıymet Takdiri Raporu"
    SATIS_ILANI = "Satış İlanı"
    TAKYIDAT = "Takyidat Belgesi"
    M103_DAVETIYE = "103 Davetiyesi"
    MAHKEME_KARARI = "Mahkeme Kararı"
    ITIRAZ_DILEKCE = "İtiraz Dilekçesi"
    TALEP_DILEKCE = "Talep/Dilekçe"
    VEKALETNAME = "Vekaletname"
    BILIRKISI_RAPORU = "Bilirkişi Raporu"
    TALIMAT_YAZISI = "Talimat Yazısı"
    DIGER = "Diğer Evrak"


class TasinmazAsama(Enum):
    HACIZ_KONULDU = "1️⃣ Haciz Konuldu"
    M103_TALEP = "2️⃣ 103 Davetiye Talep"
    M103_TEBLIG = "3️⃣ 103 Tebliğ Edildi"
    KIYMET_TALIMAT = "4️⃣ Kıymet Takdiri Talimatı"
    KIYMET_RAPOR = "5️⃣ Kıymet Takdiri Düzenlendi"
    KIYMET_TEBLIG = "6️⃣ Kıymet Takdiri Tebliği"
    KIYMET_KESINLESTI = "7️⃣ Kıymet Takdiri Kesinleşti"
    SATIS_TALEP = "8️⃣ Satış Talep Edildi"
    SATIS_AVANS = "9️⃣ Satış Avansı Yatırıldı"
    SATIS_ILANI = "🔟 Satış İlanı Yapıldı"


# ============================================================================
# VERİ YAPILARI
# ============================================================================

@dataclass
class DosyaDonusumRaporu:
    """Dosya dönüşüm raporu"""
    toplam_klasor: int = 0
    toplam_dosya: int = 0
    udf_sayisi: int = 0
    pdf_sayisi: int = 0
    tiff_sayisi: int = 0
    xml_sayisi: int = 0
    diger_sayisi: int = 0
    basarili_donusum: int = 0
    basarisiz_donusum: int = 0
    hatalar: List[str] = field(default_factory=list)
    cikti_pdf_yolu: Optional[str] = None


@dataclass
class EvrakBilgisi:
    """Parse edilmiş evrak bilgisi"""
    dosya_adi: str
    kategori: EvrakKategorisi
    tarih: Optional[datetime]
    metin: str
    sayfa_sayisi: int = 1
    onem_seviyesi: int = 0  # 0-10


@dataclass
class TebligatKaydi:
    """Tek bir tebligat kaydı"""
    evrak_adi: str
    tip: str  # "Ödeme Emri", "103 Davetiye", "Kıymet Takdiri" vs.
    durum: TebligatDurumu
    tarih: Optional[datetime]
    adres: Optional[str]
    tebellug_eden: Optional[str]
    madde_21_35: bool = False
    ikinci_tebligat_sureti_dondu: bool = False
    aciklama: str = ""


@dataclass
class HacizKaydi:
    """Tek bir haciz kaydı"""
    haciz_turu: HacizTuru
    talep_tarihi: Optional[datetime]
    haciz_tarihi: Optional[datetime]
    hedef: str  # Banka adı, plaka, ada/parsel
    tutar: Optional[float] = None
    esastan_mi: bool = True
    talimat_no: Optional[str] = None
    # Menkul haciz için özel
    adres: Optional[str] = None
    yetki_alindi_mi: Optional[bool] = None  # Ev haczi için
    # Haciz tutanağı
    tutanak_var_mi: bool = False
    tutanak_tarihi: Optional[datetime] = None
    # 106/110 - SADECE Araç ve Taşınmaz için
    dusme_tarihi: Optional[datetime] = None
    kalan_gun: Optional[int] = None
    satis_talep_edildi_mi: bool = False
    satis_avans_yatirildi_mi: bool = False


@dataclass
class TasinmazKaydi:
    """Taşınmaz detay bilgisi"""
    ada: str
    parsel: str
    il: Optional[str] = None
    ilce: Optional[str] = None
    mahalle: Optional[str] = None
    
    # Mülkiyet
    mulkiyet_tipi: MulkiyetTipi = MulkiyetTipi.BILINMIYOR
    borclu_hisse: Optional[str] = None
    diger_malikler: List[Dict] = field(default_factory=list)  # [{isim, tckn, hisse}]
    
    # Haciz
    haciz_tarihi: Optional[datetime] = None
    dusme_tarihi: Optional[datetime] = None
    kalan_gun: Optional[int] = None
    
    # 103 Davetiye
    m103_talep_tarihi: Optional[datetime] = None
    m103_teblig_durumu: Optional[TebligatDurumu] = None
    m103_teblig_tarihi: Optional[datetime] = None
    
    # Kıymet Takdiri
    kiymet_talimat_tarihi: Optional[datetime] = None
    kiymet_talimat_icra_dairesi: Optional[str] = None
    kiymet_rapor_tarihi: Optional[datetime] = None
    kiymet_degeri: Optional[float] = None
    kiymet_teblig_durumlari: List[TebligatKaydi] = field(default_factory=list)
    kiymet_kesinlesti_mi: bool = False
    
    # Satış
    satis_talep_tarihi: Optional[datetime] = None
    satis_avans_yatirildi_mi: bool = False
    satis_ilani_tarihi: Optional[datetime] = None
    
    # Takyidat bilgileri
    ipotek_var_mi: bool = False
    ipotekler: List[Dict] = field(default_factory=list)
    tedbir_var_mi: bool = False
    tedbirler: List[Dict] = field(default_factory=list)
    diger_hacizler: List[Dict] = field(default_factory=list)  # Lien tracking
    
    # Aşama
    mevcut_asama: TasinmazAsama = TasinmazAsama.HACIZ_KONULDU


@dataclass
class ItirazKaydi:
    """İtiraz bilgisi"""
    itiraz_tarihi: Optional[datetime]
    mahkeme: Optional[str]
    esas_no: Optional[str]
    itiraz_eden: Optional[str]
    sonuc: Optional[str]  # "Bekliyor", "Kabul", "Red"
    takibi_durdurur_mu: bool  # İlamsız: Evet, Kambiyo: Hayır


@dataclass
class DosyaAnalizSonucu:
    """Tam dosya analiz sonucu"""
    # Genel
    dosya_no: Optional[str] = None
    takip_turu: TakipTuru = TakipTuru.BILINMIYOR
    alacakli: Optional[str] = None
    borclu: Optional[str] = None
    borclu_tckn: Optional[str] = None
    borclu_tipi: str = "Gerçek Kişi"  # veya "Tüzel Kişi"
    toplam_alacak: Optional[float] = None
    
    # Dosya dönüşüm
    donusum_raporu: Optional[DosyaDonusumRaporu] = None
    
    # Evraklar
    evraklar: List[EvrakBilgisi] = field(default_factory=list)
    
    # Ödeme Emri / Kesinleşme
    odeme_emri_tebligati: Optional[TebligatKaydi] = None
    itiraz_suresi_gun: int = 7
    itiraz_bitis_tarihi: Optional[datetime] = None
    itiraz_suresi_doldu_mu: bool = False
    kesinlesti_mi: bool = False
    
    # İtiraz
    itiraz: Optional[ItirazKaydi] = None
    
    # Tüm tebligatlar
    tum_tebligatlar: List[TebligatKaydi] = field(default_factory=list)
    
    # Hacizler
    banka_hacizleri: List[HacizKaydi] = field(default_factory=list)
    sgk_hacizleri: List[HacizKaydi] = field(default_factory=list)
    arac_hacizleri: List[HacizKaydi] = field(default_factory=list)
    tasinmaz_hacizleri: List[HacizKaydi] = field(default_factory=list)
    menkul_hacizleri: List[HacizKaydi] = field(default_factory=list)
    diger_hacizler: List[HacizKaydi] = field(default_factory=list)
    
    # Taşınmaz detayları
    tasinmazlar: List[TasinmazKaydi] = field(default_factory=list)
    
    # Kritik uyarılar
    kritik_uyarilar: List[str] = field(default_factory=list)
    oneriler: List[str] = field(default_factory=list)


# ============================================================================
# ANA ANALİZ SINIFI
# ============================================================================

class IcraDosyaAnaliz:
    """İcra dosyası kapsamlı analiz sınıfı"""
    
    # ========================================================================
    # PATTERN'LAR
    # ========================================================================
    
    TAKIP_PATTERNS = {
        TakipTuru.KAMBIYO: [
            r'kambiyo', r'örnek\s*(?:no\s*)?:?\s*10', r'çek', r'senet', r'bono',
            r'poliçe', r'emre\s*muharrer', r'kambiyo\s*senet'
        ],
        TakipTuru.ILAMSIZ: [
            r'ilamsız', r'örnek\s*(?:no\s*)?:?\s*7', r'genel\s*haciz\s*yolu',
            r'ödeme\s*emri.*7'
        ],
        TakipTuru.ILAMLI: [
            r'ilamlı', r'örnek\s*(?:no\s*)?:?\s*4', r'icra\s*emri',
            r'mahkeme\s*kararı.*icra', r'örnek\s*4-5'
        ],
        TakipTuru.REHIN: [
            r'rehin', r'ipotek.*paraya', r'taşınır\s*rehni', r'taşınmaz\s*rehni'
        ],
        TakipTuru.IFLAS: [
            r'iflas', r'konkordato', r'iflas\s*takip'
        ]
    }
    
    TEBLIGAT_PATTERNS = {
        TebligatDurumu.BILA: [
            r'bila', r'tebliğ\s*edilemedi', r'bulunamadı', r'adreste\s*yok',
            r'tanınmıyor', r'taşınmış', r'adres\s*yetersiz'
        ],
        TebligatDurumu.MADDE_21: [
            r'madde\s*21', r'21\.\s*madde', r'tebliğ\s*imkansızlığı',
            r'kapıya\s*yapıştır', r'komşu.*muhtar', r'21/1', r'21/2'
        ],
        TebligatDurumu.MADDE_35: [
            r'madde\s*35', r'35\.\s*madde', r'adres\s*değişikliği',
            r'eski\s*adres', r'yeni\s*adres\s*bildirilmemiş'
        ],
        TebligatDurumu.MERNIS: [
            r'mernis', r'nüfus\s*müdürlüğü.*adres', r'adres\s*kayıt\s*sistemi',
            r'yerleşim\s*yeri'
        ],
        TebligatDurumu.MERSIS: [
            r'mersis', r'ticaret\s*sicil.*adres', r'şirket.*kayıtlı\s*adres'
        ],
        TebligatDurumu.ILANEN: [
            r'ilanen', r'gazete.*ilan', r'resmi\s*gazete'
        ],
        TebligatDurumu.TEBLIG_EDILDI: [
            r'tebliğ\s*edildi', r'tebellüğ', r'imza.*teslim', r'elden\s*tebliğ',
            r'bizzat', r'usulüne\s*uygun'
        ]
    }
    
    EVRAK_PATTERNS = {
        EvrakKategorisi.ODEME_EMRI: [
            r'ödeme\s*emri', r'örnek\s*7', r'örnek\s*10'
        ],
        EvrakKategorisi.ICRA_EMRI: [
            r'icra\s*emri', r'örnek\s*4', r'örnek\s*5'
        ],
        EvrakKategorisi.TEBLIGAT_MAZBATA: [
            r'tebligat', r'mazbata', r'tebliğ\s*belgesi'
        ],
        EvrakKategorisi.HACIZ_MUHTIRASI: [
            r'haciz\s*müzekkeresi', r'haciz\s*mühtırası', r'haciz\s*ihbarname'
        ],
        EvrakKategorisi.HACIZ_TUTANAGI: [
            r'haciz\s*tutanağı', r'haciz\s*zaptı'
        ],
        EvrakKategorisi.BANKA_89_IHBAR: [
            r'89.*ihbar', r'haciz\s*ihbarnamesi', r'89/1', r'89/2', r'89/3'
        ],
        EvrakKategorisi.BANKA_CEVAP: [
            r'banka.*cevap', r'cevap.*banka', r'hesap\s*bilgi'
        ],
        EvrakKategorisi.KIYMET_TAKDIRI: [
            r'kıymet\s*takdir', r'değer\s*tespit', r'bilirkişi.*değer'
        ],
        EvrakKategorisi.SATIS_ILANI: [
            r'satış\s*ilanı', r'ihale', r'açık\s*artırma'
        ],
        EvrakKategorisi.TAKYIDAT: [
            r'takyidat', r'tapu\s*kaydı', r'şerhler', r'beyanlar'
        ],
        EvrakKategorisi.M103_DAVETIYE: [
            r'103', r'davetiye', r'satış\s*hazırlık'
        ],
        EvrakKategorisi.MAHKEME_KARARI: [
            r'mahkeme\s*kararı', r'hüküm', r'karar\s*no'
        ],
        EvrakKategorisi.ITIRAZ_DILEKCE: [
            r'itiraz', r'şikayet', r'iptali\s*istemi'
        ],
        EvrakKategorisi.TALIMAT_YAZISI: [
            r'talimat', r'istinabe', r'yetki\s*belgesi'
        ]
    }
    
    HACIZ_PATTERNS = {
        HacizTuru.BANKA_89_1: [r'89/1', r'89\s*/\s*1', r'birinci\s*haciz\s*ihbar', r'1\.\s*haciz\s*ihbar'],
        HacizTuru.BANKA_89_2: [r'89/2', r'89\s*/\s*2', r'ikinci\s*haciz\s*ihbar', r'2\.\s*haciz\s*ihbar'],
        HacizTuru.BANKA_89_3: [r'89/3', r'89\s*/\s*3', r'üçüncü\s*haciz\s*ihbar', r'3\.\s*haciz\s*ihbar'],
        HacizTuru.SGK_MAAS: [r'sgk', r'maaş\s*haciz', r'355', r'emekli.*haciz', r'işveren.*haciz'],
        HacizTuru.ARAC: [r'araç\s*haciz', r'plaka', r'trafik.*şerh', r'emniyet.*haciz', r'araç.*yakalama'],
        HacizTuru.TASINMAZ: [r'taşınmaz\s*haciz', r'tapu.*haciz', r'gayrimenkul.*haciz', r'tapuya\s*şerh'],
        HacizTuru.POSTA_CEKI: [r'posta\s*çeki', r'ptt.*haciz'],
        HacizTuru.ALACAKLI_DOSYA: [r'alacaklı\s*olduğu', r'3\.\s*şahıs.*alacak'],
        HacizTuru.E_HACIZ: [r'e-haciz', r'elektronik\s*haciz']
    }
    
    MULKIYET_PATTERNS = {
        MulkiyetTipi.ISTIRAK_ELBIRLIGI: [
            r'iştirak', r'elbirliği', r'miras', r'veraset', r'tereke',
            r'muris', r'mirasçı', r'intikal'
        ],
        MulkiyetTipi.PAYLI_MUSTEREK: [
            r'müşterek', r'paylı', r'hisseli', r'\d+/\d+\s*hisse'
        ]
    }
    
    AY_MAP = {
        'ocak': 1, 'şubat': 2, 'mart': 3, 'nisan': 4,
        'mayıs': 5, 'haziran': 6, 'temmuz': 7, 'ağustos': 8,
        'eylül': 9, 'ekim': 10, 'kasım': 11, 'aralık': 12
    }
    
    # Bankalar listesi
    BANKALAR = [
        'ziraat', 'halk', 'vakıf', 'iş bank', 'garanti', 'yapı kredi', 'akbank',
        'qnb', 'finansbank', 'deniz', 'ing', 'hsbc', 'teb', 'şeker', 'anadolu',
        'fibabanka', 'odeabank', 'alternatif', 'burgan', 'turkish', 'icbc', 'bank of china'
    ]
    
    def __init__(self):
        self.bugun = datetime.now()
        self.temp_dir = None
        
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
    
    def tarih_bul(self, metin: str, context: str = None) -> Optional[datetime]:
        """Metinden tarih çıkar"""
        if not metin:
            return None
        bulunan = []
        
        # DD.MM.YYYY veya DD/MM/YYYY
        for match in re.finditer(r'(\d{2})[./](\d{2})[./](\d{4})', metin):
            try:
                g, a, y = int(match.group(1)), int(match.group(2)), int(match.group(3))
                if 1 <= g <= 31 and 1 <= a <= 12 and 1990 <= y <= 2030:
                    tarih = datetime(y, a, g)
                    if context:
                        pos = match.start()
                        ctx_pos = metin.lower().find(context.lower())
                        if ctx_pos != -1 and abs(pos - ctx_pos) < 150:
                            return tarih
                    bulunan.append(tarih)
            except:
                continue
        
        return max(bulunan) if bulunan else None
    
    def tckn_bul(self, metin: str) -> Optional[str]:
        """11 haneli TCKN bul"""
        if not metin:
            return None
        match = re.search(r'\b(\d{11})\b', metin)
        return match.group(1) if match else None
    
    def vkn_bul(self, metin: str) -> Optional[str]:
        """10 haneli VKN bul"""
        if not metin:
            return None
        match = re.search(r'\b(\d{10})\b', metin)
        return match.group(1) if match else None
    
    def tutar_bul(self, metin: str) -> Optional[float]:
        """Para tutarı bul"""
        if not metin:
            return None
        patterns = [
            r'(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?)\s*(?:TL|₺|TRY)',
            r'(?:toplam|alacak|tutar|miktar)[:\s]*(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?)',
        ]
        for p in patterns:
            match = re.search(p, metin, re.IGNORECASE)
            if match:
                tutar_str = match.group(1).replace('.', '').replace(',', '.')
                try:
                    return float(tutar_str)
                except:
                    continue
        return None
    
    def dosya_no_bul(self, metin: str) -> Optional[str]:
        """Dosya numarası bul"""
        if not metin:
            return None
        patterns = [
            r'(\d{4})\s*/\s*(\d+)\s*(?:Esas|E\.)',
            r'Dosya\s*No\s*:?\s*(\d{4}/\d+)',
            r'Esas\s*No\s*:?\s*(\d{4}/\d+)',
        ]
        for p in patterns:
            match = re.search(p, metin, re.IGNORECASE)
            if match:
                # Grupları birleştir
                groups = match.groups()
                if len(groups) == 2 and groups[0].isdigit() and groups[1].isdigit():
                    return f"{groups[0]}/{groups[1]}"
                return groups[0] if groups[0] else match.group(0)
        
        # Basit pattern
        match = re.search(r'(\d{4}/\d+)', metin)
        return match.group(1) if match else None
    
    def plaka_bul(self, metin: str) -> List[str]:
        """Araç plakası bul"""
        if not metin:
            return []
        pattern = r'\b(\d{2}\s*[A-Z]{1,3}\s*\d{1,4})\b'
        matches = re.findall(pattern, metin.upper())
        return list(set([m.replace(' ', '') for m in matches]))
    
    def ada_parsel_bul(self, metin: str) -> List[Tuple[str, str]]:
        """Ada ve parsel numaralarını bul"""
        if not metin:
            return []
        results = []
        pattern = r'(\d+)\s*ada\s*(\d+)\s*parsel'
        for match in re.finditer(pattern, metin.lower()):
            results.append((match.group(1), match.group(2)))
        return results
    
    def banka_adi_bul(self, metin: str) -> Optional[str]:
        """Banka adı bul"""
        if not metin:
            return None
        metin_lower = metin.lower()
        for banka in self.BANKALAR:
            if banka in metin_lower:
                return banka.title() + " Bankası"
        return None
    
    def isim_bul(self, metin: str, context: str = "borçlu") -> Optional[str]:
        """İsim bul (borçlu veya alacaklı)"""
        if not metin:
            return None
        pattern = rf'{context}\s*:?\s*([A-ZÇĞİÖŞÜa-zçğıöşü\s]+?)(?:\d|T\.C\.|TCKN|$|\n)'
        match = re.search(pattern, metin, re.IGNORECASE)
        if match:
            isim = match.group(1).strip()
            if len(isim) > 3 and len(isim) < 100:
                return isim
        return None
    
    # ========================================================================
    # DOSYA DÖNÜŞTÜRME
    # ========================================================================
    
    def arsiv_ac(self, dosya_yolu: str) -> Tuple[str, List[str]]:
        """ZIP veya RAR arşivini aç"""
        self.temp_dir = tempfile.mkdtemp(prefix="icra_analiz_")
        dosyalar = []
        
        try:
            if dosya_yolu.lower().endswith('.zip'):
                with zipfile.ZipFile(dosya_yolu, 'r') as zf:
                    zf.extractall(self.temp_dir)
                    dosyalar = zf.namelist()
            elif dosya_yolu.lower().endswith('.rar') and RAR_SUPPORT:
                with rarfile.RarFile(dosya_yolu, 'r') as rf:
                    rf.extractall(self.temp_dir)
                    dosyalar = rf.namelist()
            else:
                raise ValueError(f"Desteklenmeyen format: {dosya_yolu}")
        except Exception as e:
            raise Exception(f"Arşiv açma hatası: {str(e)}")
        
        return self.temp_dir, dosyalar
    
    def udf_oku(self, dosya_yolu: str) -> str:
        """UDF dosyasından metin çıkar"""
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
                                    if elem.text:
                                        metin += elem.text + " "
                            except:
                                metin += content
        except:
            try:
                with open(dosya_yolu, 'r', encoding='utf-8', errors='ignore') as f:
                    metin = f.read()
            except:
                pass
        return metin.strip()
    
    def pdf_oku(self, dosya_yolu: str) -> str:
        """PDF'den metin çıkar"""
        metin = ""
        try:
            if PDF_READ_AVAILABLE:
                import pdfplumber
                with pdfplumber.open(dosya_yolu) as pdf:
                    for page in pdf.pages:
                        text = page.extract_text()
                        if text:
                            metin += text + "\n"
        except Exception as e:
            metin = f"[PDF okuma hatası: {str(e)}]"
        return metin.strip()
    
    def dosya_donustur_ve_raporla(self, arsiv_yolu: str) -> DosyaDonusumRaporu:
        """Arşivi aç, dosyaları say ve raporla"""
        rapor = DosyaDonusumRaporu()
        
        try:
            temp_dir, dosya_listesi = self.arsiv_ac(arsiv_yolu)
            rapor.toplam_dosya = len(dosya_listesi)
            
            # Klasör sayısı
            klasorler = set()
            for d in dosya_listesi:
                parts = d.split('/')
                if len(parts) > 1:
                    klasorler.add('/'.join(parts[:-1]))
            rapor.toplam_klasor = len(klasorler)
            
            # Dosya türlerini say
            for dosya in dosya_listesi:
                ext = os.path.splitext(dosya)[1].lower()
                if ext == '.udf':
                    rapor.udf_sayisi += 1
                elif ext == '.pdf':
                    rapor.pdf_sayisi += 1
                elif ext in ['.tiff', '.tif']:
                    rapor.tiff_sayisi += 1
                elif ext == '.xml':
                    rapor.xml_sayisi += 1
                else:
                    rapor.diger_sayisi += 1
            
            # Dönüşüm işlemleri burada yapılacak...
            rapor.basarili_donusum = rapor.udf_sayisi + rapor.pdf_sayisi + rapor.tiff_sayisi
            
        except Exception as e:
            rapor.hatalar.append(str(e))
            rapor.basarisiz_donusum = rapor.toplam_dosya
        
        return rapor
    
    # ========================================================================
    # TAKİP TÜRÜ TESPİTİ
    # ========================================================================
    
    def takip_turu_tespit(self, metin: str) -> TakipTuru:
        """Takip türünü tespit et"""
        for takip_turu, patterns in self.TAKIP_PATTERNS.items():
            if self.pattern_ara(metin, patterns):
                return takip_turu
        return TakipTuru.BILINMIYOR
    
    # ========================================================================
    # TEBLİGAT ANALİZİ
    # ========================================================================
    
    def tebligat_durumu_tespit(self, metin: str) -> TebligatDurumu:
        """Tebligat durumunu tespit et"""
        for durum, patterns in self.TEBLIGAT_PATTERNS.items():
            if self.pattern_ara(metin, patterns):
                return durum
        return TebligatDurumu.BILINMIYOR
    
    def tebligat_analiz(self, metin: str, evrak_adi: str, tip: str = "Genel") -> TebligatKaydi:
        """Tek bir tebligat evrakını analiz et"""
        durum = self.tebligat_durumu_tespit(metin)
        tarih = self.tarih_bul(metin, context="tebliğ")
        
        # Adres bul
        adres = None
        adres_match = re.search(r'adres[:\s]*([^\n]{10,150})', metin, re.IGNORECASE)
        if adres_match:
            adres = adres_match.group(1).strip()
        
        # Tebellüğ eden
        tebellug = None
        teb_match = re.search(r'tebellüğ\s*eden[:\s]*([^\n]+)', metin, re.IGNORECASE)
        if teb_match:
            tebellug = teb_match.group(1).strip()
        
        # 21/35 kontrolü
        madde_21_35 = durum in [TebligatDurumu.MADDE_21, TebligatDurumu.MADDE_35]
        
        # İkinci tebligat sureti dönmüş mü?
        ikinci_sureti = self.pattern_ara(metin, [r'ikinci\s*suret', r'2\.\s*suret', r'suret.*dön'])
        
        # Açıklama oluştur
        aciklama = self._tebligat_aciklama_olustur(durum, tarih, madde_21_35)
        
        return TebligatKaydi(
            evrak_adi=evrak_adi,
            tip=tip,
            durum=durum,
            tarih=tarih,
            adres=adres,
            tebellug_eden=tebellug,
            madde_21_35=madde_21_35,
            ikinci_tebligat_sureti_dondu=ikinci_sureti,
            aciklama=aciklama
        )
    
    def _tebligat_aciklama_olustur(self, durum: TebligatDurumu, tarih: datetime, madde_21_35: bool) -> str:
        """Tebligat için açıklama oluştur"""
        if durum == TebligatDurumu.BILA:
            return "⚠️ Bila - Mernis/Mersis adresine 21 veya 35 ile yeniden tebligat gerekli"
        elif durum == TebligatDurumu.MADDE_21:
            return "✅ Madde 21 uygulandı - Tebliğ imkansızlığı (komşu/muhtar)"
        elif durum == TebligatDurumu.MADDE_35:
            return "✅ Madde 35 uygulandı - Adres değişikliği bildirmeme"
        elif durum == TebligatDurumu.TEBLIG_EDILDI:
            tarih_str = tarih.strftime('%d.%m.%Y') if tarih else ""
            return f"✅ Usulüne uygun tebliğ edildi {tarih_str}"
        elif durum == TebligatDurumu.MERNIS:
            return "🏠 Mernis adresine tebliğ"
        elif durum == TebligatDurumu.MERSIS:
            return "🏢 Mersis adresine tebliğ (Tüzel kişi)"
        else:
            return durum.value
    
    def tebligat_zinciri_kontrol(self, tebligatlar: List[TebligatKaydi], tip_filtre: str = None) -> Tuple[bool, str]:
        """
        Tebligat zincirini kontrol et
        Returns: (kesinlesti_mi, aciklama)
        """
        # Filtreleme
        if tip_filtre:
            tebligatlar = [t for t in tebligatlar if tip_filtre.lower() in t.tip.lower()]
        
        if not tebligatlar:
            return False, "⚠️ Tebligat kaydı bulunamadı"
        
        # Başarılı tebligat var mı?
        basarili = [t for t in tebligatlar if t.durum == TebligatDurumu.TEBLIG_EDILDI]
        madde_21_35 = [t for t in tebligatlar if t.madde_21_35]
        bila = [t for t in tebligatlar if t.durum == TebligatDurumu.BILA]
        
        if basarili:
            son = basarili[-1]
            return True, f"✅ Tebliğ kesinleşti - {son.tarih.strftime('%d.%m.%Y') if son.tarih else ''}"
        
        if madde_21_35:
            return True, "✅ Madde 21/35 ile tebliğ yapılmış"
        
        if bila:
            sureti_dondu = any(t.ikinci_tebligat_sureti_dondu for t in tebligatlar)
            if sureti_dondu:
                return True, "✅ Bila sonrası ikinci tebligat sureti dönmüş"
            return False, "⚠️ Bila tebligat var - Mernis/Mersis'e 21/35 ile yeniden tebligat gerekli!"
        
        return False, "⚠️ Tebligat durumu belirsiz"
    
    # ========================================================================
    # HACİZ ANALİZİ
    # ========================================================================
    
    def haciz_turu_tespit(self, metin: str) -> HacizTuru:
        """Haciz türünü tespit et"""
        for haciz_turu, patterns in self.HACIZ_PATTERNS.items():
            if self.pattern_ara(metin, patterns):
                return haciz_turu
        
        # Menkul haciz kontrolü
        if self.pattern_ara(metin, ['menkul', 'ev.*haciz', 'adres.*haciz']):
            if self.pattern_ara(metin, ['talimat', 'istinabe']):
                return HacizTuru.MENKUL_TALIMAT
            return HacizTuru.MENKUL_ESASTAN
        
        return HacizTuru.DIGER
    
    def haciz_analiz(self, metin: str, evrak_adi: str) -> Optional[HacizKaydi]:
        """Tek bir haciz evrakını analiz et"""
        haciz_turu = self.haciz_turu_tespit(metin)
        
        # Gerçekten haciz evrakı mı?
        if haciz_turu == HacizTuru.DIGER:
            if not self.pattern_ara(metin, ['haciz', 'hacze', 'haczedil']):
                return None
        
        talep_tarihi = self.tarih_bul(metin, context="talep")
        haciz_tarihi = self.tarih_bul(metin, context="haciz")
        tutar = self.tutar_bul(metin)
        
        # Hedef bilgisi
        hedef = ""
        if haciz_turu in [HacizTuru.BANKA_89_1, HacizTuru.BANKA_89_2, HacizTuru.BANKA_89_3]:
            hedef = self.banka_adi_bul(metin) or "Banka"
        elif haciz_turu == HacizTuru.ARAC:
            plakalar = self.plaka_bul(metin)
            hedef = ", ".join(plakalar) if plakalar else "Araç"
        elif haciz_turu == HacizTuru.TASINMAZ:
            ada_parseller = self.ada_parsel_bul(metin)
            hedef = ", ".join([f"{a} ada {p} parsel" for a, p in ada_parseller]) if ada_parseller else "Taşınmaz"
        elif haciz_turu == HacizTuru.SGK_MAAS:
            hedef = "SGK Maaş"
        
        # Talimat mı esastan mı?
        esastan = not self.pattern_ara(metin, ['talimat', 'istinabe'])
        talimat_no = None
        if not esastan:
            tal_match = re.search(r'talimat\s*(?:no\s*)?:?\s*(\d{4}/\d+)', metin, re.IGNORECASE)
            talimat_no = tal_match.group(1) if tal_match else None
        
        # Menkul haciz için adres ve yetki kontrolü
        adres = None
        yetki_alindi = None
        if haciz_turu in [HacizTuru.MENKUL_ESASTAN, HacizTuru.MENKUL_TALIMAT]:
            adres_match = re.search(r'adres[:\s]*([^\n]{10,150})', metin, re.IGNORECASE)
            adres = adres_match.group(1).strip() if adres_match else None
            
            # Ev adresi ise yetki kontrolü
            if adres and self.pattern_ara(metin, ['konut', 'ev', 'mesken', 'ikametgah']):
                yetki_alindi = self.pattern_ara(metin, ['yetki', 'icra\s*hukuk\s*mahkeme', 'izin'])
        
        # Haciz tutanağı kontrolü
        tutanak_var = self.pattern_ara(metin, ['tutanak', 'zapt'])
        tutanak_tarihi = self.tarih_bul(metin, context="tutanak") if tutanak_var else None
        
        # 106/110 süre hesaplama - SADECE Araç ve Taşınmaz için
        dusme_tarihi = None
        kalan_gun = None
        if haciz_turu in [HacizTuru.ARAC, HacizTuru.TASINMAZ] and haciz_tarihi:
            dusme_tarihi = haciz_tarihi + timedelta(days=365)
            kalan_gun = (dusme_tarihi - self.bugun).days
        
        # Satış kontrolü
        satis_talep = self.pattern_ara(metin, ['satış\s*talep', 'satışa\s*çıkar'])
        satis_avans = self.pattern_ara(metin, ['avans', 'harç.*yatır'])
        
        return HacizKaydi(
            haciz_turu=haciz_turu,
            talep_tarihi=talep_tarihi,
            haciz_tarihi=haciz_tarihi,
            hedef=hedef,
            tutar=tutar,
            esastan_mi=esastan,
            talimat_no=talimat_no,
            adres=adres,
            yetki_alindi_mi=yetki_alindi,
            tutanak_var_mi=tutanak_var,
            tutanak_tarihi=tutanak_tarihi,
            dusme_tarihi=dusme_tarihi,
            kalan_gun=kalan_gun,
            satis_talep_edildi_mi=satis_talep,
            satis_avans_yatirildi_mi=satis_avans
        )
    
    # ========================================================================
    # TAŞINMAZ ve TAKYİDAT ANALİZİ
    # ========================================================================
    
    def mulkiyet_tipi_tespit(self, metin: str) -> MulkiyetTipi:
        """Mülkiyet tipini tespit et"""
        for tip, patterns in self.MULKIYET_PATTERNS.items():
            if self.pattern_ara(metin, patterns):
                return tip
        
        # Tam mülkiyet kontrolü
        if self.pattern_ara(metin, ['tam\s*mülkiyet', 'tamamı', '1/1']):
            return MulkiyetTipi.TAM
        
        return MulkiyetTipi.BILINMIYOR
    
    def tasinmaz_analiz(self, metin: str, evrak_adi: str) -> Optional[TasinmazKaydi]:
        """Taşınmaz detay bilgisi çıkar"""
        ada_parseller = self.ada_parsel_bul(metin)
        if not ada_parseller:
            return None
        
        ada, parsel = ada_parseller[0]
        
        return TasinmazKaydi(
            ada=ada,
            parsel=parsel,
            mulkiyet_tipi=self.mulkiyet_tipi_tespit(metin),
            haciz_tarihi=self.tarih_bul(metin, context="haciz")
        )
    
    def takyidat_analiz(self, metin: str) -> Dict:
        """Takyidat belgesini analiz et - Lien Tracking"""
        sonuc = {
            'ada_parsel': None,
            'mulkiyet_tipi': MulkiyetTipi.BILINMIYOR,
            'malikler': [],
            'hacizler': [],
            'ipotekler': [],
            'tedbirler': [],
            'serhler': []
        }
        
        # Ada/Parsel
        ada_parseller = self.ada_parsel_bul(metin)
        if ada_parseller:
            sonuc['ada_parsel'] = ada_parseller[0]
        
        # Mülkiyet tipi
        sonuc['mulkiyet_tipi'] = self.mulkiyet_tipi_tespit(metin)
        
        # Malikler
        malik_satirlari = re.findall(r'malik[:\s]*([^\n]+)', metin, re.IGNORECASE)
        for satir in malik_satirlari:
            tckn = self.tckn_bul(satir)
            hisse_match = re.search(r'(\d+/\d+)', satir)
            sonuc['malikler'].append({
                'isim': satir[:50].strip(),
                'tckn': tckn,
                'hisse': hisse_match.group(1) if hisse_match else None
            })
        
        # Hacizler (Lien Tracking)
        haciz_satirlari = re.findall(r'haciz[^\n]*', metin, re.IGNORECASE)
        for satir in haciz_satirlari:
            dosya_match = re.search(r'(\d{4}/\d+)', satir)
            tarih = self.tarih_bul(satir)
            alacakli_match = re.search(r'alacaklı[:\s]*([^,\n]+)', satir, re.IGNORECASE)
            
            sonuc['hacizler'].append({
                'dosya_no': dosya_match.group(1) if dosya_match else None,
                'tarih': tarih,
                'alacakli': alacakli_match.group(1)[:50] if alacakli_match else None
            })
        
        # İpotekler
        ipotek_satirlari = re.findall(r'ipotek[^\n]*', metin, re.IGNORECASE)
        for satir in ipotek_satirlari:
            tutar = self.tutar_bul(satir)
            lehdar_match = re.search(r'lehine[:\s]*([^,\n]+)', satir, re.IGNORECASE)
            tarih = self.tarih_bul(satir)
            
            sonuc['ipotekler'].append({
                'tutar': tutar,
                'lehdar': lehdar_match.group(1)[:50] if lehdar_match else None,
                'tarih': tarih
            })
        
        # Tedbirler
        tedbir_satirlari = re.findall(r'tedbir[^\n]*', metin, re.IGNORECASE)
        for satir in tedbir_satirlari:
            mahkeme_match = re.search(r'(\d+\.\s*\w+\s*mahkeme)', satir, re.IGNORECASE)
            esas_match = re.search(r'(\d{4}/\d+)', satir)
            
            sonuc['tedbirler'].append({
                'mahkeme': mahkeme_match.group(1) if mahkeme_match else None,
                'esas_no': esas_match.group(1) if esas_match else None
            })
        
        return sonuc
    
    # ========================================================================
    # İTİRAZ ANALİZİ
    # ========================================================================
    
    def itiraz_analiz(self, metin: str, takip_turu: TakipTuru) -> Optional[ItirazKaydi]:
        """İtiraz bilgisi çıkar"""
        if not self.pattern_ara(metin, ['itiraz', 'şikayet']):
            return None
        
        mahkeme_match = re.search(r'(\d+\.\s*(?:icra\s*hukuk|asliye\s*ticaret)\s*mahkeme)', metin, re.IGNORECASE)
        esas_match = re.search(r'(?:esas|e\.)\s*(?:no\s*)?:?\s*(\d{4}/\d+)', metin, re.IGNORECASE)
        tarih = self.tarih_bul(metin, context="itiraz")
        
        # Kambiyo'da itiraz takibi durdurmaz!
        durdurur = takip_turu != TakipTuru.KAMBIYO
        
        return ItirazKaydi(
            itiraz_tarihi=tarih,
            mahkeme=mahkeme_match.group(1) if mahkeme_match else None,
            esas_no=esas_match.group(1) if esas_match else None,
            itiraz_eden=None,
            sonuc="Bekliyor",
            takibi_durdurur_mu=durdurur
        )
    
    # ========================================================================
    # EVRAK KATEGORİZASYON
    # ========================================================================
    
    def evrak_kategorize(self, metin: str, dosya_adi: str) -> EvrakKategorisi:
        """Evrakı kategorize et"""
        for kategori, patterns in self.EVRAK_PATTERNS.items():
            if self.pattern_ara(metin, patterns):
                return kategori
        return EvrakKategorisi.DIGER
    
    # ========================================================================
    # ANA ANALİZ FONKSİYONU
    # ========================================================================
    
    def dosya_analiz_et(self, arsiv_yolu: str) -> DosyaAnalizSonucu:
        """Ana analiz fonksiyonu"""
        sonuc = DosyaAnalizSonucu()
        
        # 1. Dosya dönüşüm raporu
        sonuc.donusum_raporu = self.dosya_donustur_ve_raporla(arsiv_yolu)
        
        if not self.temp_dir:
            return sonuc
        
        try:
            # 2. Tüm evrakları oku ve analiz et
            tum_metin = ""
            
            for root, dirs, files in os.walk(self.temp_dir):
                for dosya in files:
                    dosya_yolu = os.path.join(root, dosya)
                    ext = os.path.splitext(dosya)[1].lower()
                    
                    metin = ""
                    if ext == '.udf':
                        metin = self.udf_oku(dosya_yolu)
                    elif ext == '.pdf':
                        metin = self.pdf_oku(dosya_yolu)
                    elif ext in ['.xml', '.txt', '.html']:
                        try:
                            with open(dosya_yolu, 'r', encoding='utf-8', errors='ignore') as f:
                                metin = f.read()
                        except:
                            pass
                    
                    if metin:
                        tum_metin += metin + "\n\n"
                        
                        # Evrak bilgisi
                        kategori = self.evrak_kategorize(metin, dosya)
                        tarih = self.tarih_bul(metin)
                        
                        evrak = EvrakBilgisi(
                            dosya_adi=dosya,
                            kategori=kategori,
                            tarih=tarih,
                            metin=metin[:5000]
                        )
                        sonuc.evraklar.append(evrak)
                        
                        # Kategoriye göre analiz
                        if kategori == EvrakKategorisi.TEBLIGAT_MAZBATA:
                            teb = self.tebligat_analiz(metin, dosya)
                            sonuc.tum_tebligatlar.append(teb)
                        
                        elif kategori in [EvrakKategorisi.HACIZ_MUHTIRASI, EvrakKategorisi.BANKA_89_IHBAR]:
                            haciz = self.haciz_analiz(metin, dosya)
                            if haciz:
                                if haciz.haciz_turu in [HacizTuru.BANKA_89_1, HacizTuru.BANKA_89_2, HacizTuru.BANKA_89_3]:
                                    sonuc.banka_hacizleri.append(haciz)
                                elif haciz.haciz_turu == HacizTuru.SGK_MAAS:
                                    sonuc.sgk_hacizleri.append(haciz)
                                elif haciz.haciz_turu == HacizTuru.ARAC:
                                    sonuc.arac_hacizleri.append(haciz)
                                elif haciz.haciz_turu == HacizTuru.TASINMAZ:
                                    sonuc.tasinmaz_hacizleri.append(haciz)
                                elif haciz.haciz_turu in [HacizTuru.MENKUL_ESASTAN, HacizTuru.MENKUL_TALIMAT]:
                                    sonuc.menkul_hacizleri.append(haciz)
                                else:
                                    sonuc.diger_hacizler.append(haciz)
                        
                        elif kategori == EvrakKategorisi.TAKYIDAT:
                            takyidat = self.takyidat_analiz(metin)
                            # Takyidat bilgilerini taşınmaza ekle
                        
                        elif kategori == EvrakKategorisi.ITIRAZ_DILEKCE:
                            if not sonuc.itiraz:
                                sonuc.itiraz = self.itiraz_analiz(metin, sonuc.takip_turu)
            
            # 3. Genel bilgileri çıkar (tüm metinden)
            sonuc.dosya_no = self.dosya_no_bul(tum_metin)
            sonuc.takip_turu = self.takip_turu_tespit(tum_metin)
            sonuc.alacakli = self.isim_bul(tum_metin, "alacaklı")
            sonuc.borclu = self.isim_bul(tum_metin, "borçlu")
            sonuc.borclu_tckn = self.tckn_bul(tum_metin)
            sonuc.toplam_alacak = self.tutar_bul(tum_metin)
            
            # VKN varsa tüzel kişi
            vkn = self.vkn_bul(tum_metin)
            if vkn and not sonuc.borclu_tckn:
                sonuc.borclu_tipi = "Tüzel Kişi"
            
            # 4. İtiraz süresi hesapla
            if sonuc.takip_turu == TakipTuru.KAMBIYO:
                sonuc.itiraz_suresi_gun = 5
            else:
                sonuc.itiraz_suresi_gun = 7
            
            # Ödeme emri tebligatını bul
            odeme_emri_tebligatlari = [t for t in sonuc.tum_tebligatlar 
                                        if self.pattern_ara(t.evrak_adi, ['ödeme', 'örnek'])]
            if odeme_emri_tebligatlari:
                sonuc.odeme_emri_tebligati = odeme_emri_tebligatlari[-1]
                if sonuc.odeme_emri_tebligati.tarih:
                    sonuc.itiraz_bitis_tarihi = sonuc.odeme_emri_tebligati.tarih + timedelta(days=sonuc.itiraz_suresi_gun)
                    sonuc.itiraz_suresi_doldu_mu = self.bugun > sonuc.itiraz_bitis_tarihi
                    sonuc.kesinlesti_mi = sonuc.itiraz_suresi_doldu_mu and not sonuc.itiraz
            
            # 5. Kritik uyarıları oluştur
            self._kritik_uyarilari_olustur(sonuc)
            
        finally:
            # Temizlik
            if self.temp_dir and os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir, ignore_errors=True)
                self.temp_dir = None
        
        return sonuc
    
    def _kritik_uyarilari_olustur(self, sonuc: DosyaAnalizSonucu):
        """Kritik uyarıları oluştur"""
        # İtiraz süresi
        if not sonuc.itiraz_suresi_doldu_mu and sonuc.itiraz_bitis_tarihi:
            kalan = (sonuc.itiraz_bitis_tarihi - self.bugun).days
            if kalan <= 3:
                sonuc.kritik_uyarilar.append(f"⚠️ İtiraz süresi {kalan} gün sonra doluyor!")
        
        # Kambiyo'da itiraz varsa ama takip durmaz
        if sonuc.itiraz and sonuc.takip_turu == TakipTuru.KAMBIYO:
            sonuc.kritik_uyarilar.append("📌 Kambiyo takibinde itiraz TAKİBİ DURDURMAZ - haciz işlemlerine devam edilebilir")
        
        # Tebligat eksiklikleri
        bila_tebligatlar = [t for t in sonuc.tum_tebligatlar if t.durum == TebligatDurumu.BILA]
        if bila_tebligatlar:
            sonuc.kritik_uyarilar.append(f"⚠️ {len(bila_tebligatlar)} adet bila tebligat var - 21/35 ile yeniden tebligat gerekli")
        
        # Menkul hacizde yetki
        for h in sonuc.menkul_hacizleri:
            if h.adres and h.yetki_alindi_mi == False:
                sonuc.kritik_uyarilar.append(f"⚠️ Menkul haciz (ev adresi) için İcra Hukuk Mahkemesi yetkisi alınmamış!")
        
        # Araç ve Taşınmaz için 106/110 süre takibi
        for h in sonuc.arac_hacizleri + sonuc.tasinmaz_hacizleri:
            if h.kalan_gun is not None:
                if h.kalan_gun < 0:
                    sonuc.kritik_uyarilar.append(f"❌ {h.hedef}: Haciz DÜŞMÜŞ ({abs(h.kalan_gun)} gün önce)")
                elif h.kalan_gun <= 30:
                    sonuc.kritik_uyarilar.append(f"🔴 {h.hedef}: Haciz {h.kalan_gun} gün içinde düşecek - SATIŞ TALEP EDİN!")
                elif h.kalan_gun <= 90:
                    sonuc.kritik_uyarilar.append(f"🟠 {h.hedef}: Haciz {h.kalan_gun} gün içinde düşecek")
        
        # Öneriler
        if sonuc.kesinlesti_mi and not sonuc.banka_hacizleri:
            sonuc.oneriler.append("💡 Takip kesinleşmiş - 89/1 banka haczi talep edilebilir")
        
        if sonuc.kesinlesti_mi and not sonuc.sgk_hacizleri:
            sonuc.oneriler.append("💡 SGK maaş haczi talep edilebilir")
    
    # ========================================================================
    # RAPOR OLUŞTURMA
    # ========================================================================
    
    def rapor_olustur(self, sonuc: DosyaAnalizSonucu) -> str:
        """Detaylı rapor oluştur"""
        rapor = []
        
        rapor.append("=" * 70)
        rapor.append("📋 İCRA DOSYA ANALİZ RAPORU")
        rapor.append(f"Tarih: {self.bugun.strftime('%d.%m.%Y %H:%M')}")
        rapor.append("=" * 70)
        
        # DOSYA DÖNÜŞÜM RAPORU
        if sonuc.donusum_raporu:
            r = sonuc.donusum_raporu
            rapor.append("\n📂 DOSYA DÖNÜŞÜM RAPORU")
            rapor.append("-" * 40)
            rapor.append(f"  Toplam Klasör: {r.toplam_klasor}")
            rapor.append(f"  Toplam Dosya: {r.toplam_dosya}")
            rapor.append(f"    • UDF: {r.udf_sayisi}")
            rapor.append(f"    • PDF: {r.pdf_sayisi}")
            rapor.append(f"    • TIFF: {r.tiff_sayisi}")
            rapor.append(f"    • XML: {r.xml_sayisi}")
            rapor.append(f"    • Diğer: {r.diger_sayisi}")
            rapor.append(f"  Başarılı Dönüşüm: {r.basarili_donusum}")
        
        # GENEL BİLGİLER
        rapor.append("\n📁 GENEL BİLGİLER")
        rapor.append("-" * 40)
        rapor.append(f"  Dosya No: {sonuc.dosya_no or 'Tespit edilemedi'}")
        rapor.append(f"  Takip Türü: {sonuc.takip_turu.value}")
        rapor.append(f"  Alacaklı: {sonuc.alacakli or 'Tespit edilemedi'}")
        rapor.append(f"  Borçlu: {sonuc.borclu or 'Tespit edilemedi'} ({sonuc.borclu_tipi})")
        if sonuc.borclu_tckn:
            rapor.append(f"  TCKN/VKN: {sonuc.borclu_tckn}")
        if sonuc.toplam_alacak:
            rapor.append(f"  Toplam Alacak: {sonuc.toplam_alacak:,.2f} TL")
        
        # KRİTİK UYARILAR
        if sonuc.kritik_uyarilar:
            rapor.append("\n🚨 KRİTİK UYARILAR")
            rapor.append("-" * 40)
            for u in sonuc.kritik_uyarilar:
                rapor.append(f"  {u}")
        
        # ÖDEME EMRİ ve KEİNLEŞME
        rapor.append("\n📬 ÖDEME EMRİ TEBLİGATI")
        rapor.append("-" * 40)
        if sonuc.odeme_emri_tebligati:
            t = sonuc.odeme_emri_tebligati
            rapor.append(f"  Durum: {t.durum.value}")
            if t.tarih:
                rapor.append(f"  Tebliğ Tarihi: {t.tarih.strftime('%d.%m.%Y')}")
            rapor.append(f"  İtiraz Süresi: {sonuc.itiraz_suresi_gun} gün ({sonuc.takip_turu.value})")
            if sonuc.itiraz_bitis_tarihi:
                rapor.append(f"  İtiraz Bitiş: {sonuc.itiraz_bitis_tarihi.strftime('%d.%m.%Y')}")
            if sonuc.itiraz_suresi_doldu_mu:
                rapor.append("  ✅ İtiraz süresi doldu - Takip KEİNLEŞMİŞ")
            else:
                kalan = (sonuc.itiraz_bitis_tarihi - self.bugun).days if sonuc.itiraz_bitis_tarihi else "?"
                rapor.append(f"  ⏳ İtiraz süresi devam ediyor ({kalan} gün kaldı)")
        else:
            rapor.append("  ⚠️ Ödeme emri tebligatı bulunamadı")
        
        # İTİRAZ
        if sonuc.itiraz:
            rapor.append("\n⚖️ İTİRAZ BİLGİSİ")
            rapor.append("-" * 40)
            rapor.append(f"  Mahkeme: {sonuc.itiraz.mahkeme or 'Belirtilmemiş'}")
            rapor.append(f"  Esas No: {sonuc.itiraz.esas_no or 'Belirtilmemiş'}")
            if sonuc.itiraz.itiraz_tarihi:
                rapor.append(f"  Tarih: {sonuc.itiraz.itiraz_tarihi.strftime('%d.%m.%Y')}")
            if sonuc.itiraz.takibi_durdurur_mu:
                rapor.append("  📌 Bu itiraz TAKİBİ DURDURUR (İlamsız)")
            else:
                rapor.append("  📌 Bu itiraz TAKİBİ DURDURMAZ (Kambiyo)")
        
        # HACİZLER
        rapor.append("\n💼 HACİZ TALEPLERİ")
        rapor.append("-" * 40)
        
        if sonuc.banka_hacizleri:
            rapor.append("  🏦 BANKA HACİZLERİ (89/1-2-3):")
            for h in sonuc.banka_hacizleri:
                rapor.append(f"    • {h.hedef}: {h.haciz_turu.value}")
                rapor.append("      ℹ️ Not: Banka hacizlerinde 106/110 süre takibi YOKTUR")
        
        if sonuc.sgk_hacizleri:
            rapor.append("  💼 SGK MAAŞ HACİZLERİ:")
            for h in sonuc.sgk_hacizleri:
                rapor.append(f"    • SGK Maaş Haczi")
        
        if sonuc.arac_hacizleri:
            rapor.append("  🚗 ARAÇ HACİZLERİ (106/110 TAKİBİ):")
            for h in sonuc.arac_hacizleri:
                if h.haciz_tarihi:
                    rapor.append(f"    • {h.hedef}")
                    rapor.append(f"      Haciz: {h.haciz_tarihi.strftime('%d.%m.%Y')} | Düşme: {h.dusme_tarihi.strftime('%d.%m.%Y') if h.dusme_tarihi else '?'}")
                    if h.kalan_gun is not None:
                        if h.kalan_gun < 0:
                            rapor.append(f"      ❌ HACİZ DÜŞMÜŞ")
                        else:
                            rapor.append(f"      Kalan: {h.kalan_gun} gün")
                    rapor.append(f"      Satış Talep: {'✅' if h.satis_talep_edildi_mi else '❌'} | Avans: {'✅' if h.satis_avans_yatirildi_mi else '❌'}")
        
        if sonuc.tasinmaz_hacizleri:
            rapor.append("  🏠 TAŞINMAZ HACİZLERİ (106/110 TAKİBİ):")
            for h in sonuc.tasinmaz_hacizleri:
                if h.haciz_tarihi:
                    rapor.append(f"    • {h.hedef}")
                    rapor.append(f"      Haciz: {h.haciz_tarihi.strftime('%d.%m.%Y')} | Düşme: {h.dusme_tarihi.strftime('%d.%m.%Y') if h.dusme_tarihi else '?'}")
                    if h.kalan_gun is not None:
                        if h.kalan_gun < 0:
                            rapor.append(f"      ❌ HACİZ DÜŞMÜŞ")
                        else:
                            rapor.append(f"      Kalan: {h.kalan_gun} gün")
        
        if sonuc.menkul_hacizleri:
            rapor.append("  📦 MENKUL HACİZLERİ:")
            for h in sonuc.menkul_hacizleri:
                tip = "Esastan" if h.esastan_mi else f"Talimat ({h.talimat_no})"
                rapor.append(f"    • {tip}")
                if h.adres:
                    rapor.append(f"      Adres: {h.adres[:50]}...")
                if h.yetki_alindi_mi is not None:
                    rapor.append(f"      Yetki: {'✅ Alındı' if h.yetki_alindi_mi else '❌ ALINMADI!'}")
                if h.tutanak_var_mi:
                    rapor.append(f"      Tutanak: ✅ Var ({h.tutanak_tarihi.strftime('%d.%m.%Y') if h.tutanak_tarihi else ''})")
        
        # ÖNERİLER
        if sonuc.oneriler:
            rapor.append("\n💡 ÖNERİLER")
            rapor.append("-" * 40)
            for o in sonuc.oneriler:
                rapor.append(f"  {o}")
        
        # EVRAK İSTATİSTİKLERİ
        rapor.append("\n📊 EVRAK İSTATİSTİKLERİ")
        rapor.append("-" * 40)
        rapor.append(f"  Toplam Analiz Edilen: {len(sonuc.evraklar)}")
        
        # Kategorilere göre say
        kategori_sayim = {}
        for e in sonuc.evraklar:
            k = e.kategori.value
            kategori_sayim[k] = kategori_sayim.get(k, 0) + 1
        
        for k, s in sorted(kategori_sayim.items(), key=lambda x: -x[1]):
            rapor.append(f"    • {k}: {s}")
        
        rapor.append("\n" + "=" * 70)
        rapor.append("Bu rapor otomatik oluşturulmuştur.")
        rapor.append("Detaylı hukuki değerlendirme için uzman incelemesi önerilir.")
        rapor.append("=" * 70)
        
        return "\n".join(rapor)


# ============================================================================
# TEST
# ============================================================================

if __name__ == "__main__":
    analiz = IcraDosyaAnaliz()
    
    # Test metni
    test = """
    İSTANBUL 12. İCRA DAİRESİ
    Dosya No: 2024/45678 Esas
    Örnek 7 - İlamsız Takip
    
    Alacaklı: ZİRAAT BANKASI A.Ş.
    Borçlu: MEHMET YILMAZ - 12345678901
    Toplam: 350.000,00 TL
    
    Ödeme Emri Tebliğ Tarihi: 15.09.2024
    Tebellüğ: Bizzat borçlu
    
    89/1 Haciz İhbarnamesi - Garanti Bankası
    Tarih: 25.09.2024
    
    Taşınmaz Haczi - 456 ada 78 parsel
    Haciz Tarihi: 01.10.2024
    Mülkiyet: Müşterek 1/2 hisse
    
    Araç Haczi - 34 XYZ 456
    Haciz Tarihi: 05.10.2024
    """
    
    print("Takip Türü:", analiz.takip_turu_tespit(test).value)
    print("Dosya No:", analiz.dosya_no_bul(test))
    print("Borçlu TCKN:", analiz.tckn_bul(test))
    print("Tutar:", analiz.tutar_bul(test))
    print("Plakalar:", analiz.plaka_bul(test))
    print("Ada/Parsel:", analiz.ada_parsel_bul(test))
    print("Banka:", analiz.banka_adi_bul(test))
    print("Mülkiyet:", analiz.mulkiyet_tipi_tespit(test).value)
