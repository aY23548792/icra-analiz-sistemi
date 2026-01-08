#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NEAT PDF ÜRETİCİ v4.0 - UDF FIX
===============================
UDF dosyalarını XML'den parse edip düzgün formatlı PDF yapar.
"""

import os
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Tuple
import tempfile
import re

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm, mm
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY, TA_RIGHT
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from PyPDF2 import PdfMerger, PdfReader
    REPORTLAB_OK = True
except ImportError:
    REPORTLAB_OK = False

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
        self.stiller = None
        # Font Ayarı - Linux/Streamlit Cloud uyumlu
        self.font_name = 'Helvetica' # Fallback
        
    def _font_yukle(self):
        """Türkçe font yüklemeye çalışır"""
        font_yollari = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "C:/Windows/Fonts/arial.ttf",
            "arial.ttf"
        ]
        for yol in font_yollari:
            if os.path.exists(yol):
                try:
                    pdfmetrics.registerFont(TTFont('TurkceFont', yol))
                    self.font_name = 'TurkceFont'
                    return
                except:
                    pass

    def _udf_oku(self, udf_path: str) -> str:
        """UDF (XML) içeriğini okur ve temiz metin döndürür"""
        try:
            with zipfile.ZipFile(udf_path, 'r') as zf:
                # content.xml'i bul
                if 'content.xml' in zf.namelist():
                    xml_data = zf.read('content.xml')
                    
                    # XML Parse
                    root = ET.fromstring(xml_data)
                    
                    # Genelde metin 'content' tagi içinde CDATA olarak veya text olarak bulunur
                    text_content = []
                    
                    # Tüm text node'larını al
                    for elem in root.iter():
                        if elem.text:
                            text_content.append(elem.text.strip())
                        if elem.tail:
                            text_content.append(elem.tail.strip())
                            
                    raw_text = "\n".join(filter(None, text_content))
                    return raw_text
                else:
                    return "[HATA: UDF içinde content.xml bulunamadı]"
        except zipfile.BadZipFile:
            return "[HATA: Bozuk UDF dosyası]"
        except Exception as e:
            return f"[HATA: UDF okunamadı - {str(e)}]"

    def _stiller_olustur(self):
        styles = getSampleStyleSheet()
        styles.add(ParagraphStyle(
            name='TrNormal',
            fontName=self.font_name,
            fontSize=10,
            leading=14,
            alignment=TA_JUSTIFY
        ))
        styles.add(ParagraphStyle(
            name='TrBaslik',
            fontName=self.font_name,
            fontSize=14,
            leading=18,
            alignment=TA_CENTER,
            spaceAfter=10
        ))
        styles.add(ParagraphStyle(
            name='TrMeta',
            fontName=self.font_name,
            fontSize=8,
            textColor='grey',
            alignment=TA_RIGHT
        ))
        return styles

    def uret(self, kaynak_yol: str, cikti_yol: str, baslik="İcra Dosyası") -> NeatPDFRapor:
        if not REPORTLAB_OK:
            return NeatPDFRapor(hatalar=["ReportLab veya PyPDF2 eksik"])
            
        start_time = datetime.now()
        self._font_yukle()
        styles = self._stiller_olustur()
        rapor = NeatPDFRapor(cikti_dosya=cikti_yol)
        
        dosyalar = []
        temp_extract_dir = None
        
        # Kaynak ZIP ise aç
        if os.path.isfile(kaynak_yol) and kaynak_yol.endswith('.zip'):
            temp_extract_dir = tempfile.mkdtemp()
            with zipfile.ZipFile(kaynak_yol, 'r') as zf:
                zf.extractall(temp_extract_dir)
                for root, _, files in os.walk(temp_extract_dir):
                    for f in files:
                        dosyalar.append(os.path.join(root, f))
        elif os.path.isdir(kaynak_yol):
             for root, _, files in os.walk(kaynak_yol):
                    for f in files:
                        dosyalar.append(os.path.join(root, f))
        else: # Tek dosya (UDF vs)
            dosyalar.append(kaynak_yol)

        # PDF Oluşturma Akışı
        story = []
        merger = PdfMerger()
        
        # Kapak
        story.append(Paragraph(baslik, styles['TrBaslik']))
        story.append(Spacer(1, 2*cm))
        story.append(Paragraph(f"Oluşturma Tarihi: {datetime.now().strftime('%d.%m.%Y')}", styles['TrNormal']))
        story.append(PageBreak())

        # Dosyaları İşle
        temp_pdf = os.path.join(os.path.dirname(cikti_yol), "temp_content.pdf")
        
        processed_udf_count = 0
        for dosya in sorted(dosyalar):
            ext = os.path.splitext(dosya)[1].lower()
            dosya_adi = os.path.basename(dosya)
            
            if ext == '.udf':
                metin = self._udf_oku(dosya)
                story.append(Paragraph(f"📄 {dosya_adi}", styles['TrBaslik']))
                story.append(Spacer(1, 0.5*cm))
                
                # Paragraflara böl
                for par in metin.split('\n'):
                    if par.strip():
                        story.append(Paragraph(par, styles['TrNormal']))
                        story.append(Spacer(1, 0.2*cm))
                
                story.append(PageBreak())
                rapor.islenen_dosya += 1
                processed_udf_count += 1
            elif ext == '.pdf':
                # PyPDF2 ile sona ekleyeceğiz
                pass 

        # ReportLab PDF'i oluştur (Sadece UDF'ler varsa veya kapak için)
        if processed_udf_count > 0 or story:
            doc = SimpleDocTemplate(temp_pdf, pagesize=A4)
            doc.build(story)
            merger.append(temp_pdf)
        
        # Orijinal PDF'leri ekle
        for dosya in sorted(dosyalar):
            if dosya.endswith('.pdf'):
                try:
                    merger.append(dosya)
                    rapor.islenen_dosya += 1
                except Exception as e:
                    rapor.hatalar.append(f"{os.path.basename(dosya)} eklenemedi: {str(e)}")
                    
        merger.write(cikti_yol)
        merger.close()
        
        # Temizlik
        if os.path.exists(temp_pdf): os.remove(temp_pdf)
        if temp_extract_dir: shutil.rmtree(temp_extract_dir, ignore_errors=True)
        
        # Sayfa sayısı
        try:
            reader = PdfReader(cikti_yol)
            rapor.toplam_sayfa = len(reader.pages)
        except:
            pass
        
        rapor.sure_saniye = (datetime.now() - start_time).total_seconds()
        return rapor
