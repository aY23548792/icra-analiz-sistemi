#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
İİK 106/110 HACİZ SÜRE TAKİP MODÜLÜ v2.0
=========================================
7343 sayılı kanun sonrası güncel kurallar:
- TAŞINIR VE TAŞINMAZ AYRIMI YOK - HEPSİ 1 YIL!
- Satış talebiyle birlikte avans PEŞİN yatırılmalı
- 2026 avans tarifeleri güncel

Yasal Dayanak:
- İİK 106: Hacizden itibaren 1 YIL içinde satış istenmeli
- İİK 110: Süresinde satış istenmez veya avans yatırılmazsa haciz düşer
- 7343 sayılı kanun (30.11.2021): Taşınır/taşınmaz ayrımı kaldırıldı

Author: Arda & Claude
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, List
from enum import Enum


class MalTuru(Enum):
    """Haciz konusu mal türü"""
    TASINMAZ = "🏠 Taşınmaz"
    ARAC_OTOMOBIL = "🚗 Otomobil"
    ARAC_KAMYONET = "🚐 Kamyonet/Minibüs/Arazi"
    ARAC_KAMYON = "🚛 Otobüs/Kamyon/Çekici"
    TASINIR_DIGER = "📦 Diğer Taşınır"
    BANKA = "🏦 Banka Hesabı (89/1)"
    MAAS = "💰 Maaş Haczi"


class HacizDurumu(Enum):
    """Haciz süre durumu"""
    AKTIF = "✅ AKTİF - Süre devam ediyor"
    SATIS_ISTENDI_AVANS_TAMAM = "🔨 SATIŞ AŞAMASINDA"
    SATIS_ISTENDI_AVANS_EKSIK = "💳 AVANS EKSİK!"
    SURE_KRITIK = "🔴 KRİTİK - 30 gün kaldı!"
    SURE_UYARI = "⚠️ UYARI - 90 gün kaldı"
    DUSMUS = "❌ DÜŞMÜŞ - Yeniden haciz gerekli"
    SURESIZ = "♾️ SÜRESİZ (Banka/Maaş)"


@dataclass
class AvansTarifesi2026:
    """
    2026 Yılı Satış Giderleri Tarifesi
    Resmi Gazete: 20.12.2025, Yürürlük: 01.01.2026

    NOT: Her yıl güncellenir!
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
        """Mal türüne göre avans tutarı"""
        avans_map = {
            MalTuru.TASINMAZ: self.tasinmaz,
            MalTuru.ARAC_OTOMOBIL: self.arac_otomobil,
            MalTuru.ARAC_KAMYONET: self.arac_kamyonet,
            MalTuru.ARAC_KAMYON: self.arac_kamyon,
            MalTuru.TASINIR_DIGER: self.tasinir_diger,
            MalTuru.BANKA: 0.0,  # Süresiz
            MalTuru.MAAS: 0.0,   # Süresiz
        }
        return avans_map.get(mal_turu, 0.0)


@dataclass
class HacizKaydi:
    """Tek bir haciz kaydı"""
    id: str = ""
    mal_turu: MalTuru = MalTuru.TASINIR_DIGER
    haciz_tarihi: Optional[datetime] = None
    mal_aciklamasi: str = ""

    # Satış talebi
    satis_istendi: bool = False
    satis_talep_tarihi: Optional[datetime] = None

    # Avans
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
            "⚠️ KURAL: Tüm hacizler için 1 YIL içinde satış istenmeli + avans yatırılmalı!",
            "",
            f"📊 ÖZET:",
            f"   Toplam: {self.toplam}",
            f"   ✅ Aktif: {self.aktif}",
            f"   🔴 Kritik: {self.kritik}",
            f"   ❌ Düşmüş: {self.dusmus}",
            f"   ♾️ Süresiz: {self.suresiz}",
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

    Kullanım:
        takip = IIK106110Takip()

        # Haciz ekle
        takip.ekle(
            mal_turu=MalTuru.TASINMAZ,
            haciz_tarihi=datetime(2025, 6, 15),
            mal_aciklamasi="Kadıköy 3 ada 15 parsel",
            satis_istendi=True,
            avans_yatirildi=True,
            avans_tutari=40000
        )

        # Rapor
        print(takip.rapor().ozet)
    """

    # 7343 sonrası: HEPSİ 1 YIL (365 gün)
    SATIS_ISTEME_SURESI = 365

    # Süresiz haciz türleri
    SURESIZ = [MalTuru.BANKA, MalTuru.MAAS]

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

        # Süresiz türler (Banka 89/1, Maaş)
        if h.mal_turu in self.SURESIZ:
            h.durum = HacizDurumu.SURESIZ
            h.kalan_gun = 9999
            h.gereken_avans = 0
            h.aciklama = "Bu haciz türünde İİK 106/110 süresi işlemez. Satış talebi gerekmez."
            return

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

            # Avans hesapla
            if not h.avans_yatirildi and h.mal_turu not in self.SURESIZ:
                r.toplam_gereken_avans += h.gereken_avans

        return r

    def kritik_liste(self) -> List[HacizKaydi]:
        """Kritik hacizler"""
        return [h for h in self.hacizler if h.durum in [
            HacizDurumu.SURE_KRITIK,
            HacizDurumu.SATIS_ISTENDI_AVANS_EKSIK
        ]]

    def dusmus_liste(self) -> List[HacizKaydi]:
        """Düşmüş hacizler"""
        return [h for h in self.hacizler if h.durum == HacizDurumu.DUSMUS]


