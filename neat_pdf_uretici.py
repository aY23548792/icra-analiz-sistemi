#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NEAT PDF ÜRETİCİ v12.3 (Rich Formatting Edition)
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
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle
    from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
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
        # Genişletilmiş Font Arama
        paths = [
            os.path.join(os.path.dirname(__file__), "fonts", "Roboto-Regular.ttf"),
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "C:\\Windows\\Fonts\\arial.ttf"
        ]

        bold_paths = [
             os.path.join(os.path.dirname(__file__), "fonts", "Roboto-Bold.ttf"),
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "C:\\Windows\\Fonts\\arialbd.ttf"
        ]

        # Normal Font
        for p in paths:
            if os.path.exists(p):
                try:
                    pdfmetrics.registerFont(TTFont('TrFont', p))
                    self.font_normal = 'TrFont'
                    break
                except: pass

        # Bold Font
        for p in bold_paths:
            if os.path.exists(p):
                try:
                    pdfmetrics.registerFont(TTFont('TrFontBold', p))
                    self.font_bold = 'TrFontBold'
                    break
                except: pass

    def _clean_xml_content(self, xml_content):
        """
        UDF XML içeriğini ReportLab uyumlu HTML'e çevirir.
        Gelişmiş regex kullanarak formatlamayı korur.
        """
        if not xml_content: return ""

        # 1. CDATA veya ham metni al
        text = xml_content
        m = re.search(r'<!\[CDATA\[(.*?)\]\]>', xml_content, re.DOTALL)
        if m:
            text = m.group(1)

        # 2. HTML Entity Decode
        text = html.unescape(text)

        # 3. UDF'e özgü tagları ReportLab taglarına çevir
        # <p> -> <br/> (ReportLab Paragraph zaten p gibi davranır, ama satır içi break için)
        text = text.replace('<p>', '<br/>').replace('</p>', '<br/>')
        text = text.replace('<div>', '<br/>').replace('</div>', '')

        # Bold: <b>, <strong> -> <b>
        text = re.sub(r'<(b|strong)[^>]*>', '<b>', text, flags=re.I)
        text = re.sub(r'</(b|strong)>', '</b>', text, flags=re.I)

        # Italic: <i>, <em> -> <i>
        text = re.sub(r'<(i|em)[^>]*>', '<i>', text, flags=re.I)
        text = re.sub(r'</(i|em)>', '</i>', text, flags=re.I)

        # Underline: <u> -> <u>
        text = re.sub(r'<u[^>]*>', '<u>', text, flags=re.I)
        text = re.sub(r'</u>', '</u>', text, flags=re.I)

        # Diğer tüm tagları temizle (ReportLab'in desteklemediği stil tagları patlatır)
        # Sadece izin verilenleri tut: b, i, u, br, font, color
        allowed_tags = ['b', 'i', 'u', 'br', 'font', 'sup', 'sub']
        # Basit bir temizlik: <...> taglarını bul, allowed değilse sil

        # Regex ile sadece izin verilmeyenleri silmek zor, tersine yaklaşalım:
        # Önce <br> leri \n yap, sonra strip, sonra \n leri <br/> yap
        # Ancak bold vs korumak istiyoruz.

        # Güvenli mod: Sadece b, i, u, br'yi sakla, gerisini sil.
        # Placeholder kullanımı
        text = text.replace('<b>', '[[B]]').replace('</b>', '[[/B]]')
        text = text.replace('<i>', '[[I]]').replace('</i>', '[[/I]]')
        text = text.replace('<u>', '[[U]]').replace('</u>', '[[/U]]')
        text = text.replace('<br>', '\n').replace('<br/>', '\n')

        # Tüm tagları sil
        text = re.sub(r'<[^>]+>', '', text)

        # Placeholderları geri yükle
        text = text.replace('[[B]]', '<b>').replace('[[/B]]', '</b>')
        text = text.replace('[[I]]', '<i>').replace('[[/I]]', '</i>')
        text = text.replace('[[U]]', '<u>').replace('[[/U]]', '</u>')

        # Çoklu boşlukları ve satır sonlarını düzenle
        text = re.sub(r'\n\s*\n', '\n\n', text) # Çift enter -> paragraf

        return text.strip()

    def _udf_oku_zengin(self, path):
        """UDF dosyasını okur ve (başlık, içerik_html) döner"""
        try:
            with zipfile.ZipFile(path) as z:
                # XML bul
                xml_files = [n for n in z.namelist() if n.endswith('.xml')]
                target = 'content.xml' if 'content.xml' in xml_files else (xml_files[0] if xml_files else None)
                if not target: return os.path.basename(path), ""

                xml = z.read(target).decode('utf-8', 'ignore')
                clean_text = self._clean_xml_content(xml)
                return os.path.basename(path), clean_text
        except:
            return os.path.basename(path), ""

    def uret(self, kaynak_yol, cikti_yol, baslik="İcra Dosyası"):
        if not REPORTLAB_OK: return None

        d = os.path.dirname(cikti_yol)
        if d: os.makedirs(d, exist_ok=True)

        merger = PdfMerger()
        temp_dir = tempfile.mkdtemp()

        try:
            files = []
            if os.path.isfile(kaynak_yol) and kaynak_yol.endswith('.zip'):
                with zipfile.ZipFile(kaynak_yol) as z:
                    z.extractall(temp_dir)
                    for r, _, fs in os.walk(temp_dir):
                        for f in fs: files.append(os.path.join(r, f))
            else:
                files.append(kaynak_yol)

            # --- STYLES ---
            styles = getSampleStyleSheet()

            # Normal Stil (Justified, Türkçe Font)
            style_norm = ParagraphStyle(
                'TrNorm',
                parent=styles['Normal'],
                fontName=self.font_normal,
                fontSize=11,
                leading=16,
                alignment=TA_JUSTIFY,
                spaceAfter=6
            )

            # Başlık Stili
            style_header = ParagraphStyle(
                'TrHeader',
                parent=styles['Heading1'],
                fontName=self.font_bold,
                fontSize=14,
                leading=18,
                alignment=TA_CENTER,
                spaceAfter=12,
                textColor=colors.darkblue
            )

            # Dosya Başlığı Stili
            style_file_title = ParagraphStyle(
                'TrFileTitle',
                parent=styles['Heading2'],
                fontName=self.font_bold,
                fontSize=12,
                leading=14,
                spaceBefore=12,
                spaceAfter=6,
                textColor=colors.black,
                backColor=colors.lightgrey,
                borderPadding=4
            )

            story = []

            # --- KAPAK ---
            story.append(Paragraph(f"{baslik}", style_header))
            story.append(Spacer(1, 10))
            story.append(Paragraph(f"Oluşturulma Tarihi: {datetime.now().strftime('%d.%m.%Y %H:%M')}", style_norm))
            story.append(Spacer(1, 20))
            story.append(Paragraph("BU RAPOR OTOMATİK OLUŞTURULMUŞTUR", style_norm))
            story.append(PageBreak())

            text_files_processed = False
            for f in sorted(files):
                fname = os.path.basename(f)

                if f.endswith('.udf') or f.endswith('.xml'):
                    doc_title, content = self._udf_oku_zengin(f)
                    if content:
                        story.append(Paragraph(f"📄 {doc_title}", style_file_title))

                        # İçeriği paragraflara böl
                        paragraphs = content.split('\n\n')
                        for p_text in paragraphs:
                            if p_text.strip():
                                # Boşlukları ve satır sonlarını düzenle
                                p_text = p_text.replace('\n', '<br/>')
                                try:
                                    story.append(Paragraph(p_text, style_norm))
                                except:
                                    # Eğer xml parse hatası olursa düz metin olarak ekle
                                    clean_p = re.sub(r'<[^>]+>', '', p_text)
                                    story.append(Paragraph(clean_p, style_norm))

                        story.append(PageBreak())
                        text_files_processed = True

            # Text PDF Oluştur
            text_pdf = os.path.join(temp_dir, "text_content.pdf")
            if text_files_processed or len(story) > 4:
                doc = SimpleDocTemplate(
                    text_pdf,
                    pagesize=A4,
                    rightMargin=50, leftMargin=50,
                    topMargin=50, bottomMargin=50
                )
                doc.build(story)
                if os.path.exists(text_pdf):
                    merger.append(text_pdf)

            # Orijinal PDF'leri Ekle
            for f in sorted(files):
                if f.endswith('.pdf') and f != text_pdf:
                    try:
                        merger.append(f)
                    except: pass

            merger.write(cikti_yol)

            class Rapor: pass
            r = Rapor()
            r.cikti_dosya = cikti_yol
            try:
                reader = PdfReader(cikti_yol)
                r.toplam_sayfa = len(reader.pages)
            except:
                r.toplam_sayfa = 0

            r.islenen_dosya = len(files)
            r.hatalar = []
            r.sure_saniye = 0.5
            return r

        except Exception as e:
            print(f"PDF Üretim Hatası: {e}")
            return None
        finally:
            merger.close()
            shutil.rmtree(temp_dir, ignore_errors=True)
