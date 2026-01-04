#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NEAT PDF ÜRETİCİ v2.0 - Profesyonel Kalite
==========================================
UYAP UDF Editörü kalitesinde PDF çıktısı
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
        Table, TableStyle
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

# Font ayarları
FONT_NAME = 'Helvetica'

if REPORTLAB_OK:
    FONT_PATHS = [
        ('/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf', 'DejaVuSerif'),
        ('/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf', 'LiberationSerif'),
        ('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 'DejaVuSans'),
    ]
    
    for font_path, font_name in FONT_PATHS:
        if os.path.exists(font_path):
            try:
                pdfmetrics.registerFont(TTFont(font_name, font_path))
                FONT_NAME = font_name
                break
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
    """Profesyonel PDF üretici - UYAP kalitesinde"""
    
    ETIKET_PATTERNS = [
        'DAVACI', 'DAVALI', 'VEKİLİ', 'ADRES', 'KONU', 'İhbar Edilen',
        'İŞLEM YAPILACAK TARAF', 'HUKUKSAL NEDENLER', 'DELİLLER',
        'NETİCE-İ TALEP', 'AÇIKLAMALAR', 'Talep', 'BORÇLU', 'ALACAKLI',
        'DOSYA NO', 'ESAS NO', 'KARAR NO', 'TARİH', 'İşlem Yapılacak Taraf Adı'
    ]
    
    BASLIK_PATTERNS = [
        'TALEP EVRAKI', 'DİLEKÇE', 'TUTANAK', 'KARAR', 'ZABTI', 
        'RAPOR', 'İHBARNAME', 'MÜZEKKERE', 'TEBLİGAT', 'MAZBATA'
    ]
    
    def __init__(self):
        self.temp_dir = None
        self.stiller = None
        
    def _stiller_olustur(self):
        """PDF stilleri oluştur"""
        if not REPORTLAB_OK:
            return None
            
        styles = getSampleStyleSheet()
        
        # T.C. Başlık
        styles.add(ParagraphStyle(
            name='TCBaslik', fontName=FONT_NAME, fontSize=13,
            alignment=TA_CENTER, spaceAfter=2*mm, textColor=black,
        ))
        
        # Kurum Başlığı (Mahkeme, Daire vs.)
        styles.add(ParagraphStyle(
            name='KurumBaslik', fontName=FONT_NAME, fontSize=12,
            alignment=TA_CENTER, spaceAfter=3*mm, textColor=black, leading=15,
        ))
        
        # Dosya No
        styles.add(ParagraphStyle(
            name='DosyaNo', fontName=FONT_NAME, fontSize=11,
            alignment=TA_CENTER, spaceAfter=8*mm, textColor=black,
        ))
        
        # Alt Başlık (TALEP EVRAKI vs.)
        styles.add(ParagraphStyle(
            name='AltBaslik', fontName=FONT_NAME, fontSize=12,
            alignment=TA_CENTER, spaceAfter=8*mm, spaceBefore=8*mm, textColor=black,
        ))
        
        # Normal metin - justify
        styles.add(ParagraphStyle(
            name='NormalMetin', fontName=FONT_NAME, fontSize=11,
            alignment=TA_JUSTIFY, spaceAfter=3*mm, spaceBefore=1*mm,
            leading=14, firstLineIndent=0.8*cm, textColor=black,
        ))
        
        # Etiketli satır (DAVACI:, VEKİLİ: vs.)
        styles.add(ParagraphStyle(
            name='EtiketliSatir', fontName=FONT_NAME, fontSize=11,
            alignment=TA_LEFT, spaceAfter=2*mm, textColor=black, leading=14,
        ))
        
        # İmza alanı - sağa hizalı
        styles.add(ParagraphStyle(
            name='Imza', fontName=FONT_NAME, fontSize=11,
            alignment=TA_RIGHT, spaceAfter=0, spaceBefore=10*mm, textColor=black,
        ))
        
        # Tarih
        styles.add(ParagraphStyle(
            name='Tarih', fontName=FONT_NAME, fontSize=11,
            alignment=TA_LEFT, spaceAfter=5*mm, textColor=black,
        ))
        
        # Kapak başlık
        styles.add(ParagraphStyle(
            name='KapakBaslik', fontName=FONT_NAME, fontSize=18,
            alignment=TA_CENTER, spaceAfter=10*mm, spaceBefore=20*mm,
            textColor=HexColor('#1E3A5F'),
        ))
        
        # İçindekiler başlık
        styles.add(ParagraphStyle(
            name='IcindekilerBaslik', fontName=FONT_NAME, fontSize=14,
            alignment=TA_CENTER, spaceAfter=8*mm, textColor=HexColor('#1E3A5F'),
        ))
        
        # İçindekiler item
        styles.add(ParagraphStyle(
            name='IcindekilerItem', fontName=FONT_NAME, fontSize=10,
            alignment=TA_LEFT, spaceAfter=2*mm, leftIndent=5*mm,
        ))
        
        # Evrak header (gri, küçük)
        styles.add(ParagraphStyle(
            name='EvrakHeader', fontName=FONT_NAME, fontSize=10,
            alignment=TA_LEFT, textColor=gray, spaceAfter=5*mm,
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
                        content_match = re.search(r'<content>(.*?)</content>', content, re.DOTALL)
                        if content_match:
                            metin = content_match.group(1).strip()
                        else:
                            metin = re.sub(r'<[^>]+>', '', content).strip()
                    
                    # Başlık bul
                    for satir in metin.split('\n')[:10]:
                        satir = satir.strip()
                        if any(x in satir.upper() for x in ['MAHKEMESİ', 'DAİRESİ', 'MÜDÜRLÜĞÜ']):
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
        
        # Pattern'leri derle
        etiket_pattern = re.compile(
            r'^(' + '|'.join(self.ETIKET_PATTERNS) + r')\s*[:\t]',
            re.IGNORECASE
        )
        baslik_pattern = re.compile(
            r'(' + '|'.join(self.BASLIK_PATTERNS) + r')',
            re.IGNORECASE
        )
        
        ilk_satirlar = True
        tc_eklendi = False
        
        for satir in satirlar:
            satir_strip = satir.strip()
            
            if not satir_strip:
                flowables.append(Spacer(1, 3*mm))
                ilk_satirlar = False
                continue
            
            # HTML escape
            satir_safe = satir_strip.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            
            # İlk satırlar - T.C. ve Kurum başlığı
            if ilk_satirlar:
                if 'T.C.' in satir_strip.upper() or satir_strip.upper() == 'TC':
                    if not tc_eklendi:
                        flowables.append(Paragraph("<b>T.C.</b>", self.stiller['TCBaslik']))
                        tc_eklendi = True
                    continue
                elif any(x in satir_strip.upper() for x in ['MAHKEMESİ', 'DAİRESİ', 'MÜDÜRLÜĞÜ']):
                    flowables.append(Paragraph(f"<b>{satir_safe}</b>", self.stiller['KurumBaslik']))
                    continue
                elif any(x in satir_strip.upper() for x in ['ANKARA', 'İSTANBUL', 'İZMİR', 'BURSA', 'ANTALYA']):
                    flowables.append(Paragraph(f"<b>{satir_safe}</b>", self.stiller['KurumBaslik']))
                    continue
                elif re.match(r'^\d{4}/\d+', satir_strip):
                    flowables.append(Paragraph(f"<b>{satir_safe}</b>", self.stiller['DosyaNo']))
                    ilk_satirlar = False
                    continue
            
            ilk_satirlar = False
            
            # Alt başlık mı? (TALEP EVRAKI vs.)
            if baslik_pattern.search(satir_strip):
                flowables.append(Spacer(1, 5*mm))
                flowables.append(Paragraph(f"<b><u>{satir_safe}</u></b>", self.stiller['AltBaslik']))
                continue
            
            # Etiketli satır mı?
            etiket_match = etiket_pattern.match(satir_strip)
            if etiket_match:
                etiket = etiket_match.group(1)
                geri_kalan = satir_strip[etiket_match.end():].strip()
                geri_kalan_safe = geri_kalan.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                flowables.append(Paragraph(
                    f"<b>{etiket}:</b> {geri_kalan_safe}",
                    self.stiller['EtiketliSatir']
                ))
                continue
            
            # Avukat imzası mı?
            if satir_strip.startswith('Av.') or 'Vekili' in satir_strip or 'e-imzalıdır' in satir_strip.lower():
                flowables.append(Paragraph(satir_safe, self.stiller['Imza']))
                continue
            
            # Tarih satırı mı?
            if re.match(r'^\d{2}[./]\d{2}[./]\d{4}$', satir_strip):
                flowables.append(Paragraph(f"<b>Tarih:</b> {satir_safe}", self.stiller['Tarih']))
                continue
            
            # Normal metin
            flowables.append(Paragraph(satir_safe, self.stiller['NormalMetin']))
        
        return flowables
    
    def _img_to_pdf(self, img_path: str, pdf_path: str) -> bool:
        """Görüntüyü PDF'e dönüştür"""
        if not PIL_OK:
            return False
        
        try:
            img = Image.open(img_path)
            
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
        flowables.append(Spacer(1, 3*cm))
        flowables.append(Paragraph("<b>T.C.</b>", self.stiller['TCBaslik']))
        
        baslik_safe = baslik.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        flowables.append(Paragraph(f"<b>{baslik_safe}</b>", self.stiller['KapakBaslik']))
        flowables.append(Spacer(1, 2*cm))
        
        tarih = datetime.now().strftime('%d.%m.%Y %H:%M')
        bilgiler = [
            ['Oluşturma Tarihi:', tarih],
            ['Toplam Evrak:', str(len(dosya_bilgileri))],
            ['Format:', 'Birleşik PDF'],
        ]
        
        tablo = Table(bilgiler, colWidths=[5*cm, 8*cm])
        tablo.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), FONT_NAME),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('TEXTCOLOR', (0, 0), (0, -1), HexColor('#1E3A5F')),
            ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
            ('ALIGN', (1, 0), (1, -1), 'LEFT'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
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
        flowables.append(Spacer(1, 5*mm))
        
        for i, dosya in enumerate(dosya_bilgileri, 1):
            tur_emoji = {'UDF': '📄', 'PDF': '📑', 'TIFF': '🖼️', 'IMG': '🖼️'}.get(dosya.dosya_turu, '📄')
            baslik = dosya.baslik if dosya.baslik else dosya.orijinal_ad
            baslik_safe = (baslik[:50] + "..." if len(baslik) > 50 else baslik)
            baslik_safe = baslik_safe.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            flowables.append(Paragraph(f"{i}. {tur_emoji} {baslik_safe}", self.stiller['IcindekilerItem']))
        
        flowables.append(PageBreak())
        return flowables
    
    def _footer_ekle(self, canvas, doc):
        """Sayfa footer'ı ekle"""
        canvas.saveState()
        canvas.setFont(FONT_NAME, 9)
        canvas.setFillColor(gray)
        canvas.drawCentredString(A4[0]/2, 1*cm, f"Sayfa {doc.page}")
        canvas.drawRightString(A4[0] - 2.5*cm, 1*cm, datetime.now().strftime('%d.%m.%Y'))
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
        
        self.stiller = self._stiller_olustur()
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
            
            # İçindekiler
            if icindekiler and len(dosya_bilgileri) > 1:
                story.extend(self._icindekiler_olustur(dosya_bilgileri))
            
            # Her dosyayı işle
            for i, (dosya_yolu, bilgi) in enumerate(zip(dosya_listesi, dosya_bilgileri), 1):
                print(f"📄 İşleniyor ({i}/{len(dosya_listesi)}): {bilgi.orijinal_ad}")
                
                if bilgi.dosya_turu == 'UDF':
                    metin, _ = self._udf_icerik_cikar(dosya_yolu)
                    if metin:
                        # Evrak header
                        story.append(Paragraph(
                            f"<b>📄 {i}. {bilgi.orijinal_ad}</b>",
                            self.stiller['EvrakHeader']
                        ))
                        
                        # T.C. ekle (eğer metinde yoksa)
                        if 'T.C.' not in metin[:100].upper():
                            story.append(Paragraph("<b>T.C.</b>", self.stiller['TCBaslik']))
                        
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
                    story.append(Paragraph(
                        f"<b>📑 {i}. {bilgi.orijinal_ad}</b> (Orijinal PDF)",
                        self.stiller['EvrakHeader']
                    ))
                    story.append(PageBreak())
                    ek_pdfler.append(dosya_yolu)
                    bilgi.islendi = True
                    rapor.islenen_dosya += 1
                
                elif bilgi.dosya_turu in ['TIFF', 'IMG']:
                    story.append(Paragraph(
                        f"<b>🖼️ {i}. {bilgi.orijinal_ad}</b> (Görüntü)",
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
                ana_pdf, pagesize=A4,
                rightMargin=2.5*cm, leftMargin=2.5*cm,
                topMargin=2*cm, bottomMargin=2*cm
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
    print("NEAT PDF ÜRETİCİ v2.0")
    print(f"reportlab: {'✅' if REPORTLAB_OK else '❌'}")
    print(f"PyPDF2: {'✅' if PYPDF2_OK else '❌'}")
    print(f"Pillow: {'✅' if PIL_OK else '❌'}")
    print(f"Font: {FONT_NAME}")
