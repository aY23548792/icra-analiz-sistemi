#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
İİK 106/110 HACİZ SÜRE TAKİP MODÜLÜ v2.1
=========================================
7343 sayılı kanun sonrası güncel kurallar:
- TAŞINIR VE TAŞINMAZ AYRIMI YOK - HEPSİ 1 YIL!
- Satış talebiyle birlikte avans PEŞİN yatırılmalı
- 2026 avans tarifeleri güncel

Yasal Dayanak:
- İİK 106: Hacizden itibaren 1 YIL içinde satış istenmeli
- İİK 110: Süresinde satış istenmez veya avans yatırılmazsa haciz düşer
- 7343 sayılı kanun (30.11.2021): Taşınır/taşınmaz ayrımı kaldırıldı

ÖNEMLİ - 89/1 HACİZ İHBARNAMELERİ:
==================================
89/1 hacizleri İİK 106/110 kapsamında DEĞİLDİR! Çünkü:
- 3. kişilerdeki para veya alacak haczidir
- Para zaten PARA olduğu için SATIŞ gerekmez
- Sadece TAHSİL/MAHSUP işlemi yapılır
- Süre sınırı YOKTUR

89/1 Muhatapları (sadece banka değil!):
- Bankalar (en yaygın)
- Tüzel kişiler (şirketler, firmalar)
- Gerçek kişiler (borçluya borçlu olan kişiler)
- Kamu kurumları (SGK, vergi dairesi vs.)
- Kiracılar (kira alacağı haczi)

Author: Arda & Claude
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, List
from enum import Enum


class MalTuru(Enum):
    """
    Haciz konusu mal türü
    
    İİK 106/110 KAPSAMINDA (Satış + Avans Gerekli):
    ------------------------------------------------
    - Taşınmaz (ev, arsa, tarla, dükkan)
    - Araçlar (otomobil, kamyon, minibüs vs.)
    - Diğer taşınırlar (ev eşyası, makine, stok vs.)
    
    İİK 106/110 KAPSAMI DIŞINDA (Satış Gerekmez - SÜRESİZ):
    -------------------------------------------------------
    - 89/1 Banka haczi (para zaten para)
    - 89/1 3. şahıs alacağı - Tüzel kişi (şirket, firma)
    - 89/1 3. şahıs alacağı - Gerçek kişi (kişisel borç, kira)
    - Maaş haczi (sürekli kesinti)
    """
    # === SATIŞ GEREKTİREN TÜRLER (İİK 106/110 kapsamında) ===
    TASINMAZ = "🏠 Taşınmaz"
    ARAC_OTOMOBIL = "🚗 Otomobil"
    ARAC_KAMYONET = "🚐 Kamyonet/Minibüs/Arazi"
    ARAC_KAMYON = "🚛 Otobüs/Kamyon/Çekici"
    TASINIR_DIGER = "📦 Diğer Taşınır"
    
    # === SATIŞ GEREKTİRMEYEN TÜRLER (89/1 ve maaş - SÜRESİZ) ===
    ALACAK_89_1_BANKA = "🏦 89/1 - Banka Hesabı"
    ALACAK_89_1_TUZEL = "🏢 89/1 - Şirket/Firma Alacağı"
    ALACAK_89_1_GERCEK = "👤 89/1 - Gerçek Kişi Alacağı"
    ALACAK_89_1_KAMU = "🏛️ 89/1 - Kamu Kurumu"
    MAAS = "💰 Maaş Haczi"


class HacizDurumu(Enum):
    """Haciz süre durumu"""
    AKTIF = "✅ AKTİF - Süre devam ediyor"
    SATIS_ISTENDI_AVANS_TAMAM = "🔨 SATIŞ AŞAMASINDA"
    SATIS_ISTENDI_AVANS_EKSIK = "💳 AVANS EKSİK!"
    SURE_KRITIK = "🔴 KRİTİK - 30 gün kaldı!"
    SURE_UYARI = "⚠️ UYARI - 90 gün kaldı"
    DUSMUS = "❌ DÜŞMÜŞ - Yeniden haciz gerekli"
    SURESIZ = "♾️ SÜRESİZ (89/1 veya Maaş - Satış yok)"


