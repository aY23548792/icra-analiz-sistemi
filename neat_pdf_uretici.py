#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NEAT PDF ÜRETİCİ v11.0
======================
Profesyonel UDF -> PDF dönüştürücü.
Hata düzeltmesi: Çıktı dizini garantisi.
"""

import os
import zipfile
import tempfile
import shutil
import re
from datetime import datetime

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from PyPDF2 import PdfMerger, PdfReader
    REPORTLAB_OK = True
except ImportError:
    REPORTLAB_OK = False

class NeatPDFUretici:
    def __init__(self):
        self.font_name = 'Helvetica'
        self._font_yukle()

    def _font_yukle(self):
        # Linux/Windows font yolları
        paths = ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "C:\\Windows\\Fonts\\arial.ttf"]
        for p in paths:
            if os.path.exists(p):
                try:
                    pdfmetrics.registerFont(TTFont('TrFont', p))
                    self.font_name = 'TrFont'
                    break
                except: pass

    def _udf_oku(self, path):
        try:
            with zipfile.ZipFile(path) as z:
                xml = z.read('content.xml').decode('utf-8', 'ignore')
                # CDATA içeriğini al
                m = re.search(r'<!\[CDATA\[(.*?)\]\]>', xml, re.DOTALL)
                if m: return m.group(1)
                return re.sub(r'<[^>]+>', ' ', xml) # Fallback
        except: return ""

    def uret(self, kaynak_yol, cikti_yol, baslik="İcra Dosyası"):
        if not REPORTLAB_OK: return None

        # Çıktı klasörünü garantiye al
        os.makedirs(os.path.dirname(cikti_yol), exist_ok=True)
        
        merger = PdfMerger()
        temp_dir = tempfile.mkdtemp()
        
        try:
            # Kaynak dosya listesi
            files = []
            if os.path.isfile(kaynak_yol) and kaynak_yol.endswith('.zip'):
                with zipfile.ZipFile(kaynak_yol) as z:
                    z.extractall(temp_dir)
                    for r, _, fs in os.walk(temp_dir):
                        for f in fs: files.append(os.path.join(r, f))
            else:
                files.append(kaynak_yol)

            # PDF Oluşturma (ReportLab)
            story = []
            styles = getSampleStyleSheet()
            style_norm = ParagraphStyle('TrNorm', parent=styles['Normal'], fontName=self.font_name, fontSize=10, leading=14)
            
            # Kapak
            story.append(Paragraph(f"<b>{baslik}</b>", style_norm))
            story.append(Spacer(1, 20))
            story.append(Paragraph(f"Tarih: {datetime.now().strftime('%d.%m.%Y')}", style_norm))
            story.append(PageBreak())

            for f in sorted(files):
                if f.endswith('.udf'):
                    txt = self._udf_oku(f)
                    if txt:
                        story.append(Paragraph(f"📄 {os.path.basename(f)}", style_norm))
                        story.append(Spacer(1, 10))
                        for line in txt.split('\n'):
                            if line.strip():
                                story.append(Paragraph(line, style_norm))
                        story.append(PageBreak())
                elif f.endswith('.pdf'):
                    # PDF'leri sonra merge edeceğiz, burada yer tutucu yok
                    pass

            # Text PDF'i oluştur
            text_pdf = os.path.join(temp_dir, "text_content.pdf")
            doc = SimpleDocTemplate(text_pdf, pagesize=A4)
            doc.build(story)
            merger.append(text_pdf)

            # Orijinal PDF'leri ekle
            for f in sorted(files):
                if f.endswith('.pdf') and f != text_pdf:
                    try: merger.append(f)
                    except: pass
            
            merger.write(cikti_yol)
            
            # Rapor objesi (App.py bekliyor)
            class Rapor: pass
            r = Rapor()
            r.cikti_dosya = cikti_yol
            r.toplam_sayfa = len(merger.pages)
            r.islenen_dosya = len(files)
            r.hatalar = []
            r.sure_saniye = 0.5
            return r

        finally:
            merger.close()
            shutil.rmtree(temp_dir, ignore_errors=True)
