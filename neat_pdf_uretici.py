#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NEAT PDF ÜRETİCİ v12.4 (Performance Optimized)
==============================================
"""

import os
import zipfile
import tempfile
import shutil
import re
import html
from datetime import datetime

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
    from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
    from reportlab.lib import colors
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from PyPDF2 import PdfMerger, PdfReader
    REPORTLAB_OK = True
except ImportError:
    REPORTLAB_OK = False

class NeatPDFUretici:
    def __init__(self):
        self.font_normal = 'Helvetica'
        self.font_bold = 'Helvetica-Bold'
        self._font_yukle()

    def _font_yukle(self):
        paths = [
            os.path.join(os.path.dirname(__file__), "fonts", "Roboto-Regular.ttf"),
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "C:\\Windows\\Fonts\\arial.ttf"
        ]
        for p in paths:
            if os.path.exists(p):
                try:
                    pdfmetrics.registerFont(TTFont('TrFont', p))
                    self.font_normal = 'TrFont'
                    break
                except: pass

    def _clean_xml_content(self, xml_content):
        if not xml_content: return ""
        # Faster regex extraction
        m = re.search(r'<!\[CDATA\[(.*?)\]\]>', xml_content, re.DOTALL)
        text = m.group(1) if m else xml_content

        text = html.unescape(text)
        # Simplified replacement map for speed
        replacements = {
            '<p>': '<br/>', '</p>': '<br/>',
            '<div>': '<br/>', '</div>': '',
            '<br>': '\n', '<br/>': '\n'
        }
        for k, v in replacements.items():
            text = text.replace(k, v)

        # Strip all other tags efficiently
        text = re.sub(r'<[^>]+>', '', text)
        return text.strip()

    def uret(self, kaynak_yol, cikti_yol, baslik="İcra Dosyası"):
        if not REPORTLAB_OK: return None

        os.makedirs(os.path.dirname(cikti_yol), exist_ok=True)
        merger = PdfMerger()
        temp_dir = tempfile.mkdtemp()

        try:
            # Efficient file listing
            files = []
            if os.path.isfile(kaynak_yol) and kaynak_yol.endswith('.zip'):
                with zipfile.ZipFile(kaynak_yol) as z:
                    z.extractall(temp_dir)
                    for r, _, fs in os.walk(temp_dir):
                        for f in fs: files.append(os.path.join(r, f))
            else:
                files.append(kaynak_yol)
            files.sort()

            # Styles
            styles = getSampleStyleSheet()
            style_norm = ParagraphStyle('TrNorm', parent=styles['Normal'], fontName=self.font_normal, fontSize=11, leading=16)
            style_title = ParagraphStyle('TrTitle', parent=styles['Heading2'], fontName=self.font_normal, fontSize=12, backColor=colors.lightgrey)

            story = [
                Paragraph(f"<b>{baslik}</b>", style_norm),
                Paragraph(f"Tarih: {datetime.now().strftime('%d.%m.%Y')}", style_norm),
                PageBreak()
            ]

            text_files_processed = False
            for f in files:
                if f.endswith('.udf'):
                    try:
                        with zipfile.ZipFile(f) as z:
                            content = z.read('content.xml').decode('utf-8', 'ignore')
                            clean_txt = self._clean_xml_content(content)
                            if clean_txt:
                                story.append(Paragraph(f"📄 {os.path.basename(f)}", style_title))
                                for para in clean_txt.split('\n'):
                                    if para.strip():
                                        story.append(Paragraph(para, style_norm))
                                story.append(PageBreak())
                                text_files_processed = True
                    except: pass

            # Generate Text PDF
            text_pdf = os.path.join(temp_dir, "text.pdf")
            if text_files_processed:
                doc = SimpleDocTemplate(text_pdf, pagesize=A4)
                doc.build(story)
                if os.path.exists(text_pdf):
                    merger.append(text_pdf)

            # Append existing PDFs
            for f in files:
                if f.endswith('.pdf') and f != text_pdf:
                    try: merger.append(f)
                    except: pass

            merger.write(cikti_yol)

            class Rapor:
                toplam_sayfa = len(merger.pages)
                islenen_dosya = len(files)
                hatalar = []
                sure_saniye = 0
            return Rapor()

        except Exception as e:
            print(f"Error: {e}")
            return None
        finally:
            merger.close()
            shutil.rmtree(temp_dir, ignore_errors=True)