@dataclass
class AvansTarifesi2026:
    """
    2026 Yılı Satış Giderleri Tarifesi
    Resmi Gazete: 20.12.2025, Yürürlük: 01.01.2026
    
    NOT: Her yıl güncellenir! 89/1 hacizleri için avans GEREKMEZ.
    """
    yil: int = 2026
    
    # Taşınmaz
    tasinmaz: float = 40_000.0
    
    # Araçlar (sicile kayıtlı motorlu kara araçları)
    arac_otomobil: float = 28_000.0          # Otomobil ve diğer yük vasıtaları
    arac_kamyonet: float = 30_000.0          # Kamyonet, Minibüs, Midibüs, Arazi Taşıtı
    arac_kamyon: float = 39_000.0            # Otobüs, Kamyon, Çekici
    
    # Diğer taşınırlar
    tasinir_diger: float = 4_000.0
    
    def get_avans(self, mal_turu: MalTuru) -> float:
        """Mal türüne göre avans tutarı - 89/1 için 0"""
        avans_map = {
            # Satış gerektiren türler
            MalTuru.TASINMAZ: self.tasinmaz,
            MalTuru.ARAC_OTOMOBIL: self.arac_otomobil,
            MalTuru.ARAC_KAMYONET: self.arac_kamyonet,
            MalTuru.ARAC_KAMYON: self.arac_kamyon,
            MalTuru.TASINIR_DIGER: self.tasinir_diger,
            # 89/1 ve Maaş - AVANS YOK
            MalTuru.ALACAK_89_1_BANKA: 0.0,
            MalTuru.ALACAK_89_1_TUZEL: 0.0,
            MalTuru.ALACAK_89_1_GERCEK: 0.0,
            MalTuru.ALACAK_89_1_KAMU: 0.0,
            MalTuru.MAAS: 0.0,
        }
        return avans_map.get(mal_turu, 0.0)


@dataclass
class HacizKaydi:
    """Tek bir haciz kaydı"""
    id: str = ""
    mal_turu: MalTuru = MalTuru.TASINIR_DIGER
    haciz_tarihi: Optional[datetime] = None
    mal_aciklamasi: str = ""
    
    # Satış talebi (sadece taşınır/taşınmaz için geçerli)
    satis_istendi: bool = False
    satis_talep_tarihi: Optional[datetime] = None
    
    # Avans (sadece taşınır/taşınmaz için geçerli)
    avans_yatirildi: bool = False
    avans_tutari: float = 0.0
    
    # Hesaplanan
    durum: HacizDurumu = HacizDurumu.AKTIF
    kalan_gun: int = 0
    son_tarih: Optional[datetime] = None
    gereken_avans: float = 0.0
    aciklama: str = ""


@dataclass 
class HacizTakipRaporu:
    """Toplu rapor"""
    toplam: int = 0
    aktif: int = 0
    kritik: int = 0
    dusmus: int = 0
    suresiz: int = 0
    toplam_gereken_avans: float = 0.0
    hacizler: List[HacizKaydi] = field(default_factory=list)
    
    @property
    def ozet(self) -> str:
        lines = [
            "=" * 60,
            "İİK 106/110 HACİZ SÜRE TAKİP RAPORU",
            f"Tarih: {datetime.now().strftime('%d.%m.%Y %H:%M')}",
            "=" * 60,
            "",
            "⚠️ KURAL: Taşınır/taşınmaz için 1 YIL içinde satış + avans!",
            "ℹ️ NOT: 89/1 hacizleri (banka, şirket, kişi) SÜRESİZDİR.",
            "",
            f"📊 ÖZET:",
            f"   Toplam: {self.toplam}",
            f"   ✅ Aktif: {self.aktif}",
            f"   🔴 Kritik: {self.kritik}",
            f"   ❌ Düşmüş: {self.dusmus}",
            f"   ♾️ Süresiz (89/1 + Maaş): {self.suresiz}",
            "",
            f"💰 Toplam Gereken Avans: {self.toplam_gereken_avans:,.0f} TL",
        ]
        
        # Kritik olanlar
        kritik = [h for h in self.hacizler if h.durum in [HacizDurumu.SURE_KRITIK, HacizDurumu.SATIS_ISTENDI_AVANS_EKSIK]]
        if kritik:
            lines.extend(["", "-" * 60, "🔴 ACİL AKSİYON GEREKLİ:", "-" * 60])
            for h in kritik:
                lines.append(f"   • {h.mal_turu.value}: {h.mal_aciklamasi}")
                lines.append(f"     {h.aciklama}")
        
        # Düşmüşler
        dusmus = [h for h in self.hacizler if h.durum == HacizDurumu.DUSMUS]
        if dusmus:
            lines.extend(["", "-" * 60, "❌ DÜŞMÜŞ HACİZLER:", "-" * 60])
            for h in dusmus:
                lines.append(f"   • {h.mal_turu.value}: {h.mal_aciklamasi}")
        
        return "\n".join(lines)


