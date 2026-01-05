#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
89/1-2-3 HACİZ İHBAR ANALİZ MODÜLÜ v11.0 (Production)
=====================================================
Banka VE 3. Şahıs (Gerçek/Tüzel Kişi) cevaplarını analiz eder.
Tek Gerçeklik Kaynağı (Single Source of Truth): Bloke tutarı SADECE burada hesaplanır.

Author: Arda & Claude
"""

import os
import re
import zipfile
import tempfile
import shutil
import logging
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from enum import Enum

# --- LOGGING SETUP ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- DEPENDENCY CHECK ---
try:
    import pdfplumber
    PDF_SUPPORT = True
except ImportError:
    PDF_SUPPORT = False
    logger.warning("pdfplumber yüklü değil. PDF analizi yapılamayacak.")

# ============================================================================
# ENUMLAR
# ============================================================================

class IhbarTuru(Enum):
    IHBAR_89_1 = "89/1 - Birinci Haciz İhbarnamesi"
    IHBAR_89_2 = "89/2 - İkinci Haciz İhbarnamesi"
    IHBAR_89_3 = "89/3 - Üçüncü Haciz İhbarnamesi"
    BILINMIYOR = "Tespit Edilemedi"

class MuhatapTuru(Enum):
    BANKA = "🏦 Banka"
    TUZEL_KISI = "🏢 Tüzel Kişi (Şirket)"
    GERCEK_KISI = "👤 Gerçek Kişi (3. Şahıs)"
    KAMU_KURUMU = "🏛️ Kamu Kurumu"
    BILINMIYOR = "❓ Tespit Edilemedi"

class CevapDurumu(Enum):
    # Banka
    BLOKE_VAR = "💰 BLOKE VAR"
    HESAP_VAR_BAKIYE_YOK = "📋 Hesap Var - Bakiye Yok"
    HESAP_YOK = "❌ Hesap Bulunamadı"
    # 3. Şahıs
    ALACAK_VAR = "💵 Alacak/Hak Var"
    ALACAK_YOK = "❌ Alacak/Hak Yok"
    ODEME_YAPILDI = "✅ Ödeme Yapıldı"
    # Ortak
    ITIRAZ = "⚖️ İtiraz Edildi"
    CEVAP_YOK = "⚠️ Cevap Gelmedi"
    PARSE_HATASI = "❓ Parse Edilemedi"

# ============================================================================
# VERİ YAPILARI
# ============================================================================

@dataclass
class HacizIhbarCevabi:
    """Tek bir 89/1-2-3 cevabı"""
    muhatap_adi: str
    muhatap_turu: MuhatapTuru
    ihbar_turu: IhbarTuru
    cevap_durumu: CevapDurumu
    cevap_tarihi: Optional[datetime]
    
    bloke_tutari: float = 0.0
    alacak_tutari: float = 0.0
    odenen_tutar: float = 0.0
    
    iban_listesi: List[str] = field(default_factory=list)
    vkn: Optional[str] = None
    tckn: Optional[str] = None
    
    aciklama: str = ""
    kaynak_dosya: str = ""
    sonraki_adim: str = ""

@dataclass
class HacizIhbarAnalizSonucu:
    """Batch analiz sonucu"""
    toplam_muhatap: int = 0
    banka_sayisi: int = 0
    tuzel_kisi_sayisi: int = 0
    gercek_kisi_sayisi: int = 0
    
    toplam_bloke: float = 0.0
    toplam_alacak: float = 0.0
    toplam_odenen: float = 0.0
    
    cevaplar: List[HacizIhbarCevabi] = field(default_factory=list)
    eksik_ihbarlar: List[Dict] = field(default_factory=list)
    
    yuklenen_dosyalar: List[str] = field(default_factory=list)
    ozet_rapor: str = ""

# ============================================================================
# ANA ANALİZ SINIFI
# ============================================================================

class HacizIhbarAnalyzer:
    
    # --- COMPILED REGEX PATTERNS (PERFORMANCE) ---
    
    # 1. Banka İsimleri
    BANKALAR = {
        'Ziraat Bankası': [r'ziraat', r't\.c\.\s*ziraat'],
        'Halkbank': [r'halk\s*bank', r'türkiye\s*halk'],
        'VakıfBank': [r'vakıf', r'vakif'],
        'İş Bankası': [r'i[şs]\s*bank', r'türkiye\s*i[şs]'],
        'Garanti BBVA': [r'garanti', r'bbva'],
        'Yapı Kredi': [r'yap[ıi]\s*kredi', r'ykb'],
        'Akbank': [r'akbank'],
        'QNB Finansbank': [r'qnb', r'finansbank'],
        'Denizbank': [r'deniz', r'denizbank'],
        'TEB': [r'teb', r'türk\s*ekonomi'],
        'Kuveyt Türk': [r'kuveyt'],
        'Albaraka': [r'albaraka'],
        'PTT': [r'ptt', r'pttbank'],
        'ING Bank': [r'ing\s*bank', r'ing'],
        'HSBC': [r'hsbc'],
        'Şekerbank': [r'şeker', r'seker'],
        'Anadolubank': [r'anadolu\s*bank'],
        'Fibabanka': [r'fiba'],
        'Odeabank': [r'odea'],
        'Türkiye Finans': [r'türkiye\s*finans'],
    }
    
    # 2. Kritik Tutarlar - CONTEXT-AWARE
    # "Bloke" kelimesine yakın tutarları arar (hem önce hem sonra)
    # IMPORTANT: Only "bloke" keyword, NOT "haciz" - because "haciz" appears in subject lines
    
    # Pattern 1: Number BEFORE "bloke" (e.g., "45.678,90 TL tutarında bloke")
    # Tight proximity (max 40 chars) to avoid false positives
    BLOKE_REGEX_BEFORE = re.compile(
        r'(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?)\s*(?:TL|₺)?\s*(?:tutarında|tutar)?.{0,40}?bloke',
        re.IGNORECASE | re.DOTALL
    )
    # Pattern 2: Number AFTER "bloke" (e.g., "bloke edilen tutar: 45.678,90")
    BLOKE_REGEX_AFTER = re.compile(
        r'bloke(?:.{0,40}?)(?:tutar[ıi]|bedel|miktar|edilen)?.{0,20}?'
        r'(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?)',
        re.IGNORECASE | re.DOTALL
    )
    
    # "Alacak" kelimesine yakın tutarları arar
    ALACAK_REGEX = re.compile(
        r'(?:alacak|borç|hak|hakediş)(?:.{0,50}?)(?:tutar[ıi]|miktar)?.{0,20}?'
        r'(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?)',
        re.IGNORECASE | re.DOTALL
    )

    # 3. Negatif Durumlar
    HESAP_YOK_PATTERNS = [
        r'hesab[ıi]\s*(?:bulun|mevcut|yok)',
        r'kayıtl[ıi]\s*(?:hesab)?\s*(?:bulun|yok)',
        r'müşteri\s*kayd[ıi]\s*yok',
        r'muhatap\s*değil'
    ]
    
    BAKIYE_YOK_PATTERNS = [
        r'bakiye(?:si)?\s*(?:bulun|yok|yetersiz)',
        r'bakiye\s*:?\s*0[,.]?00',
        r'müsait\s*bakiye\s*yok',
        r'bloke\s*(?:edilebilir|olunacak)\s*.*yok'
    ]

    # 4. TR Karakter Normalizasyon Tablosu
    TR_MAP = {
        ord('İ'): 'i', ord('I'): 'ı',
        ord('Ğ'): 'ğ', ord('Ü'): 'ü',
        ord('Ş'): 'ş', ord('Ö'): 'ö',
        ord('Ç'): 'ç'
    }

    def __init__(self):
        self.temp_dirs = []

    def _clean_text(self, text: str) -> str:
        """Türkçe karakterleri düzelt ve küçült."""
        if not text: return ""
        return text.translate(self.TR_MAP).lower()

    def _parse_amount(self, amount_str: str) -> float:
        """
        Parse Turkish monetary amounts:
        '123.456,78' -> 123456.78 (TR format: period=thousands, comma=decimal)
        '123,456.78' -> 123456.78 (US format: comma=thousands, period=decimal)
        '12.500' -> 12500.0 (TR format: period=thousands, no decimal)
        '12500' -> 12500.0 (plain number)
        """
        if not amount_str: return 0.0
        
        # Sadece rakam ve ayraçları bırak
        clean = re.sub(r'[^\d.,]', '', amount_str)
        if not clean: return 0.0
        
        # Count separators
        dot_count = clean.count('.')
        comma_count = clean.count(',')
        
        # Case 1: Both separators present - TR format (period=thousands, comma=decimal)
        if dot_count > 0 and comma_count > 0:
            # Check which comes last - that's the decimal separator
            last_dot = clean.rfind('.')
            last_comma = clean.rfind(',')
            if last_comma > last_dot:
                # TR format: 123.456,78
                clean = clean.replace('.', '').replace(',', '.')
            else:
                # US format: 123,456.78
                clean = clean.replace(',', '')
        
        # Case 2: Only periods - could be thousands separator (TR) or decimal (US)
        elif dot_count > 0:
            # If there are multiple periods, they're thousands separators
            if dot_count > 1:
                clean = clean.replace('.', '')
            # If single period and 3 digits after it, it's a thousands separator
            elif re.search(r'\.\d{3}$', clean):
                clean = clean.replace('.', '')
            # Otherwise, single period is decimal
            # (e.g., "12.5" stays as 12.5)
        
        # Case 3: Only commas - could be thousands separator (US) or decimal (TR)
        elif comma_count > 0:
            # If there are multiple commas, they're thousands separators
            if comma_count > 1:
                clean = clean.replace(',', '')
            # If single comma and 3 digits after it, it's a thousands separator
            elif re.search(r',\d{3}$', clean):
                clean = clean.replace(',', '')
            # Otherwise, single comma is likely decimal (TR format)
            else:
                clean = clean.replace(',', '.')
            
        try:
            return float(clean)
        except ValueError:
            return 0.0

    # ========================================================================
    # CORE LOGIC: BAĞLAM FARKINDALIKLI ANALİZ
    # ========================================================================

    def identify_actor(self, text: str, filename: str) -> Tuple[MuhatapTuru, str]:
        """Metin ve dosya adından muhatabı belirle."""
        text_lower = self._clean_text(text + " " + filename)
        
        # 1. BANKA KONTROLÜ
        for bank_name, patterns in self.BANKALAR.items():
            for p in patterns:
                if re.search(p, text_lower):
                    return MuhatapTuru.BANKA, bank_name
        
        # 2. ŞİRKET/TÜZEL KİŞİ KONTROLÜ
        if re.search(r'a\.?\s*ş\.?|ltd\.?\s*şti\.?|ticaret|sanayi', text_lower):
            # Şirket adını bulmaya çalış (Basit Regex)
            match = re.search(r'([a-zçğıöşü\s]+(?:a\.?\s*ş\.?|ltd\.?\s*şti\.?))', text_lower)
            name = match.group(1).title() if match else "Bilinmeyen Şirket"
            return MuhatapTuru.TUZEL_KISI, name
            
        # 3. KAMU/GERÇEK KİŞİ (Fallback)
        # Basit bir varsayım: Banka veya şirket değilse Gerçek Kişidir
        # İleride TCKN kontrolü eklenebilir.
        return MuhatapTuru.GERCEK_KISI, "Gerçek Kişi / Diğer"

    def analyze_response(self, text: str, actor_type: MuhatapTuru) -> Tuple[CevapDurumu, float, str]:
        """
        Metni analiz et ve durum/tutar döndür.
        Bu fonksiyon 'Single Source of Truth'tur.
        """
        text_clean = self._clean_text(text)
        
        # --- 1. NEGATİF DURUMLAR (Önce bunları ele) ---
        if any(re.search(p, text_clean) for p in self.HESAP_YOK_PATTERNS):
            return CevapDurumu.HESAP_YOK, 0.0, "Hesap bulunamadı"
            
        if any(re.search(p, text_clean) for p in self.BAKIYE_YOK_PATTERNS):
            return CevapDurumu.HESAP_VAR_BAKIYE_YOK, 0.0, "Hesap var, bakiye yetersiz"
            
        # --- 2. POZİTİF DURUMLAR (Tutar bulma) ---
        
        # A) BANKA İSE: Bloke ara
        if actor_type == MuhatapTuru.BANKA:
            # Özel Context Check: Sadece "bloke" kelimesinin yanındaki rakamı al
            # "Dosya borcu: 100.000 TL" gibi tuzaklara düşme
            
            # Try Pattern 1: Amount BEFORE "bloke" (e.g., "45.678,90 TL bloke")
            match = self.BLOKE_REGEX_BEFORE.search(text)
            if match:
                amount = self._parse_amount(match.group(1))
                if amount > 0:
                    return CevapDurumu.BLOKE_VAR, amount, f"Bloke Tespiti: {amount:,.2f} TL"
            
            # Try Pattern 2: Amount AFTER "bloke" (e.g., "bloke edilen: 45.678,90")
            match = self.BLOKE_REGEX_AFTER.search(text)
            if match:
                amount = self._parse_amount(match.group(1))
                if amount > 0:
                    return CevapDurumu.BLOKE_VAR, amount, f"Bloke Tespiti: {amount:,.2f} TL"
            
            # Fallback: Eğer "bloke edilmiştir" diyorsa ama regex tutar bulamadıysa
            if 'bloke edil' in text_clean:
                # Belki tutar yazmıyordur ama bloke vardır
                return CevapDurumu.BLOKE_VAR, 0.0, "Bloke edildiği belirtilmiş (Tutar okunamadı)"

        # B) DİĞER İSE: Alacak/Ödeme ara
        else:
            if 'ödeme yapıl' in text_clean:
                return CevapDurumu.ODEME_YAPILDI, 0.0, "Ödeme yapıldığı belirtilmiş"
            
            match = self.ALACAK_REGEX.search(text)
            if match:
                amount = self._parse_amount(match.group(1))
                if amount > 0:
                    return CevapDurumu.ALACAK_VAR, amount, f"Alacak Tespiti: {amount:,.2f} TL"

        return CevapDurumu.PARSE_HATASI, 0.0, "Durum net tespit edilemedi"

    # ========================================================================
    # FILE HANDLING
    # ========================================================================

    def extract_text(self, file_path: str) -> str:
        """PDF veya Text dosyasından metin çıkar."""
        ext = os.path.splitext(file_path)[1].lower()
        text = ""
        
        try:
            if ext == '.pdf' and PDF_SUPPORT:
                with pdfplumber.open(file_path) as pdf:
                    for page in pdf.pages:
                        extracted = page.extract_text()
                        if extracted: text += extracted + "\n"
            elif ext in ['.txt', '.xml', '.html']:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    text = f.read()
        except Exception as e:
            logger.error(f"Dosya okuma hatası ({file_path}): {e}")
            
        return text

    def batch_analiz(self, file_paths: List[str]) -> HacizIhbarAnalizSonucu:
        """
        Batch Analiz Motoru
        file_paths: List of ZIPs or PDFs
        """
        results = HacizIhbarAnalizSonucu()
        processed_files = []
        
        # Temp dir for extraction
        work_dir = tempfile.mkdtemp()
        self.temp_dirs.append(work_dir)
        
        try:
            # 1. Extract all ZIPs
            files_to_process = []
            
            for path in file_paths:
                if path.endswith('.zip'):
                    try:
                        with zipfile.ZipFile(path, 'r') as zf:
                            zf.extractall(work_dir)
                            # Add extracted files
                            for root, _, files in os.walk(work_dir):
                                for f in files:
                                    files_to_process.append(os.path.join(root, f))
                    except Exception as e:
                        logger.error(f"ZIP hatası ({path}): {e}")
                else:
                    files_to_process.append(path)
            
            # 2. Process Files
            for fp in files_to_process:
                filename = os.path.basename(fp)
                if filename.startswith('.') or not filename.lower().endswith(('.pdf', '.txt')):
                    continue
                    
                processed_files.append(filename)
                
                # Extract
                text = self.extract_text(fp)
                if not text: continue
                
                # Identify Actor
                actor_type, actor_name = self.identify_actor(text, filename)
                
                # Analyze Content
                status, amount, desc = self.analyze_response(text, actor_type)
                
                # Determine Ihbar Type (Basic check)
                ihbar_type = IhbarTuru.BILINMIYOR
                if '89/1' in text or 'birinci' in text.lower(): ihbar_type = IhbarTuru.IHBAR_89_1
                elif '89/2' in text or 'ikinci' in text.lower(): ihbar_type = IhbarTuru.IHBAR_89_2
                elif '89/3' in text or 'üçüncü' in text.lower(): ihbar_type = IhbarTuru.IHBAR_89_3

                # Create Result Object
                result = HacizIhbarCevabi(
                    muhatap_adi=actor_name,
                    muhatap_turu=actor_type,
                    ihbar_turu=ihbar_type,
                    cevap_durumu=status,
                    cevap_tarihi=datetime.now(), # Tarih parse eklenebilir
                    aciklama=desc,
                    kaynak_dosya=fp
                )
                
                # Assign Amounts
                if status == CevapDurumu.BLOKE_VAR:
                    result.bloke_tutari = amount
                elif status == CevapDurumu.ALACAK_VAR:
                    result.alacak_tutari = amount
                elif status == CevapDurumu.ODEME_YAPILDI:
                    result.odenen_tutar = amount
                
                results.cevaplar.append(result)
            
            # 3. Aggregate Stats
            self._aggregate_results(results, processed_files)
            
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)
            
        return results

    def _aggregate_results(self, res: HacizIhbarAnalizSonucu, files: List[str]):
        """Sonuçları topla ve rapor oluştur."""
        res.yuklenen_dosyalar = files
        res.toplam_muhatap = len(set(c.muhatap_adi for c in res.cevaplar))
        
        for c in res.cevaplar:
            if c.muhatap_turu == MuhatapTuru.BANKA: res.banka_sayisi += 1
            elif c.muhatap_turu == MuhatapTuru.TUZEL_KISI: res.tuzel_kisi_sayisi += 1
            else: res.gercek_kisi_sayisi += 1
            
            res.toplam_bloke += c.bloke_tutari
            res.toplam_alacak += c.alacak_tutari
            res.toplam_odenen += c.odenen_tutar

        # Basit Özet Rapor
        lines = [
            "=" * 60,
            f"📋 89/1-2-3 HACİZ İHBAR ANALİZ RAPORU",
            f"Tarih: {datetime.now().strftime('%d.%m.%Y %H:%M')}",
            "=" * 60,
            "",
            "📊 GENEL ÖZET",
            "-" * 40,
            f"  Toplam Muhatap: {res.toplam_muhatap}",
            f"    🏦 Banka: {res.banka_sayisi}",
            f"    🏢 Tüzel Kişi: {res.tuzel_kisi_sayisi}",
            f"    👤 Gerçek Kişi: {res.gercek_kisi_sayisi}",
            f"  Toplam Cevap: {len(res.cevaplar)}",
            f"  💰 TOPLAM BLOKE: {res.toplam_bloke:,.2f} TL",
            f"  💵 TOPLAM ALACAK (3. Şahıs): {res.toplam_alacak:,.2f} TL",
            "",
            "💰 BLOKE OLAN MUHATAPLAR",
            "-" * 40,
        ]
        
        bloke_var = [c for c in res.cevaplar if c.cevap_durumu == CevapDurumu.BLOKE_VAR]
        if bloke_var:
            for c in bloke_var:
                lines.append(f"  ✅ {c.muhatap_adi} ({c.muhatap_turu.value}): {c.bloke_tutari:,.2f} TL")
        else:
            lines.append("  Bloke kaydı bulunamadı.")
        
        lines.extend([
            "",
            "=" * 60,
            "Bu rapor otomatik oluşturulmuştur.",
            "=" * 60
        ])
        
        res.ozet_rapor = "\n".join(lines)


# ============================================================================
# UNIT TESTS (PRODUCTION CHECK)
# ============================================================================
if __name__ == "__main__":
    print("🚀 Test Modu Başlatılıyor...")
    
    analyzer = HacizIhbarAnalyzer()
    
    # Test Case 1: Complex Bank Response - Context Aware Test
    txt1 = """
    T.C. ZİRAAT BANKASI A.Ş.
    Dosya Borcu: 100.000,00 TL
    Konu: 89/1 Haciz İhbarnamesi
    İlgi sayılı yazınız üzerine borçlu hesaplarında yapılan incelemede;
    Mevcut hesaplar üzerinde 45.678,90 TL tutarında bloke tesis edilmiştir.
    Saygılarımızla.
    """
    actor_type, name = analyzer.identify_actor(txt1, "ziraat.pdf")
    status, amt, desc = analyzer.analyze_response(txt1, actor_type)
    
    print(f"\nTest 1 (Ziraat - Context Aware):")
    print(f"  Muhatap: {name} ({actor_type})")
    print(f"  Durum: {status} (Beklenen: BLOKE_VAR)")
    print(f"  Tutar: {amt} (Beklenen: 45678.90, NOT 100000.00)")
    assert status == CevapDurumu.BLOKE_VAR
    assert amt == 45678.90, f"Expected 45678.90, got {amt}"
    print("  ✅ PASSED - Dosya borcu tuzağına düşmedi!")
    
    # Test Case 2: Negative Bank Response
    txt2 = """
    VAKIFBANK
    İlgi yazınızda belirtilen şahsın bankamız nezdinde herhangi bir hesabı bulunmamaktadır.
    """
    actor_type, name = analyzer.identify_actor(txt2, "vakif.pdf")
    status, amt, desc = analyzer.analyze_response(txt2, actor_type)
    
    print(f"\nTest 2 (Vakıf - Negatif):")
    print(f"  Durum: {status} (Beklenen: HESAP_YOK)")
    assert status == CevapDurumu.HESAP_YOK
    print("  ✅ PASSED")
    
    # Test Case 3: Company Debt (3. Şahıs)
    txt3 = """
    ABC İNŞAAT SANAYİ TİCARET LTD. ŞTİ.
    Şirket kayıtlarımızda borçlunun 12.500 TL hakediş alacağı mevcuttur.
    """
    actor_type, name = analyzer.identify_actor(txt3, "abc_ins.pdf")
    status, amt, desc = analyzer.analyze_response(txt3, actor_type)
    
    print(f"\nTest 3 (Şirket Alacak):")
    print(f"  Muhatap: {name}")
    print(f"  Durum: {status} (Beklenen: ALACAK_VAR)")
    print(f"  Tutar: {amt} (Beklenen: 12500.0)")
    assert status == CevapDurumu.ALACAK_VAR
    assert amt == 12500.0
    print("  ✅ PASSED")
    
    # Test Case 4: Bakiye Yok
    txt4 = """
    GARANTİ BBVA
    Borçlunun hesabında bakiye bulunmamaktadır.
    Bloke edilebilir tutar: 0,00 TL
    """
    actor_type, name = analyzer.identify_actor(txt4, "garanti.pdf")
    status, amt, desc = analyzer.analyze_response(txt4, actor_type)
    
    print(f"\nTest 4 (Garanti - Bakiye Yok):")
    print(f"  Durum: {status} (Beklenen: HESAP_VAR_BAKIYE_YOK)")
    assert status == CevapDurumu.HESAP_VAR_BAKIYE_YOK
    print("  ✅ PASSED")

    print("\n" + "=" * 50)
    print("✅ TÜM TESTLER BAŞARIYLA GEÇTİ!")
    print("=" * 50)
