#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NEAT PDF ÜRETİCİ v6.1 - SMART FORMATTER
=======================================
UDF metinlerini analiz edip UYAP benzeri layout (düzen) oluşturur.
"""

import os
import re
import zipfile
import tempfile
import shutil
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Tuple

# Kütüphane Kontrolleri
REPORTLAB_OK = False
PYPDF2_OK = False
PIL_OK = False

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm, mm
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY, TA_RIGHT
    from reportlab.lib.colors import black, gray, HexColor
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from PyPDF2 import PdfMerger, PdfReader
    from PIL import Image
    REPORTLAB_OK = True
    PYPDF2_OK = True
    PIL_OK = True
except ImportError:
    pass

@dataclass
class NeatPDFRapor:
    cikti_dosya: str = ""
    toplam_sayfa: int = 0
    islenen_dosya: int = 0
    hatalar: List[str] = field(default_factory=list)
    sure_saniye: float = 0.0

class NeatPDFUretici:
    
    def __init__(self):
        self.temp_dir = None
        self.styles = None
        self.font_name = 'Helvetica'
        
        # Windows/Linux Font Ayarı
        self._font_yukle()
        if REPORTLAB_OK:
            self._stiller_olustur()

    def _font_yukle(self):
        """Türkçe karakter destekleyen fontları dener"""
        font_yollari = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
            "arial.ttf",
            "C:\\Windows\\Fonts\\arial.ttf"
        ]
        for yol in font_yollari:
            if os.path.exists(yol):
                try:
                    pdfmetrics.registerFont(TTFont('TrFont', yol))
                    # Bold varyasyonu (basitçe aynısını kullanıyoruz hata almamak için)
                    pdfmetrics.registerFont(TTFont('TrFontBd', yol)) 
                    self.font_name = 'TrFont'
                    return
                except:
                    pass

    def _stiller_olustur(self):
        s = getSampleStyleSheet()
        
        # Başlıklar (T.C., Mahkeme Adı)
        s.add(ParagraphStyle(name='UyapHeader', fontName=self.font_name, fontSize=12, leading=16, alignment=TA_CENTER, spaceAfter=2))
        
        # Etiketler (Davacı:, Konu:)
        s.add(ParagraphStyle(name='UyapLabel', fontName=self.font_name, fontSize=10, leading=14, alignment=TA_LEFT, spaceAfter=2))
        
        # Normal Metin
        s.add(ParagraphStyle(name='UyapNormal', fontName=self.font_name, fontSize=10, leading=14, alignment=TA_JUSTIFY, spaceAfter=4))
        
        # İmza/Tarih (Sağa Yaslı)
        s.add(ParagraphStyle(name='UyapRight', fontName=self.font_name, fontSize=10, leading=14, alignment=TA_RIGHT, spaceAfter=2))
        
        # Belge Başlığı (TALEP, KARAR)
        s.add(ParagraphStyle(name='UyapTitle', fontName=self.font_name, fontSize=11, leading=14, alignment=TA_CENTER, spaceBefore=10, spaceAfter=10))

        self.styles = s

    def _udf_oku(self, udf_path: str) -> str:
        """UDF (XML) içeriğini okur"""
        try:
            with zipfile.ZipFile(udf_path, 'r') as zf:
                if 'content.xml' in zf.namelist():
                    xml_data = zf.read('content.xml').decode('utf-8', errors='ignore')
                    # CDATA içini al
                    matches = re.findall(r'<!\[CDATA\[(.*?)\]\]>', xml_data, re.DOTALL)
                    if matches:
                        return "\n".join(matches)
                    else:
                        # CDATA yoksa tagleri temizle
                        return re.sub(r'<[^>]+>', '', xml_data)
        except:
            return ""
        return ""

    def _akilli_formatla(self, metin: str, story: list):
        """Metni analiz edip doğru stili uygular"""
        lines = metin.split('\n')
        
        for line in lines:
            line = line.strip()
            if not line:
                story.append(Spacer(1, 0.2*cm))
                continue
                
            u_line = line.upper()
            
            # 1. HEADER TESPİTİ (T.C., MAHKEME, DAİRE)
            if u_line == "T.C." or "MAHKEMESİ" in u_line or "DAİRESİ" in u_line or "MÜDÜRLÜĞÜ" in u_line:
                story.append(Paragraph(f"<b>{line}</b>", self.styles['UyapHeader']))
                continue
                
            # 2. BELGE BAŞLIĞI (KARAR, TUTANAK, TALEP)
            if u_line in ["KARAR", "TUTANAK", "TALEP", "BİLİRKİŞİ RAPORU", "DURUSMA ZAPTI"]:
                story.append(Paragraph(f"<b><u>{line}</u></b>", self.styles['UyapTitle']))
                continue
                
            # 3. ETİKET TESPİTİ (DAVACI:, VEKİLİ:, KONU:)
            # Genelde satır başındadır ve ':' ile biter veya ':' içerir
            if (line.startswith("DAVACI") or line.startswith("BORÇLU") or line.startswith("ALACAKLI") or 
                line.startswith("VEKİL") or line.startswith("KONU") or line.startswith("ESAS")):
                
                parts = line.split(':', 1)
                if len(parts) == 2:
                    # Etiketi kalın yap
                    formatted = f"<b>{parts[0]}:</b> {parts[1]}"
                    story.append(Paragraph(formatted, self.styles['UyapLabel']))
                    continue

            # 4. İMZA / TARİH TESPİTİ (Sağa yaslı olmalı)
            # Tarih formatı veya "Av." ile başlayan, "Hakim" geçen kısa satırlar
            if (re.match(r'\d{2}/\d{2}/\d{4}', line) or 
                line.startswith("Av.") or 
                "Hakim" in line or 
                "Katip" in line or
                "Müdür" in line):
                
                if len(line) < 40: # Çok uzun cümle değilse
                    story.append(Paragraph(line, self.styles['UyapRight']))
                    continue

            # 5. NORMAL METİN
            story.append(Paragraph(line, self.styles['UyapNormal']))

    def uret(self, kaynak_yol: str, cikti_yol: str, baslik="İcra Dosyası") -> NeatPDFRapor:
        if not REPORTLAB_OK:
            return NeatPDFRapor(hatalar=["ReportLab kütüphanesi eksik"])
            
        self.temp_dir = tempfile.mkdtemp()
        rapor = NeatPDFRapor(cikti_dosya=cikti_yol)
        
        try:
            # Dosyaları Topla (Recursive)
            dosyalar = []
            if os.path.isfile(kaynak_yol) and kaynak_yol.lower().endswith('.zip'):
                with zipfile.ZipFile(kaynak_yol, 'r') as zf:
                    zf.extractall(self.temp_dir)
            elif os.path.isdir(kaynak_yol):
                 # Zaten klasör ise kopyalamaya gerek yok, walk yapacağız
                 pass
            
            # Klasörde gezin
            target_dir = self.temp_dir if os.path.isfile(kaynak_yol) else kaynak_yol
            for root, _, files in os.walk(target_dir):
                for f in sorted(files):
                    dosyalar.append(os.path.join(root, f))

            # PDF Oluşturma
            story = []
            final_merger = PdfMerger()
            
            # Kapak
            story.append(Paragraph("<b>T.C.</b>", self.styles['UyapHeader']))
            story.append(Paragraph(f"<b>{baslik}</b>", self.styles['UyapTitle']))
            story.append(Spacer(1, 2*cm))
            story.append(Paragraph(f"Oluşturma Tarihi: {datetime.now().strftime('%d.%m.%Y')}", self.styles['UyapRight']))
            story.append(PageBreak())

            temp_content_pdf = os.path.join(self.temp_dir, "content.pdf")
            
            # Dosyaları işle
            for dosya in dosyalar:
                ext = os.path.splitext(dosya)[1].lower()
                fname = os.path.basename(dosya)
                
                if ext == '.udf' or ext == '.xml':
                    metin = self._udf_oku(dosya)
                    if metin:
                        # Yeni sayfa ve başlık
                        story.append(Paragraph(f"📄 {fname}", self.styles['UyapMeta']))
                        story.append(Spacer(1, 0.5*cm))
                        
                        # Akıllı formatla
                        self._akilli_formatla(metin, story)
                        
                        story.append(PageBreak())
                        rapor.islenen_dosya += 1
                
                elif ext == '.pdf':
                    # PDF'i daha sonra merge edeceğiz
                    pass

            # Text content PDF'ini oluştur
            doc = SimpleDocTemplate(temp_content_pdf, pagesize=A4, rightMargin=2*cm, leftMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm)
            doc.build(story)
            
            # Birleştirme
            final_merger.append(temp_content_pdf)
            
            # Orijinal PDF'leri ekle
            for dosya in dosyalar:
                if dosya.lower().endswith('.pdf') and dosya != temp_content_pdf:
                    try:
                        final_merger.append(dosya)
                        rapor.islenen_dosya += 1
                    except:
                        pass
            
            # TIFF/Image desteği (Basit)
            if PIL_OK:
                for dosya in dosyalar:
                    if dosya.lower().endswith(('.tif', '.tiff', '.jpg', '.png')):
                        try:
                            img = Image.open(dosya)
                            img_pdf = dosya + ".pdf"
                            img.convert('RGB').save(img_pdf)
                            final_merger.append(img_pdf)
                            rapor.islenen_dosya += 1
                        except:
                            pass

            final_merger.write(cikti_yol)
            final_merger.close()
            
            try:
                rapor.toplam_sayfa = len(PdfReader(cikti_yol).pages)
            except: pass

        except Exception as e:
            rapor.hatalar.append(str(e))
        
        finally:
            if os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)

        return rapor