class IIK106110Takip:
    """
    İİK 106/110 Haciz Süre Takip Sistemi
    
    ÖNEMLI: 7343 sayılı kanunla (30.11.2021):
    - Taşınır/taşınmaz ayrımı KALDIRILDI
    - HEPSİ İÇİN 1 YIL SÜRE
    - Satış talebiyle birlikte avans PEŞİN yatırılmalı
    
    ANCAK: 89/1 hacizleri (banka, şirket, gerçek kişi alacakları)
    İİK 106/110 kapsamında DEĞİLDİR - satış/avans gerekmez!
    """
    
    # 7343 sonrası: Taşınır ve taşınmaz için 1 YIL (365 gün)
    SATIS_ISTEME_SURESI = 365
    
    # Süresiz haciz türleri (89/1 + Maaş)
    # Bu türler için İİK 106/110 işlemez - satış/avans GEREKMEZ
    SURESIZ = [
        MalTuru.ALACAK_89_1_BANKA,   # Banka haczi
        MalTuru.ALACAK_89_1_TUZEL,   # Şirket/firma alacağı
        MalTuru.ALACAK_89_1_GERCEK,  # Gerçek kişi alacağı
        MalTuru.ALACAK_89_1_KAMU,    # Kamu kurumu
        MalTuru.MAAS,                 # Maaş haczi
    ]
    
    def __init__(self, tarife: Optional[AvansTarifesi2026] = None):
        self.hacizler: List[HacizKaydi] = []
        self.tarife = tarife or AvansTarifesi2026()
    
    def ekle(
        self,
        mal_turu: MalTuru,
        haciz_tarihi: datetime,
        mal_aciklamasi: str = "",
        satis_istendi: bool = False,
        satis_talep_tarihi: Optional[datetime] = None,
        avans_yatirildi: bool = False,
        avans_tutari: float = 0.0
    ) -> HacizKaydi:
        """Haciz kaydı ekle"""
        
        haciz = HacizKaydi(
            id=f"HCZ-{len(self.hacizler)+1:04d}",
            mal_turu=mal_turu,
            haciz_tarihi=haciz_tarihi,
            mal_aciklamasi=mal_aciklamasi,
            satis_istendi=satis_istendi,
            satis_talep_tarihi=satis_talep_tarihi,
            avans_yatirildi=avans_yatirildi,
            avans_tutari=avans_tutari
        )
        
        self._hesapla(haciz)
        self.hacizler.append(haciz)
        return haciz
    
    def _hesapla(self, h: HacizKaydi):
        """Durumu hesapla"""
        bugun = datetime.now()
        
        # === SÜRESİZ TÜRLER (89/1 + Maaş) ===
        # Bu türler için İİK 106/110 işlemez!
        if h.mal_turu in self.SURESIZ:
            h.durum = HacizDurumu.SURESIZ
            h.kalan_gun = 9999
            h.gereken_avans = 0
            
            # Türe göre açıklama
            if h.mal_turu == MalTuru.ALACAK_89_1_BANKA:
                h.aciklama = "89/1 Banka haczi - Para zaten para, satış gerekmez. Tahsil bekleniyor."
            elif h.mal_turu == MalTuru.ALACAK_89_1_TUZEL:
                h.aciklama = "89/1 Şirket/Firma alacağı - Satış gerekmez. 3. şahıs cevabı bekleniyor."
            elif h.mal_turu == MalTuru.ALACAK_89_1_GERCEK:
                h.aciklama = "89/1 Gerçek kişi alacağı - Satış gerekmez. 3. şahıs cevabı bekleniyor."
            elif h.mal_turu == MalTuru.ALACAK_89_1_KAMU:
                h.aciklama = "89/1 Kamu kurumu - Satış gerekmez. Kurum cevabı bekleniyor."
            elif h.mal_turu == MalTuru.MAAS:
                h.aciklama = "Maaş haczi - Sürekli kesinti, satış gerekmez."
            else:
                h.aciklama = "Bu haciz türünde İİK 106/110 süresi işlemez."
            return
        
        # === SATIŞ GEREKTİREN TÜRLER (Taşınır/Taşınmaz) ===
        if not h.haciz_tarihi:
            h.aciklama = "Haciz tarihi belirtilmemiş!"
            return
        
        # Son tarih hesapla (haciz + 1 yıl)
        h.son_tarih = h.haciz_tarihi + timedelta(days=self.SATIS_ISTEME_SURESI)
        h.kalan_gun = (h.son_tarih - bugun).days
        h.gereken_avans = self.tarife.get_avans(h.mal_turu)
        
        # Durum belirleme
        if h.kalan_gun < 0:
            # SÜRE DOLMUŞ
            if h.satis_istendi and h.avans_yatirildi:
                h.durum = HacizDurumu.SATIS_ISTENDI_AVANS_TAMAM
                h.aciklama = "Satış süreci devam ediyor (süresinde talep edilmiş)."
            else:
                h.durum = HacizDurumu.DUSMUS
                h.aciklama = f"HACİZ DÜŞMÜŞ! {abs(h.kalan_gun)} gün önce süre doldu. YENİDEN HACİZ GEREKLİ!"
        
        elif h.kalan_gun <= 30:
            # KRİTİK - 30 gün içinde düşecek
            if h.satis_istendi and h.avans_yatirildi:
                h.durum = HacizDurumu.SATIS_ISTENDI_AVANS_TAMAM
                h.aciklama = f"Satış aşamasında. {h.kalan_gun} gün kaldı."
            elif h.satis_istendi and not h.avans_yatirildi:
                h.durum = HacizDurumu.SATIS_ISTENDI_AVANS_EKSIK
                h.aciklama = f"ACİL! Avans eksik! {h.kalan_gun} gün kaldı. {h.gereken_avans:,.0f} TL yatırılmalı!"
            else:
                h.durum = HacizDurumu.SURE_KRITIK
                h.aciklama = f"ACİL! {h.kalan_gun} gün kaldı! Satış talebi + {h.gereken_avans:,.0f} TL avans YOK!"
        
        elif h.kalan_gun <= 90:
            # UYARI - 90 gün
            if h.satis_istendi and h.avans_yatirildi:
                h.durum = HacizDurumu.SATIS_ISTENDI_AVANS_TAMAM
                h.aciklama = f"Satış aşamasında. {h.kalan_gun} gün kaldı."
            elif h.satis_istendi:
                h.durum = HacizDurumu.SATIS_ISTENDI_AVANS_EKSIK
                h.aciklama = f"UYARI! Satış istendi ama avans eksik! {h.gereken_avans:,.0f} TL gerekli."
            else:
                h.durum = HacizDurumu.SURE_UYARI
                h.aciklama = f"{h.kalan_gun} gün kaldı. Satış talebi + {h.gereken_avans:,.0f} TL avans gerekli."
        
        else:
            # Normal
            if h.satis_istendi and h.avans_yatirildi:
                h.durum = HacizDurumu.SATIS_ISTENDI_AVANS_TAMAM
                h.aciklama = f"Satış aşamasında. {h.kalan_gun} gün süre var."
            elif h.satis_istendi:
                h.durum = HacizDurumu.SATIS_ISTENDI_AVANS_EKSIK
                h.aciklama = f"Satış istendi ama avans eksik! {h.gereken_avans:,.0f} TL gerekli."
            else:
                h.durum = HacizDurumu.AKTIF
                h.aciklama = f"Aktif. {h.kalan_gun} gün içinde satış + {h.gereken_avans:,.0f} TL avans gerekli."
    
    def rapor(self) -> HacizTakipRaporu:
        """Rapor oluştur"""
        r = HacizTakipRaporu()
        r.hacizler = self.hacizler
        r.toplam = len(self.hacizler)
        
        for h in self.hacizler:
            if h.durum == HacizDurumu.SURESIZ:
                r.suresiz += 1
            elif h.durum == HacizDurumu.DUSMUS:
                r.dusmus += 1
            elif h.durum in [HacizDurumu.SURE_KRITIK, HacizDurumu.SATIS_ISTENDI_AVANS_EKSIK]:
                r.kritik += 1
                r.aktif += 1
            else:
                r.aktif += 1
            
            # Avans hesapla (sadece satış gerektiren türler için)
            if not h.avans_yatirildi and h.mal_turu not in self.SURESIZ:
                r.toplam_gereken_avans += h.gereken_avans
        
        return r
    
    def kritik_liste(self) -> List[HacizKaydi]:
        """Kritik hacizler (sadece taşınır/taşınmaz)"""
        return [h for h in self.hacizler if h.durum in [
            HacizDurumu.SURE_KRITIK, 
            HacizDurumu.SATIS_ISTENDI_AVANS_EKSIK
        ]]
    
    def dusmus_liste(self) -> List[HacizKaydi]:
        """Düşmüş hacizler (sadece taşınır/taşınmaz)"""
        return [h for h in self.hacizler if h.durum == HacizDurumu.DUSMUS]
    
    def suresiz_liste(self) -> List[HacizKaydi]:
        """Süresiz hacizler (89/1 + maaş)"""
        return [h for h in self.hacizler if h.durum == HacizDurumu.SURESIZ]


