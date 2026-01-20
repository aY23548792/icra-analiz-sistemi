#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
UYAP DOSYA ANALYZER v12.5 - ENHANCED EDITION
=============================================
Genişletilmiş evrak sınıflandırma, doğru tip atamaları.
Haciz süre hesaplaması (İİK 106/110) dahil.

Author: Arda & Claude
"""

import os
import zipfile
import re
from datetime import datetime
from typing import Optional, List, Dict
from dataclasses import dataclass, field
from enum import Enum

# === ENUMS (Standalone - import hatalarını önlemek için) ===
class EvrakKategorisi(Enum):
    ODEME_EMRI = "Ödeme Emri"
    TEBLIGAT = "Tebligat"
    HACIZ_IHBAR = "Haciz İhbarnamesi"
    BANKA_CEVABI = "Banka Cevabı"
    KIYMET_TAKDIRI = "Kıymet Takdiri"
    SATIS_ILANI = "Satış İlanı"
    MAHKEME = "Mahkeme Kararı"
    TAKYIDAT = "Takyidat"
    VEKALETNAME = "Vekaletname"
    SOZLESME = "Sözleşme"
    IHTARNAME = "İhtarname"
    MASRAF = "Masraf Belgesi"
    TALEP = "Talep/Dilekçe"
    DIGER = "Diğer"

class TebligatDurumu(Enum):
    TEBLIG_EDILDI = "✅ Tebliğ Edildi"
    BILA = "❌ Bila (İade)"
    MADDE_21 = "📍 Madde 21"
    MADDE_35 = "📍 Madde 35"
    MERNIS = "🏠 Mernis"
    BEKLENIYOR = "⏳ Bekleniyor"
    BILINMIYOR = "❓ Belirsiz"

class HacizTuru(Enum):
    BANKA_89_1 = "🏦 Banka 89/1"
    ARAC = "🚗 Araç"
    TASINMAZ = "🏠 Taşınmaz"
    MENKUL = "📦 Menkul"
    MAAS = "💰 Maaş"
    DIGER = "📋 Diğer"

class IslemDurumu(Enum):
    KRITIK = "🔴 KRİTİK"
    UYARI = "⚠️ UYARI"
    BILGI = "ℹ️ BİLGİ"
    TAMAMLANDI = "✅ TAMAMLANDI"

class RiskSeviyesi(Enum):
    DUSMUS = "❌ DÜŞMÜŞ"
    KRITIK = "🔴 KRİTİK"
    YUKSEK = "🟠 YÜKSEK"
    ORTA = "🟡 ORTA"
    DUSUK = "🟢 DÜŞÜK"
    GUVENLI = "✅ GÜVENLİ"
    BILINMIYOR = "❓ BİLİNMİYOR"

# === DATA CLASSES ===
@dataclass
class EvrakBilgisi:
    dosya_adi: str
    evrak_turu: EvrakKategorisi
    tarih: Optional[datetime] = None
    ozet: str = ""

@dataclass
class TebligatBilgisi:
    evrak_adi: str
    tarih: Optional[datetime]
    durum: TebligatDurumu
    aciklama: str = ""

@dataclass
class HacizBilgisi:
    tur: HacizTuru
    tarih: Optional[datetime]
    hedef: str = ""
    tutar: float = 0.0
    kalan_gun: Optional[int] = None
    risk: RiskSeviyesi = RiskSeviyesi.BILINMIYOR
    dosya_adi: str = ""

@dataclass
class AksiyonOnerisi:
    baslik: str
    aciklama: str
    oncelik: IslemDurumu
    son_tarih: Optional[datetime] = None

@dataclass
class DosyaAnalizSonucu:
    toplam_evrak: int = 0
    evraklar: List[EvrakBilgisi] = field(default_factory=list)
    tebligatlar: List[TebligatBilgisi] = field(default_factory=list)
    hacizler: List[HacizBilgisi] = field(default_factory=list)
    aksiyonlar: List[AksiyonOnerisi] = field(default_factory=list)
    evrak_dagilimi: Dict[str, int] = field(default_factory=dict)
    toplam_bloke: float = 0.0
    ozet_rapor: str = ""


class UYAPDosyaAnalyzer:
    """
    UYAP ZIP dosyası analizörü

    Özellikler:
    - 15+ evrak kategorisi tanıma
    - Tebligat durumu tespiti
    - Haciz süre hesaplaması (İİK 106/110)
    - Aksiyon önerileri
    """

    # === EVRAK SINIFLANDIRMA PATTERNLERİ ===
    EVRAK_PATTERNS = {
        EvrakKategorisi.ODEME_EMRI: [
            r'[oö]deme\s*emr', r'odeme\s*emr', r'[oö]rnek\s*7', r'ornek\s*7',
            r'[oö]rnek\s*10', r'ornek\s*10', r'[oö]rnek\s*4', r'ornek\s*4',
            r'[oö]rnek\s*5', r'ornek\s*5', r'icra\s*emr'
        ],
        EvrakKategorisi.TEBLIGAT: [
            r'tebli[gğ]\s*mazbata', r'teblig\s*mazbata', r'tebligat\s*par[cç]as',
            r'tebligat\s*parcas', r'tebli[gğ]\s*evrak', r'teblig\s*evrak',
            r'tebli[gğ]name', r'tebligname', r'mazbata'
        ],
        EvrakKategorisi.HACIZ_IHBAR: [
            r'89/1', r'89/2', r'89/3', r'89_1', r'89_2', r'89_3',
            r'haciz\s*ihbar', r'birinci\s*haciz', r'ikinci\s*haciz',
            r'[uü][cç][uü]nc[uü]\s*haciz', r'ucuncu\s*haciz'
        ],
        EvrakKategorisi.BANKA_CEVABI: [
            r'banka[\s_]*cevab', r'banka[\s_]*yan[ıi]t', r'bloke', r'hesap[\s_]*bilgi',
            r'haciz[\s_]*cevab', r'm[uü]zekkere[\s_]*cevab', r'muzekkere[\s_]*cevab'
        ],
        EvrakKategorisi.KIYMET_TAKDIRI: [
            r'k[ıi]ymet[\s_]*takdir', r'kiymet[\s_]*takdir', r'de[gğ]er[\s_]*tespit',
            r'deger[\s_]*tespit', r'bilirki[sş]i[\s_]*rapor', r'bilirkisi[\s_]*rapor',
            r'ekspertiz'
        ],
        EvrakKategorisi.SATIS_ILANI: [
            r'sat[ıi][sş]\s*ilan', r'satis\s*ilan', r'a[cç][ıi]k\s*art[ıi]rma',
            r'acik\s*artirma', r'ihale', r'mezat'
        ],
        EvrakKategorisi.MAHKEME: [
            r'mahkeme\s*karar', r'duru[sş]ma', r'durusma', r'tensip',
            r'h[uü]k[uü]m', r'hukum', r'yarg[ıi]tay', r'yargitay', r'ilam'
        ],
        EvrakKategorisi.TAKYIDAT: [
            r'takyidat', r'tapu\s*kayd', r'ara[cç]\s*sorgu', r'arac\s*sorgu',
            r'sicil', r'ada.*parsel', r'plaka'
        ],
        EvrakKategorisi.VEKALETNAME: [
            r'vekaletname', r'vekalet'
        ],
        EvrakKategorisi.SOZLESME: [
            r's[oö]zle[sş]me', r'sozlesme', r'kredi\s*s[oö]zle[sş]me',
            r'taahh[uü]t', r'taahhut', r'protokol'
        ],
        EvrakKategorisi.IHTARNAME: [
            r'ihtarname', r'ihtar', r'noter\s*ihtar'
        ],
        EvrakKategorisi.MASRAF: [
            r'masraf', r'har[cç]', r'harc', r'[uü]cret', r'ucret', r'makbuz'
        ],
        EvrakKategorisi.TALEP: [
            r'talep', r'dilek[cç]e', r'dilekce', r'beyan', r'ba[sş]vuru', r'basvuru'
        ],
    }

    # Haciz türü belirleme (talep hariç)
    HACIZ_KEYWORDS = {
        HacizTuru.BANKA_89_1: [r'89/1', r'89/2', r'89/3', r'banka\s*haciz'],
        HacizTuru.ARAC: [r'araç', r'plaka', r'trafik', r'yakalama'],
        HacizTuru.TASINMAZ: [r'taşınmaz', r'tapu', r'gayrimenkul', r'ada.*parsel'],
        HacizTuru.MAAS: [r'maaş', r'ücret\s*haciz', r'sgk'],
        HacizTuru.MENKUL: [r'menkul', r'eşya', r'muhafaza'],
    }

    # Tebligat durumu belirleme
    TEBLIGAT_KEYWORDS = {
        TebligatDurumu.BILA: [r'bila', r'iade', r'tebliğ\s*edilemedi', r'bulunamadı'],
        TebligatDurumu.MADDE_21: [r'21\s*madde', r'muhtar', r'haber\s*kağıdı'],
        TebligatDurumu.MADDE_35: [r'35\s*madde', r'eski\s*adres'],
        TebligatDurumu.MERNIS: [r'mernis', r'nüfus\s*kayıt'],
        TebligatDurumu.TEBLIG_EDILDI: [r'tebliğ\s*edildi', r'tebellüğ', r'imza'],
    }

    def __init__(self):
        # Pre-compile patterns
        self._evrak_compiled = {
            cat: [re.compile(p, re.IGNORECASE) for p in patterns]
            for cat, patterns in self.EVRAK_PATTERNS.items()
        }
        self._haciz_compiled = {
            tur: [re.compile(p, re.IGNORECASE) for p in patterns]
            for tur, patterns in self.HACIZ_KEYWORDS.items()
        }
        self._tebligat_compiled = {
            durum: [re.compile(p, re.IGNORECASE) for p in patterns]
            for durum, patterns in self.TEBLIGAT_KEYWORDS.items()
        }

    def analiz_et(self, zip_yolu: str) -> DosyaAnalizSonucu:
        """Ana analiz fonksiyonu"""
        sonuc = DosyaAnalizSonucu()

        if not os.path.exists(zip_yolu):
            sonuc.ozet_rapor = f"Hata: Dosya bulunamadı - {zip_yolu}"
            return sonuc

        try:
            # ZIP mi tek dosya mı?
            if zip_yolu.endswith('.zip'):
                self._analiz_zip(zip_yolu, sonuc)
            else:
                # Tek dosya
                self._analiz_dosya(zip_yolu, sonuc)
            
            # Evrak dağılımı hesapla
            for evrak in sonuc.evraklar:
                kategori = evrak.evrak_turu.value
                sonuc.evrak_dagilimi[kategori] = sonuc.evrak_dagilimi.get(kategori, 0) + 1

            # Aksiyon önerileri oluştur
            self._olustur_aksiyonlar(sonuc)

            # Özet rapor oluştur
            sonuc.ozet_rapor = self._olustur_rapor(sonuc)
            
        except Exception as e:
            sonuc.ozet_rapor = f"Analiz Hatası: {e}"

        return sonuc

    def _analiz_zip(self, zip_yolu: str, sonuc: DosyaAnalizSonucu):
        """ZIP dosyasını analiz et"""
        with zipfile.ZipFile(zip_yolu, 'r') as zf:
            for name in zf.namelist():
                sonuc.toplam_evrak += 1

                # Dosya tarihini al
                try:
                    info = zf.getinfo(name)
                    dosya_tarihi = datetime(*info.date_time[:6])
                except:
                    dosya_tarihi = None

                # Dosya içeriğini oku (sınıflandırma için)
                icerik = ""
                try:
                    if name.endswith(('.xml', '.txt')):
                        icerik = zf.read(name).decode('utf-8', errors='replace')
                        icerik = re.sub(r'<[^>]+>', ' ', icerik)  # XML tag temizle
                except:
                    pass

                # Evrak sınıflandır
                evrak_turu = self._siniflandir_evrak(name, icerik)
                sonuc.evraklar.append(EvrakBilgisi(
                    dosya_adi=name,
                    evrak_turu=evrak_turu,
                    tarih=dosya_tarihi
                ))

                # Tebligat analizi
                if evrak_turu == EvrakKategorisi.TEBLIGAT:
                    tebligat_durum = self._tespit_tebligat_durumu(name, icerik)
                    sonuc.tebligatlar.append(TebligatBilgisi(
                        evrak_adi=name,
                        tarih=dosya_tarihi,
                        durum=tebligat_durum
                    ))

                # Haciz analizi (TALEP hariç!)
                name_lower = name.lower()
                if ("haciz" in name_lower or "yakalama" in name_lower) and "talep" not in name_lower:
                    haciz_turu = self._tespit_haciz_turu(name, icerik)
                    kalan_gun, risk = self._hesapla_haciz_suresi(dosya_tarihi, haciz_turu)

                    sonuc.hacizler.append(HacizBilgisi(
                        tur=haciz_turu,
                        tarih=dosya_tarihi,
                        kalan_gun=kalan_gun,
                        risk=risk,
                        dosya_adi=name
                    ))

    def _analiz_dosya(self, dosya_yolu: str, sonuc: DosyaAnalizSonucu):
        """Tek dosya analizi"""
        sonuc.toplam_evrak = 1

        try:
            dosya_tarihi = datetime.fromtimestamp(os.path.getmtime(dosya_yolu))
        except:
            dosya_tarihi = None

        dosya_adi = os.path.basename(dosya_yolu)
        evrak_turu = self._siniflandir_evrak(dosya_adi, "")

        sonuc.evraklar.append(EvrakBilgisi(
            dosya_adi=dosya_adi,
            evrak_turu=evrak_turu,
            tarih=dosya_tarihi
        ))

    def _siniflandir_evrak(self, dosya_adi: str, icerik: str) -> EvrakKategorisi:
        """Evrak kategorisini belirle"""
        text = f"{dosya_adi} {icerik}".lower()

        # Öncelik sırasına göre kontrol
        for kategori, patterns in self._evrak_compiled.items():
            if any(p.search(text) for p in patterns):
                return kategori

        return EvrakKategorisi.DIGER

    def _tespit_tebligat_durumu(self, dosya_adi: str, icerik: str) -> TebligatDurumu:
        """Tebligat durumunu belirle"""
        text = f"{dosya_adi} {icerik}".lower()

        for durum, patterns in self._tebligat_compiled.items():
            if any(p.search(text) for p in patterns):
                return durum

        return TebligatDurumu.BILINMIYOR

    def _tespit_haciz_turu(self, dosya_adi: str, icerik: str) -> HacizTuru:
        """Haciz türünü belirle"""
        text = f"{dosya_adi} {icerik}".lower()

        for tur, patterns in self._haciz_compiled.items():
            if any(p.search(text) for p in patterns):
                return tur

        return HacizTuru.DIGER

    def _hesapla_haciz_suresi(self, haciz_tarihi: Optional[datetime], haciz_turu: HacizTuru) -> tuple:
        """
        İİK 106/110 süre hesapla

        ÖNEMLI: 7343 sayılı kanunla (30.11.2021) taşınır/taşınmaz ayrımı KALDIRILDI!
        Artık HEPSİ İÇİN 1 YIL süre var.

        Kontrol edilecekler:
        1. Hacizden itibaren 1 yıl içinde satış istendi mi?
        2. Satış talebiyle birlikte avans yatırıldı mı?
        """
        if not haciz_tarihi:
            return None, RiskSeviyesi.BILINMIYOR

        # Banka ve maaş hacizlerinde süre yok (İİK 106/110 kapsamı dışında)
        if haciz_turu in [HacizTuru.BANKA_89_1, HacizTuru.MAAS]:
            return 9999, RiskSeviyesi.GUVENLI

        bugun = datetime.now()

        # 7343 sonrası: HEPSİ 1 YIL (365 gün) - Taşınır/taşınmaz ayrımı YOK!
        gun = 365

        from datetime import timedelta
        son_gun = haciz_tarihi + timedelta(days=gun)
        kalan = (son_gun - bugun).days

        # Risk seviyesi
        if kalan < 0:
            risk = RiskSeviyesi.DUSMUS
        elif kalan <= 30:
            risk = RiskSeviyesi.KRITIK
        elif kalan <= 90:
            risk = RiskSeviyesi.YUKSEK
        elif kalan <= 180:
            risk = RiskSeviyesi.ORTA
        else:
            risk = RiskSeviyesi.DUSUK

        return kalan, risk

    def _olustur_aksiyonlar(self, sonuc: DosyaAnalizSonucu):
        """Aksiyon önerileri oluştur"""
        # Bila tebligat kontrolü
        bila_sayisi = len([t for t in sonuc.tebligatlar if t.durum == TebligatDurumu.BILA])
        if bila_sayisi > 0:
            sonuc.aksiyonlar.append(AksiyonOnerisi(
                baslik="Bila Tebligat",
                aciklama=f"{bila_sayisi} adet tebligat bila dönmüş. Mernis/Madde 21 sorgulayın.",
                oncelik=IslemDurumu.KRITIK
            ))

        # Kritik haciz süresi kontrolü
        kritik_hacizler = [h for h in sonuc.hacizler if h.risk == RiskSeviyesi.KRITIK]
        if kritik_hacizler:
            sonuc.aksiyonlar.append(AksiyonOnerisi(
                baslik="Haciz Süresi Kritik",
                aciklama=f"{len(kritik_hacizler)} adet haciz süresi dolmak üzere! ACİL satış talebi.",
                oncelik=IslemDurumu.KRITIK
            ))

        # Düşmüş haciz kontrolü
        dusmus_hacizler = [h for h in sonuc.hacizler if h.risk == RiskSeviyesi.DUSMUS]
        if dusmus_hacizler:
            sonuc.aksiyonlar.append(AksiyonOnerisi(
                baslik="Haciz Düşmüş!",
                aciklama=f"{len(dusmus_hacizler)} adet haciz süresi dolmuş. Yeniden haciz gerekli!",
                oncelik=IslemDurumu.KRITIK
            ))

        # Haciz yoksa öneri
        if not sonuc.hacizler:
            sonuc.aksiyonlar.append(AksiyonOnerisi(
                baslik="Haciz Yok",
                aciklama="Malvarlığı sorgusu yapın (Araç/Tapu/Banka/SGK).",
                oncelik=IslemDurumu.UYARI
            ))

        # Genel bilgi
        if sonuc.hacizler and not kritik_hacizler and not dusmus_hacizler:
            sonuc.aksiyonlar.append(AksiyonOnerisi(
                baslik="Haciz Takibi",
                aciklama=f"{len(sonuc.hacizler)} adet haciz mevcut. Süreleri takip edin.",
                oncelik=IslemDurumu.BILGI
            ))

    def _olustur_rapor(self, sonuc: DosyaAnalizSonucu) -> str:
        """Özet rapor oluştur"""
        lines = [
            "=" * 50,
            "📊 UYAP DOSYA ANALİZ RAPORU",
            f"Tarih: {datetime.now().strftime('%d.%m.%Y %H:%M')}",
            "=" * 50,
            "",
            f"📁 Toplam Evrak: {sonuc.toplam_evrak}",
            f"📮 Tebligat İşlemi: {len(sonuc.tebligatlar)}",
            f"🔒 Haciz İşlemi: {len(sonuc.hacizler)}",
            "",
            "-" * 50,
            "📈 EVRAK DAĞILIMI:",
            "-" * 50,
        ]

        for kategori, adet in sorted(sonuc.evrak_dagilimi.items(), key=lambda x: -x[1]):
            lines.append(f"  • {kategori}: {adet}")

        if sonuc.hacizler:
            lines.extend([
                "",
                "-" * 50,
                "🔒 HACİZ DURUMU (İİK 106/110):",
                "-" * 50,
            ])
            for h in sonuc.hacizler:
                risk_icon = h.risk.value if h.risk else "❓"
                kalan = f"{h.kalan_gun} gün" if h.kalan_gun and h.kalan_gun < 9999 else "Süresiz"
                lines.append(f"  • {h.tur.value}: {kalan} - {risk_icon}")

        if sonuc.aksiyonlar:
            lines.extend([
                "",
                "-" * 50,
                "⚡ ÖNERİLEN AKSİYONLAR:",
                "-" * 50,
            ])
            for a in sonuc.aksiyonlar:
                lines.append(f"  [{a.oncelik.value}] {a.baslik}")
                lines.append(f"      → {a.aciklama}")

        return "\n".join(lines)


# === TEST ===
if __name__ == "__main__":
    print("🧪 UYAPDosyaAnalyzer v12.5 Test")
    print("=" * 50)

    analyzer = UYAPDosyaAnalyzer()

    # Test: Evrak sınıflandırma
    test_cases = [
        ("odeme_emri_ornek7.pdf", EvrakKategorisi.ODEME_EMRI),
        ("tebligat_mazbatasi.udf", EvrakKategorisi.TEBLIGAT),
        ("89_1_haciz_ihbarnamesi.pdf", EvrakKategorisi.HACIZ_IHBAR),
        ("ziraat_banka_cevabi.pdf", EvrakKategorisi.BANKA_CEVABI),
        ("kiymet_takdiri_raporu.pdf", EvrakKategorisi.KIYMET_TAKDIRI),
        ("vekaletname.pdf", EvrakKategorisi.VEKALETNAME),
    ]

    for dosya_adi, beklenen in test_cases:
        sonuc = analyzer._siniflandir_evrak(dosya_adi, "")
        status = "✅" if sonuc == beklenen else "❌"
        print(f"{status} {dosya_adi} → {sonuc.value} (beklenen: {beklenen.value})")

    print("\n✅ Testler tamamlandı")
