#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NEAT PDF ÜRETİCİ v3.0 - UYAP KALİTESİNDE
========================================
Gerçek profesyonel PDF çıktısı

Özellikler:
- T.C. başlıklı resmi format
- Bold etiketler (DAVACI:, VEKİLİ:)
- Justified metin
- İmza alanı sağda
- Kapak + İçindekiler
- Sayfa numaraları
"""

import os
import re
import zipfile
import tempfile
import shutil
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

# Kütüphane kontrolleri
REPORTLAB_OK = False
PYPDF2_OK = False
PIL_OK = False

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm, mm
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY, TA_RIGHT
    from reportlab.lib.colors import black, gray, HexColor
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, PageBreak, 
        Table, TableStyle, KeepTogether
    )
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    REPORTLAB_OK = True
except ImportError:
    pass

try:
    from PyPDF2 import PdfMerger, PdfReader
    PYPDF2_OK = True
except ImportError:
    pass

try:
    from PIL import Image
    PIL_OK = True
except ImportError:
    pass

# Font ayarları - Türkçe destekli serif font
FONT_NORMAL = 'Helvetica'
FONT_BOLD = 'Helvetica-Bold'

if REPORTLAB_OK:
    # Serif font dene (Times benzeri, daha resmi)
    FONT_PATHS = [
        ('/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf', 'DejaVuSerif', False),
        ('/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf', 'DejaVuSerif-Bold', True),
        ('/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf', 'LiberationSerif', False),
        ('/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf', 'LiberationSerif-Bold', True),
    ]
    
    for font_path, font_name, is_bold in FONT_PATHS:
        if os.path.exists(font_path):
            try:
                pdfmetrics.registerFont(TTFont(font_name, font_path))
                if is_bold:
                    FONT_BOLD = font_name
                else:
                    FONT_NORMAL = font_name
            except:
                pass


@dataclass
class DosyaBilgisi:
    """İşlenen dosya bilgisi"""
    orijinal_ad: str
    dosya_turu: str  # UDF, PDF, TIFF, IMG
    boyut_kb: float = 0.0
    baslik: str = ""
    hata: Optional[str] = None
    islendi: bool = False


@dataclass 
class NeatPDFRapor:
    """PDF üretim raporu"""
    cikti_dosya: str = ""
    toplam_dosya: int = 0
    islenen_dosya: int = 0
    hatali_dosya: int = 0
    atlanan_dosya: int = 0
    toplam_sayfa: int = 0
    dosyalar: List[DosyaBilgisi] = field(default_factory=list)
    hatalar: List[str] = field(default_factory=list)
    sure_saniye: float = 0.0


class NeatPDFUretici:
    """
    Profesyonel PDF üretici - UYAP kalitesinde
    
    Kullanım:
        uretici = NeatPDFUretici()
        rapor = uretici.uret("dosya.zip", "cikti.pdf", "Başlık")
    """
    
    # Etiket pattern'leri - bunlar BOLD olacak
    ETIKET_LISTESI = [
        'DAVACI', 'DAVALI', 'VEKİLİ', 'ADRES', 'KONU', 
        'İhbar Edilen', 'İŞLEM YAPILACAK TARAF', 'İşlem Yapılacak Taraf Adı',
        'HUKUKSAL NEDENLER', 'HUKUKİ NEDENLER', 'DELİLLER', 'AÇIKLAMALAR',
        'NETİCE-İ TALEP', 'NETİCE VE TALEP', 'SONUÇ VE İSTEM',
        'Talep', 'BORÇLU', 'ALACAKLI', 'MÜŞTEKİ', 'SANIK', 'ŞÜPHELİ',
        'DOSYA NO', 'ESAS NO', 'KARAR NO', 'TARİH', 'İCRA MÜDÜRLÜĞÜ'
    ]
    
    # Belge başlık pattern'leri - bunlar altı çizili olacak
    BASLIK_LISTESI = [
        'TALEP EVRAKI', 'DİLEKÇE', 'DAVA DİLEKÇESİ', 'CEVAP DİLEKÇESİ',
        'TUTANAK', 'KARAR', 'ZABTI', 'DURUŞMA TUTANAĞI',
        'RAPOR', 'BİLİRKİŞİ RAPORU', 'KEŞİF RAPORU',
        'İHBARNAME', 'HACİZ İHBARNAMESİ', '89/1', '89/2', '89/3',
        'MÜZEKKERE', 'TEBLİGAT', 'TEBLİĞ MAZBATASI', 'MAZBATA',
        'İCRA EMRİ', 'ÖDEME EMRİ', 'TAKİP TALEBİ'
    ]
    
    def __init__(self):
        self.temp_dir = None
        self.stiller = None
        
    def _stiller_olustur(self):
        """Profesyonel PDF stilleri oluştur"""
        if not REPORTLAB_OK:
            return None
            
        styles = getSampleStyleSheet()
        
        # T.C. Başlık - en üstte, ortalı, bold
        styles.add(ParagraphStyle(
            name='TCBaslik',
            fontName=FONT_BOLD,
            fontSize=14,
            alignment=TA_CENTER,
            spaceAfter=3*mm,
            spaceBefore=0,
            textColor=black,
            leading=16,
        ))
        
        # Kurum Başlığı (Mahkeme, Daire vs.) - ortalı, bold
        styles.add(ParagraphStyle(
            name='KurumBaslik',
            fontName=FONT_BOLD,
            fontSize=12,
            alignment=TA_CENTER,
            spaceAfter=2*mm,
            textColor=black,
            leading=15,
        ))
        
        # Dosya No - ortalı
        styles.add(ParagraphStyle(
            name='DosyaNo',
            fontName=FONT_NORMAL,
            fontSize=11,
            alignment=TA_CENTER,
            spaceAfter=10*mm,
            spaceBefore=5*mm,
            textColor=black,
        ))
        
        # Alt Başlık (TALEP EVRAKI vs.) - ortalı, bold, altı çizili
        styles.add(ParagraphStyle(
            name='AltBaslik',
            fontName=FONT_BOLD,
            fontSize=12,
            alignment=TA_CENTER,
            spaceAfter=8*mm,
            spaceBefore=10*mm,
            textColor=black,
        ))
        
        # Normal metin - justify, paragraf girintisi
        styles.add(ParagraphStyle(
            name='NormalMetin',
            fontName=FONT_NORMAL,
            fontSize=11,
            alignment=TA_JUSTIFY,
            spaceAfter=4*mm,
            spaceBefore=2*mm,
            leading=15,
            firstLineIndent=1*cm,
            textColor=black,
        ))
        
        # Etiketli satır (DAVACI:, VEKİLİ: vs.) - sol hizalı
        styles.add(ParagraphStyle(
            name='EtiketliSatir',
            fontName=FONT_NORMAL,
            fontSize=11,
            alignment=TA_LEFT,
            spaceAfter=3*mm,
            spaceBefore=1*mm,
            textColor=black,
            leading=14,
            leftIndent=0,
        ))
        
        # İmza alanı - sağa hizalı
        styles.add(ParagraphStyle(
            name='Imza',
            fontName=FONT_NORMAL,
            fontSize=11,
            alignment=TA_RIGHT,
            spaceAfter=2*mm,
            spaceBefore=15*mm,
            textColor=black,
        ))
        
        # Tarih - sol hizalı
        styles.add(ParagraphStyle(
            name='Tarih',
            fontName=FONT_NORMAL,
            fontSize=11,
            alignment=TA_LEFT,
            spaceAfter=8*mm,
            spaceBefore=5*mm,
            textColor=black,
        ))
        
        # Kapak başlık - büyük, renkli
        styles.add(ParagraphStyle(
            name='KapakBaslik',
            fontName=FONT_BOLD,
            fontSize=20,
            alignment=TA_CENTER,
            spaceAfter=15*mm,
            spaceBefore=30*mm,
            textColor=HexColor('#1a3c5a'),
        ))
        
        # İçindekiler başlık
        styles.add(ParagraphStyle(
            name='IcindekilerBaslik',
            fontName=FONT_BOLD,
            fontSize=14,
            alignment=TA_CENTER,
            spaceAfter=10*mm,
            textColor=HexColor('#1a3c5a'),
        ))
        
        # İçindekiler item
        styles.add(ParagraphStyle(
            name='IcindekilerItem',
            fontName=FONT_NORMAL,
            fontSize=10,
            alignment=TA_LEFT,
            spaceAfter=3*mm,
            leftIndent=10*mm,
        ))
        
        # Evrak header (dosya adı) - gri, küçük
        styles.add(ParagraphStyle(
            name='EvrakHeader',
            fontName=FONT_NORMAL,
            fontSize=9,
            alignment=TA_LEFT,
            textColor=gray,
            spaceAfter=8*mm,
            spaceBefore=0,
        ))
        
        return styles
    
    def _udf_icerik_cikar(self, udf_path: str) -> Tuple[str, str]:
        """UDF'den içerik ve başlık çıkar"""
        metin = ""
        baslik = ""
        
        try:
            with zipfile.ZipFile(udf_path, 'r') as zf:
                if 'content.xml' in zf.namelist():
                    content = zf.read('content.xml').decode('utf-8', errors='ignore')
                    
                    # CDATA içeriğini çıkar
                    cdata_match = re.search(r'<!\[CDATA\[(.*?)\]\]>', content, re.DOTALL)
                    if cdata_match:
                        metin = cdata_match.group(1).strip()
                    else:
                        # content tag'ini dene
                        content_match = re.search(r'<content>(.*?)</content>', content, re.DOTALL)
                        if content_match:
                            metin = content_match.group(1).strip()
                        else:
                            # Tag'leri temizle
                            metin = re.sub(r'<[^>]+>', '', content).strip()
                    
                    # Başlık bul (ilk mahkeme/daire satırı)
                    for satir in metin.split('\n')[:15]:
                        satir = satir.strip()
                        if any(x in satir.upper() for x in ['MAHKEMESİ', 'DAİRESİ', 'MÜDÜRLÜĞÜ', 'İCRA DAİRESİ']):
                            baslik = satir
                            break
        except Exception as e:
            print(f"UDF okuma hatası: {e}")
        
        return metin, baslik
    
    def _metin_formatla(self, metin: str) -> List:
        """Metni profesyonel formatta flowable'lara dönüştür"""
        if not self.stiller:
            return []
        
        flowables = []
        satirlar = metin.split('\n')
        
        # Etiket pattern'i derle
        etiket_pattern = re.compile(
            r'^(' + '|'.join(re.escape(e) for e in self.ETIKET_LISTESI) + r')\s*[:\-\t]+\s*(.*)$',
            re.IGNORECASE
        )
        
        # Başlık pattern'i derle  
        baslik_keywords = '|'.join(re.escape(b) for b in self.BASLIK_LISTESI)
        baslik_pattern = re.compile(rf'^\s*({baslik_keywords})\s*$', re.IGNORECASE)
        
        ilk_satirlar = True
        tc_eklendi = False
        kurum_satirlari = []
        
        i = 0
        while i < len(satirlar):
            satir = satirlar[i]
            satir_strip = satir.strip()
            i += 1
            
            if not satir_strip:
                if kurum_satirlari:
                    # Kurum satırlarını ekle
                    for ks in kurum_satirlari:
                        ks_safe = self._html_escape(ks)
                        flowables.append(Paragraph(f"<b>{ks_safe}</b>", self.stiller['KurumBaslik']))
                    kurum_satirlari = []
                    ilk_satirlar = False
                
                flowables.append(Spacer(1, 4*mm))
                continue
            
            # HTML escape
            satir_safe = self._html_escape(satir_strip)
            
            # === İLK SATIRLAR: T.C. ve Kurum başlığı ===
            if ilk_satirlar:
                # T.C. satırı
                if satir_strip.upper() in ['T.C.', 'TC', 'T.C']:
                    if not tc_eklendi:
                        flowables.append(Paragraph("<b>T.C.</b>", self.stiller['TCBaslik']))
                        tc_eklendi = True
                    continue
                
                # Kurum satırları (Mahkeme, Daire vs.)
                if any(x in satir_strip.upper() for x in ['MAHKEMESİ', 'DAİRESİ', 'MÜDÜRLÜĞÜ', 'İCRA DAİRESİ', 'SAVCILIĞI']):
                    kurum_satirlari.append(satir_strip)
                    continue
                
                # İl/İlçe satırları
                if any(x in satir_strip.upper() for x in ['ANKARA', 'İSTANBUL', 'İZMİR', 'BURSA', 'ANTALYA', 'ADANA']):
                    if len(satir_strip) < 50:  # Kısa satır = muhtemelen il adı
                        kurum_satirlari.append(satir_strip)
                        continue
                
                # Dosya no (2023/12345 ESAS gibi)
                if re.match(r'^\d{4}/\d+', satir_strip) or 'ESAS' in satir_strip.upper():
                    # Önce kurum satırlarını ekle
                    if kurum_satirlari:
                        for ks in kurum_satirlari:
                            ks_safe = self._html_escape(ks)
                            flowables.append(Paragraph(f"<b>{ks_safe}</b>", self.stiller['KurumBaslik']))
                        kurum_satirlari = []
                    
                    flowables.append(Paragraph(satir_safe, self.stiller['DosyaNo']))
                    ilk_satirlar = False
                    continue
            
            # Kurum satırları bekliyor, ama farklı içerik geldi
            if kurum_satirlari:
                for ks in kurum_satirlari:
                    ks_safe = self._html_escape(ks)
                    flowables.append(Paragraph(f"<b>{ks_safe}</b>", self.stiller['KurumBaslik']))
                kurum_satirlari = []
                ilk_satirlar = False
            
            # === BELGE BAŞLIĞI (TALEP EVRAKI vs.) ===
            if baslik_pattern.match(satir_strip):
                flowables.append(Spacer(1, 5*mm))
                flowables.append(Paragraph(f"<b><u>{satir_safe}</u></b>", self.stiller['AltBaslik']))
                continue
            
            # === ETİKETLİ SATIR (DAVACI:, VEKİLİ: vs.) ===
            etiket_match = etiket_pattern.match(satir_strip)
            if etiket_match:
                etiket = etiket_match.group(1)
                deger = etiket_match.group(2).strip()
                deger_safe = self._html_escape(deger)
                
                flowables.append(Paragraph(
                    f"<b>{etiket.upper()}:</b> {deger_safe}",
                    self.stiller['EtiketliSatir']
                ))
                continue
            
            # === İMZA ALANI ===
            if (satir_strip.startswith('Av.') or 
                satir_strip.startswith('Avukat') or
                'Vekili' in satir_strip or 
                'e-imzalıdır' in satir_strip.lower() or
                'imzalıdır' in satir_strip.lower()):
                flowables.append(Paragraph(satir_safe, self.stiller['Imza']))
                continue
            
            # === TARİH SATIRI ===
            if re.match(r'^\d{2}[./]\d{2}[./]\d{4}$', satir_strip):
                flowables.append(Paragraph(satir_safe, self.stiller['Tarih']))
                continue
            
            # === NORMAL METİN ===
            flowables.append(Paragraph(satir_safe, self.stiller['NormalMetin']))
        
        return flowables
    
    def _html_escape(self, text: str) -> str:
        """HTML özel karakterlerini escape et"""
        return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    
    def _img_to_pdf(self, img_path: str, pdf_path: str) -> bool:
        """Görüntüyü PDF'e dönüştür"""
        if not PIL_OK:
            return False
        
        try:
            img = Image.open(img_path)
            
            # RGB'ye çevir
            if img.mode == 'RGBA':
                bg = Image.new('RGB', img.size, (255, 255, 255))
                bg.paste(img, mask=img.split()[3])
                img = bg
            elif img.mode != 'RGB':
                img = img.convert('RGB')
            
            img.save(pdf_path, 'PDF', resolution=150)
            return True
        except Exception as e:
            print(f"Görüntü dönüştürme hatası: {e}")
            return False
    
    def _kapak_olustur(self, baslik: str, dosya_bilgileri: List[DosyaBilgisi]) -> List:
        """Kapak sayfası oluştur"""
        if not self.stiller:
            return []
        
        flowables = []
        
        # Üst boşluk
        flowables.append(Spacer(1, 4*cm))
        
        # T.C.
        flowables.append(Paragraph("<b>T.C.</b>", self.stiller['TCBaslik']))
        flowables.append(Spacer(1, 5*mm))
        
        # Ana başlık
        baslik_safe = self._html_escape(baslik)
        flowables.append(Paragraph(f"<b>{baslik_safe}</b>", self.stiller['KapakBaslik']))
        
        flowables.append(Spacer(1, 3*cm))
        
        # Bilgi tablosu
        tarih = datetime.now().strftime('%d.%m.%Y %H:%M')
        
        # Dosya türü sayıları
        tur_sayilari = {}
        for d in dosya_bilgileri:
            tur = d.dosya_turu
            tur_sayilari[tur] = tur_sayilari.get(tur, 0) + 1
        
        tur_str = ", ".join([f"{s} {t}" for t, s in tur_sayilari.items()])
        
        bilgiler = [
            ['Oluşturma Tarihi:', tarih],
            ['Toplam Evrak:', str(len(dosya_bilgileri))],
            ['İçerik:', tur_str or 'Belirtilmemiş'],
        ]
        
        tablo = Table(bilgiler, colWidths=[5*cm, 9*cm])
        tablo.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), FONT_NORMAL),
            ('FONTSIZE', (0, 0), (-1, -1), 11),
            ('FONTNAME', (0, 0), (0, -1), FONT_BOLD),
            ('TEXTCOLOR', (0, 0), (0, -1), HexColor('#1a3c5a')),
            ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
            ('ALIGN', (1, 0), (1, -1), 'LEFT'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
        ]))
        flowables.append(tablo)
        
        flowables.append(PageBreak())
        
        return flowables
    
    def _icindekiler_olustur(self, dosya_bilgileri: List[DosyaBilgisi]) -> List:
        """İçindekiler sayfası oluştur"""
        if not self.stiller:
            return []
        
        flowables = []
        
        flowables.append(Paragraph("<b>İÇİNDEKİLER</b>", self.stiller['IcindekilerBaslik']))
        flowables.append(Spacer(1, 8*mm))
        
        for i, dosya in enumerate(dosya_bilgileri, 1):
            tur_emoji = {
                'UDF': '📄',
                'PDF': '📑', 
                'TIFF': '🖼️',
                'IMG': '🖼️'
            }.get(dosya.dosya_turu, '📄')
            
            # Başlık veya dosya adı
            baslik = dosya.baslik if dosya.baslik else dosya.orijinal_ad
            if len(baslik) > 60:
                baslik = baslik[:57] + "..."
            baslik_safe = self._html_escape(baslik)
            
            flowables.append(Paragraph(
                f"{i}. {tur_emoji} {baslik_safe}",
                self.stiller['IcindekilerItem']
            ))
        
        flowables.append(PageBreak())
        
        return flowables
    
    def _footer_ekle(self, canvas, doc):
        """Sayfa footer'ı ekle"""
        canvas.saveState()
        
        # Sayfa numarası - orta
        canvas.setFont(FONT_NORMAL, 9)
        canvas.setFillColor(gray)
        canvas.drawCentredString(A4[0]/2, 1.2*cm, f"— {doc.page} —")
        
        # Tarih - sağ
        canvas.drawRightString(A4[0] - 2*cm, 1.2*cm, datetime.now().strftime('%d.%m.%Y'))
        
        canvas.restoreState()
    
    def uret(self, kaynak: str, cikti_yolu: str, baslik: str = "İCRA DOSYASI", icindekiler: bool = True) -> NeatPDFRapor:
        """
        Ana üretim metodu
        
        Args:
            kaynak: ZIP dosyası veya klasör yolu
            cikti_yolu: Çıktı PDF yolu
            baslik: Kapak başlığı
            icindekiler: İçindekiler sayfası eklensin mi
        
        Returns:
            NeatPDFRapor
        """
        import time
        baslangic = time.time()
        
        rapor = NeatPDFRapor()
        rapor.cikti_dosya = cikti_yolu
        
        if not REPORTLAB_OK:
            rapor.hatalar.append("reportlab kütüphanesi yüklü değil")
            return rapor
        
        # Stilleri oluştur
        self.stiller = self._stiller_olustur()
        
        # Temp dizin
        self.temp_dir = tempfile.mkdtemp(prefix="neat_pdf_")
        
        try:
            # Dosyaları topla
            dosya_listesi = self._dosyalari_topla(kaynak)
            rapor.toplam_dosya = len(dosya_listesi)
            
            if not dosya_listesi:
                rapor.hatalar.append("İşlenecek dosya bulunamadı")
                return rapor
            
            story = []
            ek_pdfler = []
            dosya_bilgileri = []
            
            # Önce tüm dosyaları analiz et
            for dosya_yolu in dosya_listesi:
                bilgi = self._dosya_analiz(dosya_yolu)
                dosya_bilgileri.append(bilgi)
            
            # Kapak
            story.extend(self._kapak_olustur(baslik, dosya_bilgileri))
            
            # İçindekiler (2+ dosya varsa)
            if icindekiler and len(dosya_bilgileri) > 1:
                story.extend(self._icindekiler_olustur(dosya_bilgileri))
            
            # Her dosyayı işle
            for i, (dosya_yolu, bilgi) in enumerate(zip(dosya_listesi, dosya_bilgileri), 1):
                print(f"📄 İşleniyor ({i}/{len(dosya_listesi)}): {bilgi.orijinal_ad}")
                
                if bilgi.dosya_turu == 'UDF':
                    metin, _ = self._udf_icerik_cikar(dosya_yolu)
                    if metin:
                        # Evrak header (dosya adı)
                        story.append(Paragraph(
                            f"📄 Evrak {i}: {bilgi.orijinal_ad}",
                            self.stiller['EvrakHeader']
                        ))
                        
                        # Formatlanmış içerik
                        flowables = self._metin_formatla(metin)
                        story.extend(flowables)
                        story.append(PageBreak())
                        
                        bilgi.islendi = True
                        rapor.islenen_dosya += 1
                    else:
                        bilgi.hata = "İçerik çıkarılamadı"
                        rapor.hatali_dosya += 1
                        rapor.hatalar.append(f"{bilgi.orijinal_ad}: İçerik çıkarılamadı")
                
                elif bilgi.dosya_turu == 'PDF':
                    # PDF - header ekle, sonra birleştir
                    story.append(Paragraph(
                        f"📑 Evrak {i}: {bilgi.orijinal_ad} (Orijinal PDF)",
                        self.stiller['EvrakHeader']
                    ))
                    story.append(PageBreak())
                    ek_pdfler.append(dosya_yolu)
                    bilgi.islendi = True
                    rapor.islenen_dosya += 1
                
                elif bilgi.dosya_turu in ['TIFF', 'IMG']:
                    # Görüntü - PDF'e çevir
                    story.append(Paragraph(
                        f"🖼️ Evrak {i}: {bilgi.orijinal_ad} (Görüntü)",
                        self.stiller['EvrakHeader']
                    ))
                    story.append(PageBreak())
                    
                    temp_pdf = os.path.join(self.temp_dir, f"img_{i}.pdf")
                    if self._img_to_pdf(dosya_yolu, temp_pdf):
                        ek_pdfler.append(temp_pdf)
                        bilgi.islendi = True
                        rapor.islenen_dosya += 1
                    else:
                        bilgi.hata = "Görüntü dönüştürülemedi"
                        rapor.hatali_dosya += 1
            
            rapor.dosyalar = dosya_bilgileri
            rapor.atlanan_dosya = rapor.toplam_dosya - rapor.islenen_dosya - rapor.hatali_dosya
            
            # Ana PDF'i oluştur
            ana_pdf = os.path.join(self.temp_dir, "ana.pdf")
            doc = SimpleDocTemplate(
                ana_pdf,
                pagesize=A4,
                rightMargin=2.5*cm,
                leftMargin=2.5*cm,
                topMargin=2.5*cm,
                bottomMargin=2.5*cm
            )
            
            doc.build(story, onFirstPage=self._footer_ekle, onLaterPages=self._footer_ekle)
            
            # PDF'leri birleştir
            if PYPDF2_OK:
                merger = PdfMerger()
                merger.append(ana_pdf)
                
                for ek_pdf in ek_pdfler:
                    try:
                        merger.append(ek_pdf)
                    except Exception as e:
                        rapor.hatalar.append(f"PDF birleştirme hatası: {e}")
                
                merger.write(cikti_yolu)
                merger.close()
                
                # Sayfa sayısı
                try:
                    reader = PdfReader(cikti_yolu)
                    rapor.toplam_sayfa = len(reader.pages)
                except:
                    pass
            else:
                shutil.copy(ana_pdf, cikti_yolu)
            
            print(f"\n✅ PDF oluşturuldu: {cikti_yolu}")
        
        except Exception as e:
            rapor.hatalar.append(f"Genel hata: {str(e)}")
            import traceback
            traceback.print_exc()
        
        finally:
            # Temizlik
            if self.temp_dir and os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir, ignore_errors=True)
                self.temp_dir = None
        
        rapor.sure_saniye = time.time() - baslangic
        return rapor
    
    def _dosyalari_topla(self, kaynak: str) -> List[str]:
        """Kaynaktan dosyaları topla"""
        dosyalar = []
        
        if kaynak.lower().endswith('.zip'):
            try:
                with zipfile.ZipFile(kaynak, 'r') as zf:
                    zf.extractall(self.temp_dir)
                
                for root, dirs, files in os.walk(self.temp_dir):
                    for f in sorted(files):
                        ext = os.path.splitext(f)[1].lower()
                        if ext in ['.udf', '.pdf', '.tiff', '.tif', '.jpg', '.jpeg', '.png']:
                            dosyalar.append(os.path.join(root, f))
            except Exception as e:
                print(f"ZIP açma hatası: {e}")
        
        elif os.path.isdir(kaynak):
            for f in sorted(os.listdir(kaynak)):
                ext = os.path.splitext(f)[1].lower()
                if ext in ['.udf', '.pdf', '.tiff', '.tif', '.jpg', '.jpeg', '.png']:
                    dosyalar.append(os.path.join(kaynak, f))
        
        else:
            if os.path.exists(kaynak):
                dosyalar.append(kaynak)
        
        return dosyalar
    
    def _dosya_analiz(self, dosya_yolu: str) -> DosyaBilgisi:
        """Dosyayı analiz et"""
        dosya_adi = os.path.basename(dosya_yolu)
        ext = os.path.splitext(dosya_adi)[1].lower()
        
        if ext == '.udf':
            dosya_turu = 'UDF'
        elif ext == '.pdf':
            dosya_turu = 'PDF'
        elif ext in ['.tiff', '.tif']:
            dosya_turu = 'TIFF'
        else:
            dosya_turu = 'IMG'
        
        boyut = os.path.getsize(dosya_yolu) / 1024
        
        baslik = ""
        if dosya_turu == 'UDF':
            _, baslik = self._udf_icerik_cikar(dosya_yolu)
        
        return DosyaBilgisi(
            orijinal_ad=dosya_adi,
            dosya_turu=dosya_turu,
            boyut_kb=boyut,
            baslik=baslik
        )


# Test
if __name__ == "__main__":
    print("=" * 50)
    print("NEAT PDF ÜRETİCİ v3.0 - UYAP KALİTESİNDE")
    print("=" * 50)
    print(f"reportlab: {'✅' if REPORTLAB_OK else '❌'}")
    print(f"PyPDF2: {'✅' if PYPDF2_OK else '❌'}")
    print(f"Pillow: {'✅' if PIL_OK else '❌'}")
    print(f"Font Normal: {FONT_NORMAL}")
    print(f"Font Bold: {FONT_BOLD}")
