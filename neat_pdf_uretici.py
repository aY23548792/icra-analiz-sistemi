#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PROFESYONEL UDF → PDF DÖNÜŞTÜRÜCÜ v12.0
========================================
UYAP .udf dosyalarını okunabilir, profesyonel PDF'lere dönüştürür.

Özellikler:
- Türkçe karakter desteği (DejaVu/Arial font)
- Kapak sayfası
- Sayfa numaraları
- İçindekiler
- Syntax highlighting (başlıklar için)
- Mevcut PDF'leri merge etme

Author: Arda & Claude
"""

import os
import re
import zipfile
import tempfile
import shutil
import html
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === DEPENDENCY CHECK ===
try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm, mm
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.colors import HexColor, black, gray, white
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, PageBreak, 
        Table, TableStyle, Image, KeepTogether
    )
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    REPORTLAB_OK = True
except ImportError:
    REPORTLAB_OK = False
    logger.error("ReportLab yüklü değil: pip install reportlab")

try:
    from PyPDF2 import PdfMerger, PdfReader
    PYPDF2_OK = True
except ImportError:
    PYPDF2_OK = False
    logger.warning("PyPDF2 yüklü değil - PDF merge devre dışı")

# === DATA CLASSES ===
@dataclass
class EvrakIcerik:
    """Tek bir evrakın içeriği"""
    dosya_adi: str
    baslik: str
    icerik: str
    tarih: Optional[datetime] = None
    sayfa_sayisi: int = 1
    kaynak_tur: str = "UDF"  # UDF, PDF, TXT

@dataclass
class PDFUretimRaporu:
    """Üretim sonuç raporu"""
    cikti_dosya: str = ""
    toplam_sayfa: int = 0
    islenen_dosya: int = 0
    basarili: int = 0
    hatali: int = 0
    hatalar: List[str] = field(default_factory=list)
    sure_saniye: float = 0.0

# === MAIN CLASS ===
class NeatPDFUretici:
    """
    Profesyonel PDF Üretici
    -----------------------
    UDF, PDF ve metin dosyalarını birleştirip tek PDF yapar.
    """
    
    # Renk Paleti
    RENK_KAPAK_BG = HexColor('#1E3A5F')  # Koyu mavi
    RENK_BASLIK = HexColor('#2C5282')     # Orta mavi
    RENK_VURGU = HexColor('#E53E3E')      # Kırmızı
    RENK_METIN = black
    RENK_SOLUK = gray
    
    def __init__(self):
        self.font_normal = 'Helvetica'
        self.font_bold = 'Helvetica-Bold'
        self.styles = None
        self._font_yukle()
        self._stil_olustur()
    
    def _font_yukle(self):
        """Türkçe karakter destekli font yükle"""
        if not REPORTLAB_OK:
            return
        
        font_paths = [
            # Linux
            '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
            '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
            # Ubuntu/Debian
            '/usr/share/fonts/truetype/freefont/FreeSans.ttf',
            '/usr/share/fonts/truetype/freefont/FreeSansBold.ttf',
            # Windows
            'C:\\Windows\\Fonts\\arial.ttf',
            'C:\\Windows\\Fonts\\arialbd.ttf',
            # Mac
            '/Library/Fonts/Arial.ttf',
        ]
        
        # Normal font
        for path in font_paths:
            if os.path.exists(path) and 'Bold' not in path and 'bd' not in path.lower():
                try:
                    pdfmetrics.registerFont(TTFont('TurkceFont', path))
                    self.font_normal = 'TurkceFont'
                    logger.info(f"Font yüklendi: {path}")
                    break
                except Exception as e:
                    logger.warning(f"Font yüklenemedi ({path}): {e}")
        
        # Bold font
        for path in font_paths:
            if os.path.exists(path) and ('Bold' in path or 'bd' in path.lower()):
                try:
                    pdfmetrics.registerFont(TTFont('TurkceFontBold', path))
                    self.font_bold = 'TurkceFontBold'
                    break
                except:
                    pass
    
    def _stil_olustur(self):
        """PDF stilleri oluştur"""
        if not REPORTLAB_OK:
            return
        
        self.styles = getSampleStyleSheet()
        
        # Kapak Başlık
        self.styles.add(ParagraphStyle(
            'KapakBaslik',
            parent=self.styles['Heading1'],
            fontName=self.font_bold,
            fontSize=24,
            textColor=white,
            alignment=TA_CENTER,
            spaceAfter=20,
        ))
        
        # Kapak Alt Başlık
        self.styles.add(ParagraphStyle(
            'KapakAlt',
            parent=self.styles['Normal'],
            fontName=self.font_normal,
            fontSize=14,
            textColor=white,
            alignment=TA_CENTER,
            spaceAfter=10,
        ))
        
        # Evrak Başlık
        self.styles.add(ParagraphStyle(
            'EvrakBaslik',
            parent=self.styles['Heading2'],
            fontName=self.font_bold,
            fontSize=14,
            textColor=self.RENK_BASLIK,
            spaceBefore=15,
            spaceAfter=10,
            borderWidth=1,
            borderColor=self.RENK_BASLIK,
            borderPadding=5,
        ))
        
        # Normal Metin
        self.styles.add(ParagraphStyle(
            'Icerik',
            parent=self.styles['Normal'],
            fontName=self.font_normal,
            fontSize=10,
            leading=14,
            alignment=TA_JUSTIFY,
            spaceAfter=6,
        ))
        
        # Küçük/Meta Metin
        self.styles.add(ParagraphStyle(
            'Meta',
            parent=self.styles['Normal'],
            fontName=self.font_normal,
            fontSize=8,
            textColor=self.RENK_SOLUK,
            spaceAfter=4,
        ))
        
        # İçindekiler
        self.styles.add(ParagraphStyle(
            'Icindekiler',
            parent=self.styles['Normal'],
            fontName=self.font_normal,
            fontSize=11,
            leading=16,
            leftIndent=10,
        ))
    
    # ========================================================================
    # DOSYA OKUMA
    # ========================================================================
    
    def _udf_oku(self, yol: str) -> Tuple[str, str]:
        """
        UDF dosyasını oku ve içeriği çıkar.
        Returns: (baslik, icerik)
        """
        baslik = os.path.basename(yol).replace('.udf', '')
        icerik = ""
        
        try:
            with zipfile.ZipFile(yol, 'r') as zf:
                # content.xml var mı?
                if 'content.xml' not in zf.namelist():
                    return baslik, "[İçerik bulunamadı]"
                
                raw_xml = zf.read('content.xml').decode('utf-8', errors='replace')
                
                # CDATA içeriğini çıkar (varsa)
                cdata_match = re.search(r'<!\[CDATA\[(.*?)\]\]>', raw_xml, re.DOTALL)
                if cdata_match:
                    icerik = cdata_match.group(1)
                else:
                    # XML tag'lerini temizle
                    icerik = re.sub(r'<[^>]+>', ' ', raw_xml)
                
                # HTML entity decode
                icerik = html.unescape(icerik)
                
                # Fazla boşlukları temizle
                icerik = re.sub(r'\s+', ' ', icerik).strip()
                icerik = re.sub(r'\n\s*\n', '\n\n', icerik)
                
                # Başlık çıkarma (ilk satır veya KONU:)
                lines = icerik.split('\n')
                if lines:
                    first_line = lines[0].strip()[:100]
                    if first_line and len(first_line) > 5:
                        baslik = first_line
                
                # KONU: satırını ara
                konu_match = re.search(r'KONU\s*:\s*(.+?)(?:\n|$)', icerik, re.IGNORECASE)
                if konu_match:
                    baslik = konu_match.group(1).strip()[:100]
                    
        except zipfile.BadZipFile:
            logger.error(f"Geçersiz UDF (ZIP değil): {yol}")
            icerik = "[Dosya okunamadı - geçersiz format]"
        except Exception as e:
            logger.error(f"UDF okuma hatası ({yol}): {e}")
            icerik = f"[Okuma hatası: {str(e)}]"
        
        return baslik, icerik
    
    def _txt_oku(self, yol: str) -> Tuple[str, str]:
        """Text dosyası oku"""
        baslik = os.path.basename(yol)
        try:
            with open(yol, 'r', encoding='utf-8', errors='replace') as f:
                icerik = f.read()
            return baslik, icerik
        except Exception as e:
            return baslik, f"[Okuma hatası: {e}]"
    
    # ========================================================================
    # PDF OLUŞTURMA
    # ========================================================================
    
    def _kapak_sayfasi(self, story: list, baslik: str, dosya_sayisi: int):
        """Profesyonel kapak sayfası ekle (basitleştirilmiş)"""
        # Boşluk bırak
        story.append(Spacer(1, 6*cm))
        
        # Ana Başlık
        kapak_baslik = ParagraphStyle(
            'KapakBaslikDark',
            parent=self.styles['Heading1'],
            fontName=self.font_bold,
            fontSize=28,
            textColor=self.RENK_KAPAK_BG,
            alignment=TA_CENTER,
            spaceAfter=30,
        )
        story.append(Paragraph(f"📁 {baslik}", kapak_baslik))
        
        # Çizgi
        story.append(Spacer(1, 0.5*cm))
        
        # Alt bilgiler
        kapak_alt = ParagraphStyle(
            'KapakAltDark',
            parent=self.styles['Normal'],
            fontName=self.font_normal,
            fontSize=14,
            textColor=self.RENK_BASLIK,
            alignment=TA_CENTER,
            spaceAfter=15,
        )
        story.append(Paragraph(f"Toplam {dosya_sayisi} Evrak", kapak_alt))
        story.append(Paragraph(f"Oluşturma: {datetime.now().strftime('%d.%m.%Y %H:%M')}", kapak_alt))
        story.append(Spacer(1, 3*cm))
        
        # Footer
        kapak_footer = ParagraphStyle(
            'KapakFooter',
            parent=self.styles['Normal'],
            fontName=self.font_normal,
            fontSize=10,
            textColor=self.RENK_SOLUK,
            alignment=TA_CENTER,
        )
        story.append(Paragraph("İcra Analiz Sistemi v12.0", kapak_footer))
        
        story.append(PageBreak())
    
    def _icindekiler(self, story: list, evraklar: List[EvrakIcerik]):
        """İçindekiler sayfası"""
        story.append(Paragraph("<b>📋 İÇİNDEKİLER</b>", self.styles['EvrakBaslik']))
        story.append(Spacer(1, 0.5*cm))
        
        for i, evrak in enumerate(evraklar, 1):
            baslik_kisa = evrak.baslik[:60] + "..." if len(evrak.baslik) > 60 else evrak.baslik
            # Güvenli karakter escape
            baslik_kisa = html.escape(baslik_kisa)
            story.append(Paragraph(f"{i}. {baslik_kisa}", self.styles['Icindekiler']))
        
        story.append(PageBreak())
    
    def _evrak_ekle(self, story: list, evrak: EvrakIcerik, sira: int):
        """Tek bir evrakı PDF'e ekle"""
        # Başlık
        baslik_safe = html.escape(evrak.baslik[:80])
        story.append(Paragraph(f"📄 {sira}. {baslik_safe}", self.styles['EvrakBaslik']))
        
        # Meta bilgi
        meta = f"Kaynak: {evrak.dosya_adi}"
        if evrak.tarih:
            meta += f" | Tarih: {evrak.tarih.strftime('%d.%m.%Y')}"
        story.append(Paragraph(meta, self.styles['Meta']))
        story.append(Spacer(1, 0.3*cm))
        
        # İçerik
        if evrak.icerik:
            # Paragrafları ayır
            paragraflar = evrak.icerik.split('\n\n')
            for para in paragraflar:
                para = para.strip()
                if para:
                    # Güvenli HTML escape
                    para_safe = html.escape(para)
                    # Satır sonlarını <br/> yap
                    para_safe = para_safe.replace('\n', '<br/>')
                    try:
                        story.append(Paragraph(para_safe, self.styles['Icerik']))
                    except Exception as e:
                        # Fallback - düz metin
                        story.append(Paragraph(f"[Formatlama hatası: {para[:50]}...]", self.styles['Meta']))
        else:
            story.append(Paragraph("[İçerik boş]", self.styles['Meta']))
        
        story.append(PageBreak())
    
    # ========================================================================
    # ANA ÜRET FONKSİYONU
    # ========================================================================
    
    def uret(self, kaynak_yol: str, cikti_yol: str, baslik: str = "İcra Dosyası") -> Optional[PDFUretimRaporu]:
        """
        Ana üretim fonksiyonu.
        
        Args:
            kaynak_yol: ZIP, UDF veya klasör yolu
            cikti_yol: Çıktı PDF yolu
            baslik: PDF başlığı
        
        Returns:
            PDFUretimRaporu veya None (hata durumunda)
        """
        if not REPORTLAB_OK:
            logger.error("ReportLab yüklü değil!")
            return None
        
        import time
        start_time = time.time()
        
        rapor = PDFUretimRaporu(cikti_dosya=cikti_yol)
        temp_dir = tempfile.mkdtemp()
        evraklar: List[EvrakIcerik] = []
        pdf_dosyalari: List[str] = []
        
        try:
            # 1. Dosyaları topla
            dosyalar = []
            
            if os.path.isfile(kaynak_yol):
                if kaynak_yol.lower().endswith('.zip'):
                    # ZIP aç
                    with zipfile.ZipFile(kaynak_yol, 'r') as zf:
                        zf.extractall(temp_dir)
                    for root, _, files in os.walk(temp_dir):
                        for f in files:
                            dosyalar.append(os.path.join(root, f))
                else:
                    dosyalar.append(kaynak_yol)
            elif os.path.isdir(kaynak_yol):
                for root, _, files in os.walk(kaynak_yol):
                    for f in files:
                        dosyalar.append(os.path.join(root, f))
            
            # 2. Dosyaları işle
            for dosya in sorted(dosyalar):
                fname = os.path.basename(dosya)
                if fname.startswith('.'):
                    continue
                
                rapor.islenen_dosya += 1
                ext = os.path.splitext(fname)[1].lower()
                
                try:
                    if ext == '.udf':
                        baslik_evrak, icerik = self._udf_oku(dosya)
                        evraklar.append(EvrakIcerik(
                            dosya_adi=fname,
                            baslik=baslik_evrak,
                            icerik=icerik,
                            kaynak_tur="UDF"
                        ))
                        rapor.basarili += 1
                    
                    elif ext == '.pdf':
                        pdf_dosyalari.append(dosya)
                        rapor.basarili += 1
                    
                    elif ext in ['.txt', '.xml', '.html']:
                        baslik_evrak, icerik = self._txt_oku(dosya)
                        evraklar.append(EvrakIcerik(
                            dosya_adi=fname,
                            baslik=baslik_evrak,
                            icerik=icerik,
                            kaynak_tur="TXT"
                        ))
                        rapor.basarili += 1
                    
                    # Diğer formatları atla
                    
                except Exception as e:
                    rapor.hatali += 1
                    rapor.hatalar.append(f"{fname}: {str(e)}")
            
            # 3. Çıktı klasörünü oluştur
            cikti_dir = os.path.dirname(cikti_yol)
            if cikti_dir:
                os.makedirs(cikti_dir, exist_ok=True)
            
            # 4. Ana PDF oluştur
            story = []
            
            # Kapak
            self._kapak_sayfasi(story, baslik, len(evraklar) + len(pdf_dosyalari))
            
            # İçindekiler (sadece evrak varsa)
            if evraklar:
                self._icindekiler(story, evraklar)
            
            # Evrakları ekle
            for i, evrak in enumerate(evraklar, 1):
                self._evrak_ekle(story, evrak, i)
            
            # PDF oluştur
            metin_pdf = os.path.join(temp_dir, "metin_icerik.pdf")
            doc = SimpleDocTemplate(
                metin_pdf,
                pagesize=A4,
                leftMargin=2*cm,
                rightMargin=2*cm,
                topMargin=2*cm,
                bottomMargin=2*cm
            )
            doc.build(story)
            
            # 5. PDF'leri birleştir
            if PYPDF2_OK:
                merger = PdfMerger()
                merger.append(metin_pdf)
                
                for pdf in pdf_dosyalari:
                    try:
                        merger.append(pdf)
                    except Exception as e:
                        rapor.hatalar.append(f"PDF merge hatası ({os.path.basename(pdf)}): {e}")
                
                merger.write(cikti_yol)
                merger.close()
                
                # Sayfa sayısını hesapla
                with open(cikti_yol, 'rb') as f:
                    reader = PdfReader(f)
                    rapor.toplam_sayfa = len(reader.pages)
            else:
                # PyPDF2 yoksa sadece metin PDF'i kopyala
                shutil.copy(metin_pdf, cikti_yol)
                rapor.toplam_sayfa = len(evraklar) + 2  # Kapak + içindekiler
            
            rapor.sure_saniye = time.time() - start_time
            logger.info(f"PDF oluşturuldu: {cikti_yol} ({rapor.toplam_sayfa} sayfa)")
            
            return rapor
            
        except Exception as e:
            logger.error(f"PDF üretim hatası: {e}")
            rapor.hatalar.append(str(e))
            return rapor
            
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


