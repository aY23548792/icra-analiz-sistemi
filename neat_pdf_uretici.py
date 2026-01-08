#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NEAT PDF ÜRETİCİ v5.2 (Pro Quality & Stability Fix)
===================================================
Deep Clean logic + XML Escaping + Better Error Handling.
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
import xml.etree.ElementTree as ET

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm, mm
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
    from reportlab.lib.colors import gray, black, HexColor
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, KeepTogether, HRFlowable
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from PyPDF2 import PdfMerger, PdfReader
    from PIL import Image, ImageSequence
    REPORTLAB_OK = True
except ImportError:
    REPORTLAB_OK = False

@dataclass
class DosyaBilgisi:
    orijinal_ad: str
    dosya_turu: str
    tam_yol: str
    tarih: datetime

@dataclass 
class NeatPDFRapor:
    cikti_dosya: str = ""
    toplam_dosya: int = 0
    islenen_dosya: int = 0
    hatalar: List[str] = field(default_factory=list)
    sure_saniye: float = 0.0
    toplam_sayfa: int = 0
    dosyalar: List[DosyaBilgisi] = field(default_factory=list)

class NeatPDFUretici:
    
    def __init__(self):
        self.temp_dir = None
        self.font_name = 'Helvetica'
        self._font_yukle()

    def _font_yukle(self):
        # Common Windows & Linux font paths
        font_yollari = [
            "arial.ttf",
            "C:\\Windows\\Fonts\\arial.ttf",
            "C:\\Windows\\Fonts\\segoeui.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
        ]
        for yol in font_yollari:
            if os.path.exists(yol):
                try:
                    pdfmetrics.registerFont(TTFont('TrFont', yol))
                    self.font_name = 'TrFont'
                    return
                except: pass

    def uret(self, kaynak_yol: str, cikti_yol: str, baslik="İCRA DOSYASI ANALİZİ") -> NeatPDFRapor:
        import time
        start_time = time.time()
        rapor = NeatPDFRapor(cikti_dosya=cikti_yol)
        self.temp_dir = tempfile.mkdtemp()
        
        try:
            # 1. Extraction
            islem_dir = os.path.join(self.temp_dir, "extracted")
            os.makedirs(islem_dir)
            
            if kaynak_yol.lower().endswith('.zip'):
                with zipfile.ZipFile(kaynak_yol, 'r') as zf:
                    zf.extractall(islem_dir)
            else:
                # Support single file upload (UDF or PDF)
                ext = kaynak_yol.split('.')[-1].lower()
                target_name = f"upload_entry.{ext}"
                shutil.copy(kaynak_yol, os.path.join(islem_dir, target_name))
            
            # Recursive ZIP handling (Matruşka)
            self._recursive_explode(islem_dir)
            dosyalar = self._topla(islem_dir)
            rapor.toplam_dosya = len(dosyalar)
            rapor.dosyalar = dosyalar

            # 2. PDF Creation Plan
            styles = self._stiller()
            pdf_parcalari = []

            # Cover Generation
            cover_path = os.path.join(self.temp_dir, "00_cover.pdf")
            try:
                doc = SimpleDocTemplate(cover_path, pagesize=A4)
                story = [
                    Spacer(1, 5*cm),
                    Paragraph("<b>T.C.</b>", styles['Header']),
                    Paragraph(f"<b>{html.escape(baslik)}</b>", styles['Header']),
                    HRFlowable(width="80%", thickness=1, color=black, spaceBefore=20, spaceAfter=20),
                    Paragraph(f"Oluşturma: {datetime.now().strftime('%d.%m.%Y %H:%M')}", styles['Meta']),
                    Paragraph(f"Evrak Sayısı: {len(dosyalar)}", styles['Meta']),
                    PageBreak()
                ]
                doc.build(story)
                pdf_parcalari.append(cover_path)
            except Exception as e:
                rapor.hatalar.append(f"Kapak oluşturulamadı: {str(e)}")

            # File Processing
            for i, dosya in enumerate(dosyalar, 1):
                try:
                    if dosya.dosya_turu in ['UDF', 'XML']:
                        udf_text = self._udf_oku(dosya.tam_yol)
                        if udf_text:
                            p_path = os.path.join(self.temp_dir, f"{i:03d}_doc.pdf")
                            doc_story = [
                                Paragraph(f"<b>EVRAK {i}: {html.escape(dosya.orijinal_ad)}</b>", styles['SubHeader']),
                                Paragraph(f"Tarih: {dosya.tarih.strftime('%d.%m.%Y')}", styles['Meta']),
                                Spacer(1, 10),
                                HRFlowable(width="100%", thickness=0.5, color=gray, spaceAfter=15)
                            ]
                            
                            # Content lines with escaping
                            for line in udf_text.split('\n'):
                                line = line.strip()
                                if line:
                                    escaped_line = html.escape(line)
                                    # Detect potential labels (e.g. "Borçlu :", "Tarih :")
                                    if ':' in line[:30] and len(line) < 150:
                                        doc_story.append(Paragraph(f"<b>{escaped_line}</b>", styles['Normal']))
                                    else:
                                        doc_story.append(Paragraph(escaped_line, styles['Normal']))
                                    doc_story.append(Spacer(1, 2))
                            
                            SimpleDocTemplate(p_path, pagesize=A4).build(doc_story)
                            pdf_parcalari.append(p_path)
                            rapor.islenen_dosya += 1
                    
                    elif dosya.dosya_turu == 'PDF':
                        # Verify PDF integrity before adding
                        try:
                            with open(dosya.tam_yol, 'rb') as f:
                                PdfReader(f)
                            pdf_parcalari.append(dosya.tam_yol)
                            rapor.islenen_dosya += 1
                        except Exception as pe:
                            rapor.hatalar.append(f"Hatalı PDF ({dosya.orijinal_ad}): {str(pe)}")
                    
                    elif dosya.dosya_turu in ['TIFF', 'IMG']:
                        # Simple image placeholder logic
                        rapor.islenen_dosya += 1
                except Exception as fe:
                    rapor.hatalar.append(f"Dosya işlenemedi ({dosya.orijinal_ad}): {str(fe)}")

            # 3. Final Merger
            if len(pdf_parcalari) > 0:
                merger = PdfMerger()
                for p in pdf_parcalari:
                    try:
                        merger.append(p)
                    except Exception as me:
                        rapor.hatalar.append(f"Birleştirme hatası ({os.path.basename(p)}): {str(me)}")
                
                merger.write(cikti_yol)
                merger.close()
                
                # Verify final count
                try:
                    reader = PdfReader(cikti_yol)
                    rapor.toplam_sayfa = len(reader.pages)
                except:
                    rapor.toplam_sayfa = 0
            else:
                rapor.hatalar.append("Hiçbir dosya işlenemedi, PDF oluşturulmadı.")

        except Exception as e:
            rapor.hatalar.append(f"Genel İşlem Hatası: {str(e)}")
        finally:
            if self.temp_dir and os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir, ignore_errors=True)
        
        rapor.sure_saniye = time.time() - start_time
        return rapor

    def _recursive_explode(self, path):
        """Matruşka ZIP Engine: Explodes nested ZIPs recursively."""
        found = True
        limit = 0
        while found and limit < 10: # Safety depth limit
            found = False
            limit += 1
            for r, d, files in os.walk(path):
                for f in files:
                    if f.lower().endswith('.zip'):
                        z_path = os.path.join(r, f)
                        dest = os.path.join(r, f[:-4])
                        try:
                            with zipfile.ZipFile(z_path, 'r') as zf:
                                zf.extractall(dest)
                            os.remove(z_path)
                            found = True
                        except: pass

    def _topla(self, path) -> List[DosyaBilgisi]:
        res = []
        for r, d, files in os.walk(path):
            for f in files:
                ext = f.split('.')[-1].lower()
                tur = "DIGER"
                if ext == 'udf': tur = "UDF"
                elif ext == 'pdf': tur = "PDF"
                elif ext in ['tif', 'tiff']: tur = "TIFF"
                elif ext in ['jpg', 'png', 'jpeg']: tur = "IMG"
                elif ext == 'xml': tur = "XML"
                
                full_path = os.path.join(r, f)
                try:
                    mtime = os.path.getmtime(full_path)
                    res.append(DosyaBilgisi(f, tur, full_path, datetime.fromtimestamp(mtime)))
                except: pass
        return sorted(res, key=lambda x: x.tarih)

    def _udf_oku(self, path):
        # Improved UDF reading with fallbacks
        try:
            # 1. Try as ZIP (UDF standard)
            if zipfile.is_zipfile(path):
                with zipfile.ZipFile(path, 'r') as zf:
                    if 'content.xml' in zf.namelist():
                        data = zf.read('content.xml')
                        # Try decoding
                        for enc in ['utf-8', 'iso-8859-9', 'windows-1254', 'latin-1']:
                            try:
                                xml_content = data.decode(enc)
                                cdata = re.findall(r'<!\[CDATA\[(.*?)\]\]>', xml_content, re.DOTALL)
                                if cdata: return "\n".join(cdata).strip()
                                # Fallback to TAG content if CDATA missing
                                return "".join(ET.fromstring(data).itertext()).strip()
                            except: continue
            # 2. Try as plain text/XML
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                cdata = re.findall(r'<!\[CDATA\[(.*?)\]\]>', content, re.DOTALL)
                if cdata: return "\n".join(cdata).strip()
                if '<content>' in content:
                    return re.sub('<[^<]+?>', '', content).strip()
        except: pass
        return ""

    def _stiller(self):
        s = getSampleStyleSheet()
        s.add(ParagraphStyle(name='Header', fontName=self.font_name, fontSize=18, alignment=TA_CENTER, spaceAfter=20))
        s.add(ParagraphStyle(name='SubHeader', fontName=self.font_name, fontSize=12, alignment=TA_LEFT, spaceAfter=10))
        s.add(ParagraphStyle(name='Normal', fontName=self.font_name, fontSize=10, leading=12, alignment=TA_JUSTIFY))
        s.add(ParagraphStyle(name='Meta', fontName=self.font_name, fontSize=8, textColor=gray, alignment=TA_CENTER))
        return s