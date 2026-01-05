#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
UYAP DOSYA ANALİZ MOTORU v11.0 (Production)
===========================================
UYAP ZIP arşivlerini tarar, evrakları sınıflandırır ve kritik süreleri hesaplar.

CRITICAL DESIGN NOTE:
=====================
This module does NOT calculate bloke amounts!
Bloke calculation is ONLY done in haciz_ihbar_analyzer.py (Single Source of Truth)

Author: Arda & Claude
"""

import os
import re
import zipfile
import shutil
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import pandas as pd

# --- SHARED CORE IMPORTS ---
try:
    from icra_analiz_v2 import (
        BaseAnalyzer, IcraUtils,
        EvrakBilgisi, TebligatBilgisi, HacizBilgisi,
        DosyaAnalizSonucu, AksiyonOnerisi,
        EvrakKategorisi, TebligatDurumu, HacizTuru, IslemDurumu, TakipTuru
    )
except ImportError as e:
    raise ImportError(f"icra_analiz_v2.py bulunamadı! Lütfen aynı dizinde olduğundan emin olun. Hata: {e}")

# --- LOGGING ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class UYAPDosyaAnalyzer(BaseAnalyzer):
    """
    Main Logic Class for processing UYAP ZIP archives.
    Inherits temp_dir management from BaseAnalyzer.
    
    IMPORTANT: This class does NOT calculate bloke amounts.
    For bloke analysis, use haciz_ihbar_analyzer.py
    """

    # --- CLASSIFICATION PATTERNS (Compiled once for performance) ---
    PATTERNS = {
        EvrakKategorisi.ODEME_EMRI: [r'ödeme\s*emr', r'örnek\s*7', r'örnek\s*10'],
        EvrakKategorisi.TEBLIGAT_MAZBATA: [r'tebli[gğ]\s*mazbata', r'tebli[gğ]at\s*parçası'],
        EvrakKategorisi.HACIZ_IHBARNAMESI: [r'89/1', r'89/2', r'89/3', r'haciz\s*ihbar'],
        EvrakKategorisi.HACIZ_TUTANAGI: [r'haciz\s*tutana[gğ]', r'haciz\s*zapt'],
        EvrakKategorisi.KIYMET_TAKDIRI: [r'k[ıi]ymet\s*takdir', r'değer\s*tespit', r'bilirkişi'],
        EvrakKategorisi.SATIS_ILANI: [r'satış\s*ilanı', r'açık\s*artırma', r'ihale'],
        EvrakKategorisi.MAHKEME_KARARI: [r'gerekçeli\s*karar', r'duruşma\s*zapt', r'tensip'],
        EvrakKategorisi.TAKYIDAT: [r'takyidat', r'tapu\s*kayd', r'araç\s*sorgu'],
        EvrakKategorisi.TALEP_DILEKCE: [r'talep', r'beyan', r'dilekçe'],
        EvrakKategorisi.BANKA_CEVABI: [r'banka\s*cevab', r'bloke', r'hesap\s*bilgi'],
    }

    TEBLIGAT_PATTERNS = {
        TebligatDurumu.TEBLIG_EDILDI: [r'tebliğ\s*edildi', r'bizzat', r'imza\s*karşılığı'],
        TebligatDurumu.BILA: [r'bila', r'iade', r'tanınmıyor', r'adres\s*yetersiz'],
        TebligatDurumu.MADDE_21: [r'21\.?\s*madde', r'muhtar', r'haber\s*kağıdı'],
        TebligatDurumu.MADDE_35: [r'35\.?\s*madde', r'eski\s*adres'],
        TebligatDurumu.MERNIS: [r'mernis', r'nüfus\s*kayıt']
    }

    def __init__(self):
        super().__init__()
        self.today = datetime.now()

    def analiz_et(self, zip_path: str) -> DosyaAnalizSonucu:
        """
        Main entry point.
        1. Extract ZIP
        2. Iterate files -> Classify -> Extract Data
        3. Analyze Deadlines (106/110)
        4. Generate Action Items
        
        NOTE: Does NOT calculate bloke amounts (Single Source principle)
        """
        result = DosyaAnalizSonucu()
        self.setup_temp_dir()

        try:
            self.unzip_file(zip_path, self.temp_dir)
            
            # Track document distribution
            evrak_dagilimi = {}
            
            # --- FILE ITERATION ---
            for root, _, files in os.walk(self.temp_dir):
                for fname in files:
                    if fname.startswith('.'): continue
                    
                    file_path = os.path.join(root, fname)
                    text = IcraUtils.read_file_content(file_path)
                    
                    if not text: continue
                    
                    result.toplam_evrak += 1
                    
                    # 1. Classify
                    category = self._classify_document(text, fname)
                    date = IcraUtils.extract_date(text)
                    summary = text[:200].replace('\n', ' ').strip()
                    
                    # Track distribution
                    cat_name = category.value
                    evrak_dagilimi[cat_name] = evrak_dagilimi.get(cat_name, 0) + 1
                    
                    evrak = EvrakBilgisi(
                        dosya_adi=fname,
                        evrak_turu=category,
                        tarih=date,
                        metin_ozeti=summary
                    )
                    result.evraklar.append(evrak)
                    
                    # 2. Extract Specific Data based on Category
                    if category == EvrakKategorisi.TEBLIGAT_MAZBATA:
                        self._process_tebligat(result, text, fname, date)
                    
                    elif category == EvrakKategorisi.HACIZ_IHBARNAMESI:
                        # We just LOG it here. 
                        # IMPORTANT: NO amount extraction - Single Source principle
                        # Detailed bloke analysis is in haciz_ihbar_analyzer.py
                        haciz = HacizBilgisi(
                            tur=HacizTuru.BANKA_89_1,
                            tarih=date,
                            hedef="Banka/3.Şahıs (Detay için Haciz İhbar modülü)",
                            dosya_adi=fname
                            # NOTE: tutar is NOT set here!
                        )
                        result.hacizler.append(haciz)
                    
                    elif category == EvrakKategorisi.BANKA_CEVABI:
                        # Same principle - just log, don't calculate
                        pass  # Will be handled by haciz_ihbar_analyzer

                    elif category == EvrakKategorisi.TAKYIDAT:
                        # Check for Assets (Araç/Taşınmaz)
                        self._process_assets(result, text, date, fname)

            # Store distribution
            result.evrak_dagilimi = evrak_dagilimi
            
            # --- POST-PROCESSING ---
            self._analyze_deadlines(result)
            self._generate_actions(result)
            self._generate_summary(result)

        except Exception as e:
            logger.error(f"Analysis failed: {e}")
            result.ozet_rapor += f"\n[HATA] Analiz sırasında hata oluştu: {str(e)}"
        
        finally:
            self.cleanup()

        return result

    # ========================================================================
    # INTERNAL LOGIC
    # ========================================================================

    def _classify_document(self, text: str, fname: str) -> EvrakKategorisi:
        """Classify document based on content patterns."""
        text_lower = IcraUtils.clean_text(text + " " + fname)
        for cat, patterns in self.PATTERNS.items():
            for p in patterns:
                if re.search(p, text_lower):
                    return cat
        return EvrakKategorisi.BILINMIYOR

    def _process_tebligat(self, result: DosyaAnalizSonucu, text: str, fname: str, date: Optional[datetime]):
        """Extract notification status from tebligat documents."""
        status = TebligatDurumu.BILINMIYOR
        text_lower = IcraUtils.clean_text(text)
        
        for s, patterns in self.TEBLIGAT_PATTERNS.items():
            for p in patterns:
                if re.search(p, text_lower):
                    status = s
                    break
            if status != TebligatDurumu.BILINMIYOR:
                break
        
        # Simple extraction logic for recipient
        recipient = "Borçlu" # Default
        
        tb = TebligatBilgisi(
            evrak_adi=fname,
            durum=status,
            tarih=date,
            alici=recipient,
            mazbata_metni=text[:100]
        )
        result.tebligatlar.append(tb)

    def _process_assets(self, result: DosyaAnalizSonucu, text: str, date: Optional[datetime], fname: str):
        """
        Detects Vehicles (Araç) or Real Estate (Taşınmaz) in Takyidat docs
        to track 106/110 deadlines.
        """
        text_lower = IcraUtils.clean_text(text)
        
        # 1. Araç Detection
        if 'araç' in text_lower or 'plaka' in text_lower:
            # Look for license plate pattern roughly
            plaka_match = re.search(r'\d{2}\s?[a-z]{1,3}\s?\d{2,4}', text_lower)
            if plaka_match:
                hb = HacizBilgisi(
                    tur=HacizTuru.ARAC,
                    tarih=date,
                    hedef=plaka_match.group(0).upper(),
                    dosya_adi=fname
                )
                result.hacizler.append(hb)
        
        # 2. Taşınmaz Detection
        if 'taşınmaz' in text_lower or 'tapu' in text_lower:
            if 'ada' in text_lower and 'parsel' in text_lower:
                hb = HacizBilgisi(
                    tur=HacizTuru.TASINMAZ,
                    tarih=date,
                    hedef="Taşınmaz (Ada/Parsel)",
                    dosya_adi=fname
                )
                result.hacizler.append(hb)

    def _analyze_deadlines(self, result: DosyaAnalizSonucu):
        """
        Implements İİK 106/110 logic.
        - Movables (Araç): 1 Year
        - Immovables (Taşınmaz): 1 Year
        
        Note: Law changed in 2021, now both are 1 year (previously 6 months for movables)
        """
        for haciz in result.hacizler:
            if haciz.tur in [HacizTuru.ARAC, HacizTuru.TASINMAZ] and haciz.tarih:
                deadline = haciz.tarih + timedelta(days=365)
                haciz.dusme_tarihi = deadline
                remaining = (deadline - self.today).days
                haciz.sure_106_110 = remaining

    def _generate_actions(self, result: DosyaAnalizSonucu):
        """Generate action items based on analysis."""
        
        # 1. Tebligat Actions
        bila_count = sum(1 for t in result.tebligatlar if t.durum == TebligatDurumu.BILA)
        if bila_count > 0:
            result.aksiyonlar.append(AksiyonOnerisi(
                baslik="Bila Tebligat",
                aciklama=f"{bila_count} adet tebligat iade dönmüş. Mernis/Tk 21 talebi açılmalı.",
                oncelik=IslemDurumu.KRITIK
            ))

        # 2. Haciz Deadline Actions
        for h in result.hacizler:
            if h.sure_106_110 is not None:
                if h.sure_106_110 < 0:
                    result.aksiyonlar.append(AksiyonOnerisi(
                        baslik=f"{h.hedef} - Haciz Düştü!",
                        aciklama=f"Satış isteme süresi {abs(h.sure_106_110)} gün önce doldu. Yeniden haciz gerekli.",
                        oncelik=IslemDurumu.KRITIK
                    ))
                elif h.sure_106_110 < 45:
                    result.aksiyonlar.append(AksiyonOnerisi(
                        baslik=f"{h.hedef} - Satış İsteme Süresi Kritik",
                        aciklama=f"Haczin düşmesine sadece {h.sure_106_110} gün kaldı!",
                        oncelik=IslemDurumu.KRITIK,
                        son_tarih=h.dusme_tarihi
                    ))
                elif h.sure_106_110 < 90:
                    result.aksiyonlar.append(AksiyonOnerisi(
                        baslik=f"{h.hedef} - Satış Hazırlığı",
                        aciklama=f"Kalan süre: {h.sure_106_110} gün.",
                        oncelik=IslemDurumu.UYARI,
                        son_tarih=h.dusme_tarihi
                    ))
        
        # 3. Bank Response Notification
        banka_cevaplari = sum(1 for e in result.evraklar if e.evrak_turu == EvrakKategorisi.BANKA_CEVABI)
        haciz_ihbarlari = sum(1 for e in result.evraklar if e.evrak_turu == EvrakKategorisi.HACIZ_IHBARNAMESI)
        
        if banka_cevaplari > 0 or haciz_ihbarlari > 0:
            result.aksiyonlar.append(AksiyonOnerisi(
                baslik="Banka/89 Cevapları Mevcut",
                aciklama=f"{banka_cevaplari + haciz_ihbarlari} adet banka/haciz evrakı var. "
                        "Detaylı bloke analizi için '89/1-2-3 Haciz İhbar Analizi' modülünü kullanın.",
                oncelik=IslemDurumu.BILGI
            ))

    def _generate_summary(self, result: DosyaAnalizSonucu):
        """Generate text summary report."""
        lines = [
            "=" * 60,
            f"📋 UYAP DOSYA ANALİZ RAPORU",
            f"Tarih: {self.today.strftime('%d.%m.%Y %H:%M')}",
            "=" * 60,
            "",
            "📊 GENEL ÖZET",
            "-" * 40,
            f"  Toplam Evrak: {result.toplam_evrak}",
            f"  Analiz Edilen: {result.toplam_evrak}",
            f"  Tebligat Sayısı: {len(result.tebligatlar)}",
            f"  Haciz Sayısı: {len(result.hacizler)}",
            "",
            "📁 EVRAK DAĞILIMI",
            "-" * 40,
        ]
        
        for tur, sayi in sorted(result.evrak_dagilimi.items(), key=lambda x: -x[1]):
            lines.append(f"  {tur}: {sayi}")
        
        lines.extend([
            "",
            "✅ YAPILACAKLAR",
            "-" * 40,
        ])
        
        if result.aksiyonlar:
            for a in result.aksiyonlar:
                icon = "🔴" if a.oncelik == IslemDurumu.KRITIK else "🟠" if a.oncelik == IslemDurumu.UYARI else "ℹ️"
                lines.append(f"  {icon} {a.oncelik.value} {a.baslik}")
                lines.append(f"     → {a.aciklama}")
        else:
            lines.append("  ✅ Acil aksiyon gerektiren durum tespit edilmedi.")
        
        lines.extend([
            "",
            "=" * 60,
            "Bu rapor otomatik oluşturulmuştur."
        ])
        
        result.ozet_rapor = "\n".join(lines)

    def excel_olustur(self, result: DosyaAnalizSonucu, file_path: str):
        """Generate Excel report."""
        try:
            with pd.ExcelWriter(file_path, engine='openpyxl') as writer:
                # 1. Summary Sheet
                pd.DataFrame([{
                    'Tarih': self.today,
                    'Evrak Sayısı': result.toplam_evrak,
                    'Kritik İşlem': len([a for a in result.aksiyonlar if a.oncelik == IslemDurumu.KRITIK])
                }]).to_excel(writer, sheet_name='Ozet', index=False)
                
                # 2. Inventory Sheet
                if result.evraklar:
                    pd.DataFrame([{
                        'Dosya': e.dosya_adi,
                        'Tür': e.evrak_turu.value,
                        'Tarih': e.tarih.strftime('%d.%m.%Y') if e.tarih else '-'
                    } for e in result.evraklar]).to_excel(writer, sheet_name='Evrak Listesi', index=False)
                
                # 3. Actions Sheet
                if result.aksiyonlar:
                    pd.DataFrame([{
                        'Öncelik': a.oncelik.value,
                        'Konu': a.baslik,
                        'Detay': a.aciklama,
                        'Son Tarih': a.son_tarih.strftime('%d.%m.%Y') if a.son_tarih else '-'
                    } for a in result.aksiyonlar]).to_excel(writer, sheet_name='Yapilacaklar', index=False)
                    
        except Exception as e:
            logger.error(f"Excel creation failed: {e}")
            raise


# ============================================================================
# TEST RUNNER
# ============================================================================
if __name__ == "__main__":
    print("🧪 Testing UYAPDosyaAnalyzer...")
    print("=" * 50)
    
    analyzer = UYAPDosyaAnalyzer()
    
    # Test document classification
    test_cases = [
        ("89/1 haciz ihbarnamesi gönderildi", EvrakKategorisi.HACIZ_IHBARNAMESI),
        ("Tebliğ mazbatası - bizzat tebliğ edildi", EvrakKategorisi.TEBLIGAT_MAZBATA),
        ("Kıymet takdiri raporu", EvrakKategorisi.KIYMET_TAKDIRI),
        ("Random unclassifiable text", EvrakKategorisi.BILINMIYOR),
    ]
    
    for text, expected in test_cases:
        result = analyzer._classify_document(text, "test.pdf")
        status = "✅" if result == expected else "❌"
        print(f"{status} '{text[:30]}...' -> {result.value}")
        assert result == expected, f"Expected {expected}, got {result}"
    
    print("\n" + "=" * 50)
    print("✅ TÜM TESTLER BAŞARIYLA GEÇTİ!")
    print("=" * 50)
