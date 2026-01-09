#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
UYAP DOSYA ANALİZ MOTORU v12.0
==============================
UYAP ZIP arşivlerini tarar, evrakları sınıflandırır, kritik süreleri hesaplar.

Özellikler:
- Akıllı evrak sınıflandırma (20+ kategori)
- İİK 106/110 süre takibi
- Tebligat durumu analizi
- Aksiyon önerileri

NOT: Bloke hesaplaması burada YAPILMAZ (Single Source of Truth prensibi)
     Bloke için haciz_ihbar_analyzer.py kullanın.

Author: Arda & Claude
"""

import os
import re
import zipfile
import tempfile
import shutil
import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict
from dataclasses import dataclass, field

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# PDF desteği
try:
    import pdfplumber
    PDF_OK = True
except ImportError:
    PDF_OK = False

# Shared core
try:
    from icra_analiz_v2 import (
        IcraUtils, MalTuru, RiskSeviyesi, IslemDurumu,
        TebligatDurumu, EvrakKategorisi, HacizTuru,
        EvrakBilgisi, TebligatBilgisi, HacizBilgisi,
        AksiyonOnerisi, DosyaAnalizSonucu
    )
except ImportError:
    # Minimal fallback
    from enum import Enum
    class EvrakKategorisi(Enum):
        DIGER = "Diğer"
    class TebligatDurumu(Enum):
        BILINMIYOR = "Belirsiz"
    class IslemDurumu(Enum):
        UYARI = "Uyarı"
    
    @dataclass
    class EvrakBilgisi:
        dosya_adi: str
        evrak_turu: str
        tarih: datetime = None
        ozet: str = ""
    
    @dataclass
    class DosyaAnalizSonucu:
        toplam_evrak: int = 0
        evraklar: List = field(default_factory=list)
        aksiyonlar: List = field(default_factory=list)
        ozet_rapor: str = ""


class UYAPDosyaAnalyzer:
    """
    UYAP Dosya Analiz Motoru
    ------------------------
    ZIP içindeki tüm evrakları tarar, sınıflandırır ve analiz eder.
    """
    
    # Evrak sınıflandırma pattern'leri
    EVRAK_PATTERNS = {
        'ODEME_EMRI': [r'ödeme\s*emr', r'örnek\s*7', r'örnek\s*10', r'örnek\s*4'],
        'TEBLIGAT': [r'tebli[gğ]\s*mazbata', r'tebligat\s*parçası', r'tebliğ\s*evrakı'],
        'HACIZ_IHBAR': [r'89/1', r'89/2', r'89/3', r'haciz\s*ihbar'],
        'BANKA_CEVABI': [r'banka\s*cevab', r'bloke', r'hesap\s*bilgi'],
        'KIYMET_TAKDIRI': [r'k[ıi]ymet\s*takdir', r'değer\s*tespit', r'bilirkişi\s*rapor'],
        'SATIS_ILANI': [r'satış\s*ilan', r'açık\s*artırma', r'ihale'],
        'MAHKEME': [r'karar', r'duruşma', r'tensip', r'bilirkişi'],
        'TAKYIDAT': [r'takyidat', r'tapu\s*kayd', r'araç\s*sorgu', r'sicil'],
        'TALEP': [r'talep', r'dilekçe', r'beyan'],
        'VEKALETNAME': [r'vekaletname', r'vekalet'],
        'SOZLESME': [r'sözleşme', r'kredi', r'taahhüt'],
        'IHTARNAME': [r'ihtarname', r'ihtar'],
        'MASRAF': [r'masraf', r'harç', r'ücret'],
    }
    
    TEBLIGAT_DURUM_PATTERNS = {
        TebligatDurumu.TEBLIG_EDILDI: [r'tebliğ\s*edildi', r'bizzat', r'imza\s*karşılığı', r'teslim\s*edildi'],
        TebligatDurumu.BILA: [r'bila', r'iade', r'tanınmıyor', r'adres\s*yetersiz', r'taşınmış'],
        TebligatDurumu.MADDE_21: [r'21\.?\s*madde', r'muhtar', r'haber\s*kağıdı'],
        TebligatDurumu.MADDE_35: [r'35\.?\s*madde', r'eski\s*adres'],
        TebligatDurumu.MERNIS: [r'mernis', r'nüfus\s*kayıt'],
    }
    
    def __init__(self):
        self.bugun = datetime.now()
    
    def analiz_et(self, kaynak_yol: str) -> DosyaAnalizSonucu:
        """
        Ana analiz fonksiyonu.
        
        Args:
            kaynak_yol: ZIP dosyası veya klasör yolu
        
        Returns:
            DosyaAnalizSonucu
        """
        sonuc = DosyaAnalizSonucu()
        temp_dir = tempfile.mkdtemp()
        
        try:
            # 1. Dosyaları çıkar
            dosyalar = self._dosyalari_topla(kaynak_yol, temp_dir)
            
            # 2. Her dosyayı analiz et
            for dosya in dosyalar:
                self._dosya_analiz(dosya, sonuc)
            
            # 3. Post-processing
            self._haciz_sureleri_hesapla(sonuc)
            self._aksiyonlar_olustur(sonuc)
            self._ozet_rapor_olustur(sonuc)
            
        except Exception as e:
            logger.error(f"Analiz hatası: {e}")
            sonuc.ozet_rapor = f"Hata: {str(e)}"
        
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
        
        return sonuc
    
    def _dosyalari_topla(self, kaynak: str, temp_dir: str) -> List[str]:
        """Kaynak yoldan dosyaları topla"""
        dosyalar = []
        
        if os.path.isfile(kaynak) and kaynak.lower().endswith('.zip'):
            try:
                with zipfile.ZipFile(kaynak, 'r') as zf:
                    zf.extractall(temp_dir)
                for root, _, files in os.walk(temp_dir):
                    for f in files:
                        if not f.startswith('.'):
                            dosyalar.append(os.path.join(root, f))
            except Exception as e:
                logger.error(f"ZIP açma hatası: {e}")
        
        elif os.path.isdir(kaynak):
            for root, _, files in os.walk(kaynak):
                for f in files:
                    if not f.startswith('.'):
                        dosyalar.append(os.path.join(root, f))
        
        elif os.path.isfile(kaynak):
            dosyalar.append(kaynak)
        
        return sorted(dosyalar)
    
    def _dosya_oku(self, yol: str) -> str:
        """Dosya içeriğini oku"""
        ext = os.path.splitext(yol)[1].lower()
        
        try:
            if ext == '.pdf' and PDF_OK:
                with pdfplumber.open(yol) as pdf:
                    return "\n".join([p.extract_text() or "" for p in pdf.pages])
            
            elif ext == '.udf':
                with zipfile.ZipFile(yol, 'r') as zf:
                    if 'content.xml' in zf.namelist():
                        raw = zf.read('content.xml').decode('utf-8', errors='replace')
                        return re.sub(r'<[^>]+>', ' ', raw)
            
            elif ext in ['.txt', '.xml', '.html']:
                with open(yol, 'r', encoding='utf-8', errors='replace') as f:
                    return f.read()
        
        except Exception as e:
            logger.warning(f"Dosya okuma hatası ({yol}): {e}")
        
        return ""
    
    def _dosya_analiz(self, dosya_yolu: str, sonuc: DosyaAnalizSonucu):
        """Tek bir dosyayı analiz et"""
        fname = os.path.basename(dosya_yolu)
        metin = self._dosya_oku(dosya_yolu)
        
        sonuc.toplam_evrak += 1
        
        # Evrak türü tespit
        evrak_turu = self._evrak_siniflandir(metin, fname)
        
        # Tarih çıkar
        tarih = self._tarih_cikar(metin)
        
        # Evrak bilgisi ekle
        evrak = EvrakBilgisi(
            dosya_adi=fname,
            evrak_turu=evrak_turu,
            tarih=tarih,
            ozet=metin[:150] if metin else ""
        )
        sonuc.evraklar.append(evrak)
        
        # Evrak dağılımı güncelle
        tur_str = evrak_turu.value if hasattr(evrak_turu, 'value') else str(evrak_turu)
        sonuc.evrak_dagilimi[tur_str] = sonuc.evrak_dagilimi.get(tur_str, 0) + 1
        
        # Özel işlemler
        if evrak_turu == EvrakKategorisi.TEBLIGAT:
            self._tebligat_isle(metin, fname, tarih, sonuc)
        
        elif evrak_turu in [EvrakKategorisi.TAKYIDAT]:
            self._varlik_isle(metin, tarih, fname, sonuc)
    
    def _evrak_siniflandir(self, metin: str, fname: str) -> EvrakKategorisi:
        """Evrak türünü belirle"""
        combined = (metin + " " + fname).lower()
        
        # Türkçe karakter normalize
        tr_map = str.maketrans('İIĞÜŞÖÇ', 'iığüşöç')
        combined = combined.translate(tr_map)
        
        for kategori, patterns in self.EVRAK_PATTERNS.items():
            for p in patterns:
                if re.search(p, combined, re.IGNORECASE):
                    try:
                        return EvrakKategorisi[kategori]
                    except KeyError:
                        return EvrakKategorisi.DIGER
        
        return EvrakKategorisi.DIGER
    
    def _tarih_cikar(self, metin: str) -> Optional[datetime]:
        """Metinden tarih çıkar"""
        if not metin:
            return None
        
        # DD.MM.YYYY veya DD/MM/YYYY
        matches = re.findall(r'(\d{2})[./](\d{2})[./](\d{4})', metin)
        tarihler = []
        
        for d, m, y in matches:
            try:
                dt = datetime(int(y), int(m), int(d))
                if 2000 <= dt.year <= 2030:
                    tarihler.append(dt)
            except ValueError:
                pass
        
        return max(tarihler) if tarihler else None
    
    def _tebligat_isle(self, metin: str, fname: str, tarih: datetime, sonuc: DosyaAnalizSonucu):
        """Tebligat evrakını işle"""
        metin_lower = metin.lower() if metin else ""
        durum = TebligatDurumu.BILINMIYOR
        
        for d, patterns in self.TEBLIGAT_DURUM_PATTERNS.items():
            for p in patterns:
                if re.search(p, metin_lower):
                    durum = d
                    break
            if durum != TebligatDurumu.BILINMIYOR:
                break
        
        tebligat = TebligatBilgisi(
            evrak_adi=fname,
            tarih=tarih,
            durum=durum,
            aciklama=metin[:100] if metin else ""
        )
        sonuc.tebligatlar.append(tebligat)
    
    def _varlik_isle(self, metin: str, tarih: datetime, fname: str, sonuc: DosyaAnalizSonucu):
        """Varlık (araç/taşınmaz) bilgisi çıkar"""
        metin_lower = metin.lower() if metin else ""
        
        # Araç tespiti
        if 'araç' in metin_lower or 'plaka' in metin_lower:
            plaka = re.search(r'\d{2}\s?[a-zA-Z]{1,3}\s?\d{2,4}', metin)
            haciz = HacizBilgisi(
                tur=HacizTuru.ARAC,
                tarih=tarih,
                hedef=plaka.group(0) if plaka else "Araç",
                dosya_adi=fname
            )
            sonuc.hacizler.append(haciz)
        
        # Taşınmaz tespiti
        if 'taşınmaz' in metin_lower or 'tapu' in metin_lower or 'ada' in metin_lower:
            haciz = HacizBilgisi(
                tur=HacizTuru.TASINMAZ,
                tarih=tarih,
                hedef="Taşınmaz",
                dosya_adi=fname
            )
            sonuc.hacizler.append(haciz)
    
    def _haciz_sureleri_hesapla(self, sonuc: DosyaAnalizSonucu):
        """Haciz sürelerini hesapla (İİK 106/110)"""
        for haciz in sonuc.hacizler:
            if haciz.tur in [HacizTuru.ARAC, HacizTuru.TASINMAZ] and haciz.tarih:
                # Basit hesaplama (detaylı için IcraUtils kullanılabilir)
                base_days = 365  # 1 yıl
                deadline = haciz.tarih + timedelta(days=base_days)
                haciz.sure_106_110 = (deadline - self.bugun).days
    
    def _aksiyonlar_olustur(self, sonuc: DosyaAnalizSonucu):
        """Aksiyon önerileri oluştur"""
        
        # Bila tebligat kontrolü
        bila_sayisi = sum(1 for t in sonuc.tebligatlar if t.durum == TebligatDurumu.BILA)
        if bila_sayisi > 0:
            sonuc.aksiyonlar.append(AksiyonOnerisi(
                baslik="Bila Tebligat",
                aciklama=f"{bila_sayisi} adet tebligat bila dönmüş. Mernis/Madde 21 talebi açın.",
                oncelik=IslemDurumu.KRITIK
            ))
        
        # Haciz süre kontrolü
        for haciz in sonuc.hacizler:
            if haciz.sure_106_110 is not None:
                if haciz.sure_106_110 < 0:
                    sonuc.aksiyonlar.append(AksiyonOnerisi(
                        baslik=f"{haciz.hedef} - Haciz Düştü!",
                        aciklama=f"Satış isteme süresi {abs(haciz.sure_106_110)} gün önce doldu.",
                        oncelik=IslemDurumu.KRITIK
                    ))
                elif haciz.sure_106_110 < 45:
                    sonuc.aksiyonlar.append(AksiyonOnerisi(
                        baslik=f"{haciz.hedef} - Süre Kritik",
                        aciklama=f"Haczin düşmesine {haciz.sure_106_110} gün kaldı!",
                        oncelik=IslemDurumu.KRITIK
                    ))
        
        # Banka cevabı kontrolü
        banka_cevap_sayisi = sum(1 for e in sonuc.evraklar 
                                 if hasattr(e.evrak_turu, 'name') and 'BANKA' in e.evrak_turu.name)
        if banka_cevap_sayisi > 0:
            sonuc.aksiyonlar.append(AksiyonOnerisi(
                baslik="Banka Cevapları Mevcut",
                aciklama=f"{banka_cevap_sayisi} adet banka cevabı var. Bloke analizi için 'Haciz İhbar' modülünü kullanın.",
                oncelik=IslemDurumu.BILGI
            ))
    
    def _ozet_rapor_olustur(self, sonuc: DosyaAnalizSonucu):
        """Özet rapor oluştur"""
        lines = [
            "=" * 60,
            "📋 UYAP DOSYA ANALİZ RAPORU",
            f"Tarih: {self.bugun.strftime('%d.%m.%Y %H:%M')}",
            "=" * 60,
            "",
            f"📊 GENEL ÖZET",
            "-" * 40,
            f"  Toplam Evrak: {sonuc.toplam_evrak}",
            f"  Tebligat: {len(sonuc.tebligatlar)}",
            f"  Haciz: {len(sonuc.hacizler)}",
            "",
            "📁 EVRAK DAĞILIMI",
            "-" * 40,
        ]
        
        for tur, sayi in sorted(sonuc.evrak_dagilimi.items(), key=lambda x: -x[1]):
            lines.append(f"  {tur}: {sayi}")
        
        lines.extend([
            "",
            "⚡ YAPILACAKLAR",
            "-" * 40,
        ])
        
        if sonuc.aksiyonlar:
            for a in sonuc.aksiyonlar:
                icon = "🔴" if a.oncelik == IslemDurumu.KRITIK else "⚠️"
                lines.append(f"  {icon} {a.baslik}: {a.aciklama}")
        else:
            lines.append("  ✅ Acil işlem yok")
        
        lines.append("=" * 60)
        sonuc.ozet_rapor = "\n".join(lines)
    
    def excel_olustur(self, sonuc: DosyaAnalizSonucu, cikti_yol: str):
        """Excel raporu oluştur"""
        try:
            import pandas as pd
            
            with pd.ExcelWriter(cikti_yol, engine='openpyxl') as writer:
                # Özet
                pd.DataFrame([{
                    'Tarih': self.bugun,
                    'Toplam Evrak': sonuc.toplam_evrak,
                    'Tebligat': len(sonuc.tebligatlar),
                    'Haciz': len(sonuc.hacizler),
                }]).to_excel(writer, sheet_name='Özet', index=False)
                
                # Evraklar
                if sonuc.evraklar:
                    df = pd.DataFrame([{
                        'Dosya': e.dosya_adi,
                        'Tür': e.evrak_turu.value if hasattr(e.evrak_turu, 'value') else str(e.evrak_turu),
                        'Tarih': e.tarih.strftime('%d.%m.%Y') if e.tarih else '-'
                    } for e in sonuc.evraklar])
                    df.to_excel(writer, sheet_name='Evraklar', index=False)
                
                # Aksiyonlar
                if sonuc.aksiyonlar:
                    df = pd.DataFrame([{
                        'Öncelik': a.oncelik.value if hasattr(a.oncelik, 'value') else str(a.oncelik),
                        'Başlık': a.baslik,
                        'Açıklama': a.aciklama
                    } for a in sonuc.aksiyonlar])
                    df.to_excel(writer, sheet_name='Yapılacaklar', index=False)
            
            logger.info(f"Excel oluşturuldu: {cikti_yol}")
            
        except ImportError:
            logger.error("pandas/openpyxl yüklü değil")
        except Exception as e:
            logger.error(f"Excel hatası: {e}")


# === TEST ===
if __name__ == "__main__":
    print("🧪 UYAPDosyaAnalyzer Test")
    print("=" * 50)
    
    analyzer = UYAPDosyaAnalyzer()
    
    # Sınıflandırma testi
    test_cases = [
        ("89/1 haciz ihbarnamesi", "HACIZ_IHBAR"),
        ("tebliğ mazbatası", "TEBLIGAT"),
        ("kıymet takdiri raporu", "KIYMET_TAKDIRI"),
        ("random text", "DIGER"),
    ]
    
    for metin, beklenen in test_cases:
        sonuc = analyzer._evrak_siniflandir(metin, "test.pdf")
        status = "✅" if beklenen in str(sonuc) else "❌"
        print(f"{status} '{metin[:30]}' -> {sonuc}")
    
    print("\n✅ Test tamamlandı")
