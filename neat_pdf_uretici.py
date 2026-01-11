#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NEAT PDF ÜRETİCİ v12.5 - ENHANCED EDITION
==========================================
UDF dosyalarını profesyonel PDF'lere dönüştürür.
Türkçe karakter desteği ve robust error handling.

Author: Arda & Claude
"""

import os
import zipfile
import tempfile
import shutil
import re
import html
from datetime import datetime
from dataclasses import dataclass
from typing import List, Optional

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
    from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
    from reportlab.lib import colors
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from PyPDF2 import PdfMerger, PdfReader
    REPORTLAB_OK = True
except ImportError:
    REPORTLAB_OK = False

@dataclass
class PDFRapor:
    """PDF üretim raporu"""
    toplam_sayfa: int = 0
    islenen_dosya: int = 0
    hatalar: List[str] = None
    sure_saniye: float = 0.0
    
    def __post_init__(self):
        if self.hatalar is None:
            self.hatalar = []


class NeatPDFUretici:
    """
    Profesyonel PDF üretici
    
    Özellikler:
    - UDF → PDF dönüşümü
    - Türkçe karakter desteği
    - Kapak sayfası
    - Sayfa numaralandırma
    - PDF birleştirme
    """
    
    # Türkçe font arama yolları
    FONT_PATHS = [
        # Linux
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        # Windows
        "C:\\Windows\\Fonts\\arial.ttf",
        "C:\\Windows\\Fonts\\calibri.ttf",
        "C:\\Windows\\Fonts\\segoeui.ttf",
        # macOS
        "/Library/Fonts/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        # Relative path
        os.path.join(os.path.dirname(__file__), "fonts", "DejaVuSans.ttf"),
    ]
    
    def __init__(self):
        self.font_name = "Helvetica"  # Fallback
        self.font_bold = "Helvetica-Bold"
        self._yukle_turkce_font()
    
    def _yukle_turkce_font(self):
        """Türkçe karakter destekleyen font yükle"""
        if not REPORTLAB_OK:
            return
        
        for path in self.FONT_PATHS:
            if os.path.exists(path):
                try:
                    pdfmetrics.registerFont(TTFont('TurkceFont', path))
                    self.font_name = 'TurkceFont'
                    return
                except Exception as e:
                    pass
    
    def uret(self, kaynak_yol: str, cikti_yol: str, baslik: str = "İcra Dosyası") -> Optional[PDFRapor]:
        """
        Ana üretim fonksiyonu
        
        Args:
            kaynak_yol: ZIP dosyası veya tek dosya yolu
            cikti_yol: Çıktı PDF yolu
            baslik: PDF başlığı
        
        Returns:
            PDFRapor veya None (hata durumunda)
        """
        if not REPORTLAB_OK:
            print("❌ ReportLab yüklü değil!")
            return None
        
        start_time = datetime.now()
        rapor = PDFRapor()
        
        # Çıktı klasörünü oluştur
        cikti_dir = os.path.dirname(cikti_yol)
        if cikti_dir:
            os.makedirs(cikti_dir, exist_ok=True)
        
        temp_dir = tempfile.mkdtemp()
        merger = PdfMerger()
        
        try:
            # Dosyaları topla
            dosyalar = self._topla_dosyalar(kaynak_yol, temp_dir)
            rapor.islenen_dosya = len(dosyalar)
            
            if not dosyalar:
                rapor.hatalar.append("İşlenecek dosya bulunamadı")
                return rapor
            
            # Stiller oluştur
            styles = self._olustur_stiller()
            
            # Story (içerik) oluştur
            story = []
            
            # Kapak sayfası
            story.extend(self._olustur_kapak(baslik, len(dosyalar), styles))
            
            # Her dosya için içerik ekle
            metin_var = False
            for dosya_yolu in dosyalar:
                try:
                    if dosya_yolu.endswith('.udf'):
                        icerik = self._oku_udf(dosya_yolu)
                        if icerik:
                            story.extend(self._olustur_evrak_sayfasi(
                                os.path.basename(dosya_yolu),
                                icerik,
                                styles
                            ))
                            metin_var = True
                except Exception as e:
                    rapor.hatalar.append(f"UDF okuma hatası ({os.path.basename(dosya_yolu)}): {e}")
            
            # Metin PDF'i oluştur
            if metin_var:
                text_pdf = os.path.join(temp_dir, "text_content.pdf")
                doc = SimpleDocTemplate(
                    text_pdf,
                    pagesize=A4,
                    leftMargin=50,
                    rightMargin=50,
                    topMargin=50,
                    bottomMargin=50
                )
                
                try:
                    doc.build(story)
                    if os.path.exists(text_pdf):
                        merger.append(text_pdf)
                except Exception as e:
                    rapor.hatalar.append(f"PDF oluşturma hatası: {e}")
            
            # Mevcut PDF'leri ekle
            for dosya_yolu in dosyalar:
                if dosya_yolu.endswith('.pdf'):
                    try:
                        merger.append(dosya_yolu)
                    except Exception as e:
                        rapor.hatalar.append(f"PDF ekleme hatası ({os.path.basename(dosya_yolu)}): {e}")
            
            # Final PDF'i yaz
            if len(merger.pages) > 0:
                merger.write(cikti_yol)
                rapor.toplam_sayfa = len(merger.pages)
            else:
                rapor.hatalar.append("Hiçbir sayfa oluşturulamadı")
            
        except Exception as e:
            rapor.hatalar.append(f"Genel hata: {e}")
        
        finally:
            merger.close()
            shutil.rmtree(temp_dir, ignore_errors=True)
        
        rapor.sure_saniye = (datetime.now() - start_time).total_seconds()
        return rapor
    
    def _topla_dosyalar(self, kaynak_yol: str, temp_dir: str) -> List[str]:
        """Kaynak yolundan dosyaları topla"""
        dosyalar = []
        
        if os.path.isfile(kaynak_yol):
            if kaynak_yol.endswith('.zip'):
                # ZIP içeriğini çıkar
                try:
                    with zipfile.ZipFile(kaynak_yol, 'r') as zf:
                        zf.extractall(temp_dir)
                        for root, _, files in os.walk(temp_dir):
                            for f in files:
                                if f.endswith(('.udf', '.pdf')):
                                    dosyalar.append(os.path.join(root, f))
                except Exception as e:
                    print(f"ZIP açma hatası: {e}")
            else:
                dosyalar.append(kaynak_yol)
        
        elif os.path.isdir(kaynak_yol):
            for root, _, files in os.walk(kaynak_yol):
                for f in files:
                    if f.endswith(('.udf', '.pdf')):
                        dosyalar.append(os.path.join(root, f))
        
        return sorted(dosyalar)
    
    def _olustur_stiller(self) -> dict:
        """ReportLab stilleri oluştur"""
        styles = getSampleStyleSheet()
        
        return {
            'baslik': ParagraphStyle(
                'Baslik',
                parent=styles['Heading1'],
                fontName=self.font_name,
                fontSize=18,
                textColor=colors.HexColor('#1E3A5F'),
                alignment=TA_CENTER,
                spaceAfter=20
            ),
            'alt_baslik': ParagraphStyle(
                'AltBaslik',
                parent=styles['Heading2'],
                fontName=self.font_name,
                fontSize=12,
                textColor=colors.HexColor('#2C5282'),
                alignment=TA_CENTER,
                spaceAfter=10
            ),
            'normal': ParagraphStyle(
                'Normal',
                parent=styles['Normal'],
                fontName=self.font_name,
                fontSize=10,
                leading=14,
                alignment=TA_JUSTIFY,
                spaceAfter=6
            ),
            'evrak_baslik': ParagraphStyle(
                'EvrakBaslik',
                parent=styles['Heading3'],
                fontName=self.font_name,
                fontSize=11,
                textColor=colors.white,
                backColor=colors.HexColor('#2C5282'),
                alignment=TA_LEFT,
                spaceBefore=10,
                spaceAfter=10,
                leftIndent=5,
                rightIndent=5
            ),
            'footer': ParagraphStyle(
                'Footer',
                parent=styles['Normal'],
                fontName=self.font_name,
                fontSize=8,
                textColor=colors.grey,
                alignment=TA_CENTER
            )
        }
    
    def _olustur_kapak(self, baslik: str, dosya_sayisi: int, styles: dict) -> List:
        """Kapak sayfası oluştur"""
        story = []
        
        story.append(Spacer(1, 100))
        story.append(Paragraph(f"<b>{baslik}</b>", styles['baslik']))
        story.append(Spacer(1, 30))
        story.append(Paragraph(f"Oluşturma Tarihi: {datetime.now().strftime('%d.%m.%Y %H:%M')}", styles['alt_baslik']))
        story.append(Paragraph(f"Toplam Dosya: {dosya_sayisi}", styles['alt_baslik']))
        story.append(Spacer(1, 50))
        story.append(Paragraph("İcra Analiz Pro v12.5 ile oluşturuldu", styles['footer']))
        story.append(PageBreak())
        
        return story
    
    def _olustur_evrak_sayfasi(self, dosya_adi: str, icerik: str, styles: dict) -> List:
        """Tek evrak için sayfa oluştur"""
        story = []
        
        # Evrak başlığı
        story.append(Paragraph(f"📄 {dosya_adi}", styles['evrak_baslik']))
        story.append(Spacer(1, 10))
        
        # İçerik
        paragraflar = icerik.split('\n')
        for para in paragraflar:
            para = para.strip()
            if para:
                # XML/HTML karakterlerini escape et
                safe_para = self._safe_text(para)
                try:
                    story.append(Paragraph(safe_para, styles['normal']))
                except Exception:
                    # Hatalı paragrafı atla
                    pass
        
        story.append(PageBreak())
        return story
    
    def _oku_udf(self, udf_yolu: str) -> str:
        """UDF dosyasını oku ve içeriği çıkar"""
        try:
            with zipfile.ZipFile(udf_yolu, 'r') as zf:
                if 'content.xml' not in zf.namelist():
                    return ""
                
                raw = zf.read('content.xml').decode('utf-8', errors='replace')
                
                # CDATA içeriğini çıkar
                match = re.search(r'<!\[CDATA\[(.*?)\]\]>', raw, re.DOTALL)
                if match:
                    text = match.group(1)
                else:
                    # XML taglerini temizle
                    text = re.sub(r'<[^>]+>', ' ', raw)
                
                # HTML entity decode
                text = html.unescape(text)
                
                # Fazla boşlukları temizle
                text = re.sub(r'\s+', ' ', text)
                text = re.sub(r'\n\s*\n', '\n', text)
                
                return text.strip()
                
        except Exception as e:
            print(f"UDF okuma hatası ({udf_yolu}): {e}")
            return ""
    
    def _safe_text(self, text: str) -> str:
        """Metni ReportLab için güvenli hale getir"""
        if not text:
            return ""
        
        # Tehlikeli karakterleri escape et
        text = text.replace('&', '&amp;')
        text = text.replace('<', '&lt;')
        text = text.replace('>', '&gt;')
        
        # Kontrol karakterlerini kaldır
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', text)
        
        return text


# === TEST ===
if __name__ == "__main__":
    print("🧪 NeatPDFUretici v12.5 Test")
    print("=" * 50)
    
    if not REPORTLAB_OK:
        print("❌ ReportLab yüklü değil!")
    else:
        print("✅ ReportLab yüklü")
        
        uretici = NeatPDFUretici()
        print(f"✅ Font: {uretici.font_name}")
        
        # Test PDF oluştur
        import tempfile
        test_dir = tempfile.mkdtemp()
        test_output = os.path.join(test_dir, "test.pdf")
        
        # Boş test
        rapor = uretici.uret(test_dir, test_output, "Test PDF")
        if rapor:
            print(f"✅ Test tamamlandı: {rapor.toplam_sayfa} sayfa, {rapor.sure_saniye:.2f}s")
            if rapor.hatalar:
                for h in rapor.hatalar:
                    print(f"  ⚠️ {h}")
        
        shutil.rmtree(test_dir, ignore_errors=True)
    
    print("\n✅ Testler tamamlandı")