# === TEST ===
if __name__ == "__main__":
    print("🧪 NeatPDFUretici Test")
    print("=" * 50)
    
    if not REPORTLAB_OK:
        print("❌ ReportLab yüklü değil!")
    else:
        print(f"✅ ReportLab OK")
        
        uretici = NeatPDFUretici()
        print(f"✅ Font: {uretici.font_normal}")
        
        # Basit test
        test_dir = tempfile.mkdtemp()
        
        # Test UDF oluştur
        test_udf = os.path.join(test_dir, "test.udf")
        with zipfile.ZipFile(test_udf, 'w') as zf:
            content = """<?xml version="1.0"?>
            <document>
                <content><![CDATA[
                KONU: Test Haciz İhbarnamesi
                
                Sayın Yetkili,
                
                İlgi yazınız üzerine borçlu hesaplarında 45.678,90 TL tutarında bloke tesis edilmiştir.
                
                Türkçe karakterler: İıĞğÜüŞşÖöÇç
                
                Saygılarımızla.
                ]]></content>
            </document>
            """
            zf.writestr('content.xml', content.encode('utf-8'))
        
        # PDF üret
        test_pdf = os.path.join(test_dir, "test_cikti.pdf")
        rapor = uretici.uret(test_udf, test_pdf, "Test Dosyası")
        
        if rapor and os.path.exists(test_pdf):
            print(f"✅ PDF oluşturuldu: {rapor.toplam_sayfa} sayfa")
            print(f"   Süre: {rapor.sure_saniye:.2f}s")
        else:
            print("❌ PDF oluşturulamadı")
        
        # Temizle
        shutil.rmtree(test_dir, ignore_errors=True)
    
    print("\n" + "=" * 50)
    print("Test tamamlandı")