# === TEST ===
if __name__ == "__main__":
    print("🧪 İİK 106/110 Takip v2.0 Test")
    print("=" * 60)

    takip = IIK106110Takip()

    # 2026 Tarifesi
    print("\n💰 2026 AVANS TARİFESİ:")
    print(f"   🏠 Taşınmaz:        {takip.tarife.tasinmaz:>10,.0f} TL")
    print(f"   🚗 Otomobil:        {takip.tarife.arac_otomobil:>10,.0f} TL")
    print(f"   🚐 Kamyonet/Arazi:  {takip.tarife.arac_kamyonet:>10,.0f} TL")
    print(f"   🚛 Kamyon/Otobüs:   {takip.tarife.arac_kamyon:>10,.0f} TL")
    print(f"   📦 Diğer Taşınır:   {takip.tarife.tasinir_diger:>10,.0f} TL")

    # Test 1: Taşınmaz - satış istenmemiş
    print("\n" + "=" * 60)
    print("📝 Test 1: Taşınmaz - Satış istenmemiş")
    h1 = takip.ekle(
        mal_turu=MalTuru.TASINMAZ,
        haciz_tarihi=datetime(2025, 6, 15),
        mal_aciklamasi="Kadıköy 3 ada 15 parsel",
        satis_istendi=False
    )
    print(f"   Haciz: 15.06.2025")
    print(f"   Son tarih: {h1.son_tarih.strftime('%d.%m.%Y')}")
    print(f"   Kalan: {h1.kalan_gun} gün")
    print(f"   Durum: {h1.durum.value}")
    print(f"   Gereken avans: {h1.gereken_avans:,.0f} TL")

    # Test 2: Araç - satış istendi, avans eksik
    print("\n" + "=" * 60)
    print("📝 Test 2: Araç - Satış istendi ama avans YOK")
    h2 = takip.ekle(
        mal_turu=MalTuru.ARAC_OTOMOBIL,
        haciz_tarihi=datetime(2025, 10, 1),
        mal_aciklamasi="34 ABC 123 - Mercedes E200",
        satis_istendi=True,
        avans_yatirildi=False
    )
    print(f"   Haciz: 01.10.2025")
    print(f"   Son tarih: {h2.son_tarih.strftime('%d.%m.%Y')}")
    print(f"   Kalan: {h2.kalan_gun} gün")
    print(f"   Durum: {h2.durum.value}")
    print(f"   Gereken avans: {h2.gereken_avans:,.0f} TL")

    # Test 3: Banka - süresiz
    print("\n" + "=" * 60)
    print("📝 Test 3: Banka 89/1 - Süresiz")
    h3 = takip.ekle(
        mal_turu=MalTuru.BANKA,
        haciz_tarihi=datetime(2024, 1, 1),
        mal_aciklamasi="Ziraat Bankası"
    )
    print(f"   Durum: {h3.durum.value}")
    print(f"   Açıklama: {h3.aciklama}")

    # Test 4: Düşmüş haciz
    print("\n" + "=" * 60)
    print("📝 Test 4: Düşmüş haciz (1 yıldan fazla)")
    h4 = takip.ekle(
        mal_turu=MalTuru.TASINIR_DIGER,
        haciz_tarihi=datetime(2024, 1, 1),
        mal_aciklamasi="Ev eşyaları",
        satis_istendi=False
    )
    print(f"   Haciz: 01.01.2024")
    print(f"   Kalan: {h4.kalan_gun} gün")
    print(f"   Durum: {h4.durum.value}")
    print(f"   Açıklama: {h4.aciklama}")

    # Test 5: Tam prosedür
    print("\n" + "=" * 60)
    print("📝 Test 5: Tam prosedür - Satış istendi + Avans yatırıldı")
    h5 = takip.ekle(
        mal_turu=MalTuru.TASINMAZ,
        haciz_tarihi=datetime(2025, 3, 1),
        mal_aciklamasi="Beşiktaş 5 ada 20 parsel",
        satis_istendi=True,
        satis_talep_tarihi=datetime(2025, 9, 1),
        avans_yatirildi=True,
        avans_tutari=40000
    )
    print(f"   Haciz: 01.03.2025, Satış talebi: 01.09.2025")
    print(f"   Durum: {h5.durum.value}")
    print(f"   Açıklama: {h5.aciklama}")

    # Rapor
    print("\n" + "=" * 60)
    rapor = takip.rapor()
    print(rapor.ozet)
