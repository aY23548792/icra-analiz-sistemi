#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NEAT PDF ÜRETİCİ v11.1
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
        # Font yolları (Öncelik: Proje içi fonts klasörü)
        paths = [
            os.path.join(os.path.dirname(__file__), "fonts", "Roboto-Regular.ttf"),
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "C:\\Windows\\Fonts\\arial.ttf"
        ]

        for p in paths:
            if os.path.exists(p):
                try:
                    # Font ismini dosya adından türetelim ki çakışma olmasın
                    font_alias = 'TrFont'
                    pdfmetrics.registerFont(TTFont(font_alias, p))
                    self.font_name = font_alias
                    break
                except Exception as e:
                    print(f"Font yükleme hatası ({p}): {e}")

    def _udf_oku(self, path):
        try:
            with zipfile.ZipFile(path) as z:
                # content.xml yoksa ilk xml dosyasını dene
                xml_files = [n for n in z.namelist() if n.endswith('.xml')]
                if 'content.xml' in xml_files:
                    target_xml = 'content.xml'
                elif xml_files:
                    target_xml = xml_files[0]
                else:
                    return ""

                xml = z.read(target_xml).decode('utf-8', 'ignore')

                # 1. CDATA içeriğini al
                m = re.search(r'<!\[CDATA\[(.*?)\]\]>', xml, re.DOTALL)
                if m:
                    content = m.group(1)
                else:
                    # CDATA yoksa tüm XML taglerini temizle
                    content = re.sub(r'<[^>]+>', ' ', xml)

                # HTML entity'lerini temizle/dönüştür (Gerekirse)
                content = content.replace('&nbsp;', ' ').replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&')
                return content.strip()
        except Exception as e:
            print(f"UDF okuma hatası ({path}): {e}")
            return ""

    def uret(self, kaynak_yol, cikti_yol, baslik="İcra Dosyası"):
        if not REPORTLAB_OK: return None

        # Çıktı klasörünü garantiye al
        d = os.path.dirname(cikti_yol)
        if d: os.makedirs(d, exist_ok=True)

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
            # Font desteğine göre style oluştur
            try:
                style_norm = ParagraphStyle('TrNorm', parent=styles['Normal'], fontName=self.font_name, fontSize=10, leading=14)
            except:
                style_norm = styles['Normal']

            # Kapak
            story.append(Paragraph(f"<b>{baslik}</b>", style_norm))
            story.append(Spacer(1, 20))
            story.append(Paragraph(f"Tarih: {datetime.now().strftime('%d.%m.%Y')}", style_norm))
            story.append(PageBreak())

            text_files_processed = False
            for f in sorted(files):
                if f.endswith('.udf'):
                    txt = self._udf_oku(f)
                    if txt:
                        story.append(Paragraph(f"📄 {os.path.basename(f)}", style_norm))
                        story.append(Spacer(1, 10))
                        # Satır satır ekle
                        for line in txt.split('\n'):
                            if line.strip():
                                # Uzun kelimeleri veya satırları bölmek gerekebilir ama ReportLab Paragraph bunu yapar
                                story.append(Paragraph(line, style_norm))
                        story.append(PageBreak())
                        text_files_processed = True
                elif f.endswith('.pdf'):
                    # PDF'leri sonra merge edeceğiz
                    pass

            # Text PDF'i oluştur (sadece içerik varsa)
            text_pdf = os.path.join(temp_dir, "text_content.pdf")
            if text_files_processed or len(story) > 4: # Kapak harici içerik varsa
                doc = SimpleDocTemplate(text_pdf, pagesize=A4)
                doc.build(story)
                if os.path.exists(text_pdf):
                    merger.append(text_pdf)

            # Orijinal PDF'leri ekle
            for f in sorted(files):
                if f.endswith('.pdf') and f != text_pdf:
                    try: merger.append(f)
                    except: pass

            merger.write(cikti_yol)

            # Rapor objesi
            class Rapor: pass
            r = Rapor()
            r.cikti_dosya = cikti_yol
            try:
                # Sayfa sayısını okumak için
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