# === TEST ===
if __name__ == "__main__":
    print("🧪 İİK 106/110 Takip v2.1 Test")
    print("=" * 60)
    
    takip = IIK106110Takip()
    
    # 2026 Tarifesi
    print("\n💰 2026 AVANS TARİFESİ (Sadece Taşınır/Taşınmaz):")
    print(f"   🏠 Taşınmaz:        {takip.tarife.tasinmaz:>10,.0f} TL")
    print(f"   🚗 Otomobil:        {takip.tarife.arac_otomobil:>10,.0f} TL")
    print(f"   🚐 Kamyonet/Arazi:  {takip.tarife.arac_kamyonet:>10,.0f} TL")
    print(f"   🚛 Kamyon/Otobüs:   {takip.tarife.arac_kamyon:>10,.0f} TL")
    print(f"   📦 Diğer Taşınır:   {takip.tarife.tasinir_diger:>10,.0f} TL")
    print(f"\n   ⚠️ 89/1 hacizleri için avans GEREKMEZ!")
    
    # Test 1: Taşınmaz
    print("\n" + "=" * 60)
    print("📝 Test 1: Taşınmaz - Satış + Avans gerekli")
    h1 = takip.ekle(
        mal_turu=MalTuru.TASINMAZ,
        haciz_tarihi=datetime(2025, 6, 15),
        mal_aciklamasi="Kadıköy 3 ada 15 parsel",
        satis_istendi=False
    )
    print(f"   Durum: {h1.durum.value}")
    print(f"   Kalan: {h1.kalan_gun} gün")
    print(f"   Avans: {h1.gereken_avans:,.0f} TL")
    
    # Test 2: 89/1 Banka - SÜRESİZ
    print("\n" + "=" * 60)
    print("📝 Test 2: 89/1 Banka Haczi - SÜRESİZ")
    h2 = takip.ekle(
        mal_turu=MalTuru.ALACAK_89_1_BANKA,
        haciz_tarihi=datetime(2024, 1, 1),
        mal_aciklamasi="Ziraat Bankası - Bloke 45.678 TL"
    )
    print(f"   Durum: {h2.durum.value}")
    print(f"   Avans: {h2.gereken_avans:,.0f} TL (GEREKMEZ!)")
    print(f"   Açıklama: {h2.aciklama}")
    
    # Test 3: 89/1 Şirket - SÜRESİZ
    print("\n" + "=" * 60)
    print("📝 Test 3: 89/1 Şirket Alacağı - SÜRESİZ")
    h3 = takip.ekle(
        mal_turu=MalTuru.ALACAK_89_1_TUZEL,
        haciz_tarihi=datetime(2025, 3, 1),
        mal_aciklamasi="ABC İnşaat A.Ş. - Hakediş alacağı"
    )
    print(f"   Durum: {h3.durum.value}")
    print(f"   Açıklama: {h3.aciklama}")
    
    # Test 4: 89/1 Gerçek Kişi - SÜRESİZ
    print("\n" + "=" * 60)
    print("📝 Test 4: 89/1 Gerçek Kişi Alacağı - SÜRESİZ")
    h4 = takip.ekle(
        mal_turu=MalTuru.ALACAK_89_1_GERCEK,
        haciz_tarihi=datetime(2025, 5, 1),
        mal_aciklamasi="Ahmet Yılmaz - Kira alacağı"
    )
    print(f"   Durum: {h4.durum.value}")
    print(f"   Açıklama: {h4.aciklama}")
    
    # Test 5: Araç - Düşmüş
    print("\n" + "=" * 60)
    print("📝 Test 5: Araç - DÜŞMÜŞ (1 yıldan fazla)")
    h5 = takip.ekle(
        mal_turu=MalTuru.ARAC_OTOMOBIL,
        haciz_tarihi=datetime(2024, 1, 1),
        mal_aciklamasi="34 ABC 123 - Mercedes",
        satis_istendi=False
    )
    print(f"   Durum: {h5.durum.value}")
    print(f"   Açıklama: {h5.aciklama}")
    
    # Rapor
    print("\n" + "=" * 60)
    rapor = takip.rapor()
    print(rapor.ozet)
