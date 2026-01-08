#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NEAT PDF ÜRETİCİ v5.0 - ULTIMATE DEEP CLEAN
===========================================
Karmaşık, iç içe geçmiş (nested) ZIP ve Klasör yapılarını
dümdüz eder ve tek bir profesyonel PDF haline getirir.

Özellikler:
- Recursive ZIP Extraction (ZIP içindeki ZIP'i açar)
- Deep Directory Walk (Klasör içindeki klasörü tarar)
- Multi-page TIFF desteği
- UDF XML Parsing
"""

import os
import re
import zipfile
import tempfile
import shutil
import mimetypes
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

# Gerekli Kütüphaneler
try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm, mm
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY, TA_RIGHT
    from reportlab.lib.colors import black, gray, HexColor
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle
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
    baslik: str = ""
    hata: Optional[str] = None

@dataclass 
class NeatPDFRapor:
    cikti_dosya: str = ""
    toplam_dosya: int = 0
    islenen_dosya: int = 0
    hatalar: List[str] = field(default_factory=list)
    sure_saniye: float = 0.0

class NeatPDFUretici:
    
    def __init__(self):
        self.temp_dir = None
        self.stiller = None
        self.font_name = 'Helvetica'
        self._font_yukle()

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
                    pdfmetrics.registerFont(TTFont('TrFontBd', yol.replace('Regular', 'Bold').replace('Serif', 'Serif-Bold'))) # Basit bold mantığı
                    self.font_name = 'TrFont'
                    return
                except:
                    pass

    def _recursive_zip_extract(self, klasor_yolu: str):
        """
        Matruşka ZIP Çözücü:
        Bir klasördeki tüm ZIP'leri bulur, açar, içinden çıkan ZIP'leri de açar.
        Sonsuz döngüyü engeller.
        """
        zip_bulundu = True
        while zip_bulundu:
            zip_bulundu = False
            for root, dirs, files in os.walk(klasor_yolu):
                for file in files:
                    if file.lower().endswith('.zip') or file.lower().endswith('.rar'): # Rar desteği ek kütüphane ister
                        tam_yol = os.path.join(root, file)
                        try:
                            # ZIP ise olduğu yere klasör olarak aç
                            hedef_klasor = os.path.join(root, os.path.splitext(file)[0])
                            
                            # Eğer zaten açılmışsa atla (sonsuz döngü koruması)
                            if os.path.exists(hedef_klasor):
                                continue

                            with zipfile.ZipFile(tam_yol, 'r') as zf:
                                zf.extractall(hedef_klasor)
                            
                            # Orijinal ZIP'i sil (veya ismini değiştir) ki tekrar işlenmesin
                            os.remove(tam_yol) 
                            zip_bulundu = True # Yeni dosyalar çıktı, tekrar taramalıyız
                        except Exception as e:
                            print(f"ZIP açma hatası ({file}): {e}")

    def _dosyalari_topla_ve_duzlestir(self, kok_dizin: str) -> List[DosyaBilgisi]:
        """Tüm alt klasörleri tarar ve tek bir liste haline getirir"""
        
        # Önce tüm iç içe ZIP'leri patlat
        self._recursive_zip_extract(kok_dizin)
        
        toplanan_dosyalar = []
        
        for root, dirs, files in os.walk(kok_dizin):
            for file in files:
                ext = os.path.splitext(file)[1].lower()
                tam_yol = os.path.join(root, file)
                
                # Dosya türü tespiti
                tur = "BILINMIYOR"
                if ext == '.udf': tur = 'UDF'
                elif ext == '.pdf': tur = 'PDF'
                elif ext in ['.tif', '.tiff']: tur = 'TIFF'
                elif ext in ['.jpg', '.jpeg', '.png']: tur = 'IMG'
                elif ext == '.xml': tur = 'XML' # Bazen UDF'ler XML olarak iner
                
                if tur != "BILINMIYOR":
                    tarih = datetime.fromtimestamp(os.path.getmtime(tam_yol))
                    toplanan_dosyalar.append(DosyaBilgisi(
                        orijinal_ad=file,
                        dosya_turu=tur,
                        tam_yol=tam_yol,
                        tarih=tarih
                    ))
        
        # Tarihe göre sırala (Eskiden yeniye)
        toplanan_dosyalar.sort(key=lambda x: x.tarih)
        return toplanan_dosyalar

    def _udf_oku(self, udf_path: str) -> str:
        """UDF (XML) içeriğini okur, CDATA temizler"""
        metin = ""
        try:
            # UDF aslında ZIP'tir
            with zipfile.ZipFile(udf_path, 'r') as zf:
                if 'content.xml' in zf.namelist():
                    xml_data = zf.read('content.xml')
                    try:
                        # Encoding sorunlarını çözmeye çalış
                        xml_str = xml_data.decode('utf-8')
                    except UnicodeDecodeError:
                        xml_str = xml_data.decode('latin-1')

                    # XML Parse etmeden regex ile CDATA al (Bazen XML bozuk oluyor)
                    # CDATA içindeki her şeyi al
                    cdata_pattern = re.compile(r'<!\[CDATA\[(.*?)\]\]>', re.DOTALL)
                    matches = cdata_pattern.findall(xml_str)
                    
                    if matches:
                        metin = "\n".join(matches)
                    else:
                        # CDATA yoksa saf text çıkarmaya çalış (ElementTree ile)
                        root = ET.fromstring(xml_data)
                        text_list = [elem.text for elem in root.iter() if elem.text]
                        metin = "\n".join(text_list)

        except zipfile.BadZipFile:
            # Belki de ZIP değil düz XML'dir?
            try:
                with open(udf_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    if '<content>' in content:
                         cdata_pattern = re.compile(r'<!\[CDATA\[(.*?)\]\]>', re.DOTALL)
                         matches = cdata_pattern.findall(content)
                         metin = "\n".join(matches)
            except:
                pass
        except Exception as e:
            print(f"UDF okuma hatası: {e}")
            
        return metin.strip()

    def _tiff_to_pdf(self, tiff_path: str) -> List[str]:
        """TIFF'i (çok sayfalı olabilir) geçici PDF'lere çevirir"""
        pdf_paths = []
        try:
            img = Image.open(tiff_path)
            # Çoklu sayfa desteği
            for i, page in enumerate(ImageSequence.Iterator(img)):
                page = page.convert("RGB")
                temp_pdf = os.path.join(self.temp_dir, f"{os.path.basename(tiff_path)}_{i}.pdf")
                page.save(temp_pdf, "PDF", resolution=100.0)
                pdf_paths.append(temp_pdf)
        except Exception as e:
            print(f"TIFF convert hatası: {e}")
        return pdf_paths

    def _stiller_olustur(self):
        styles = getSampleStyleSheet()
        styles.add(ParagraphStyle(name='TrBaslik', fontName=self.font_name, fontSize=14, leading=18, alignment=TA_CENTER, spaceAfter=10))
        styles.add(ParagraphStyle(name='TrNormal', fontName=self.font_name, fontSize=10, leading=14, alignment=TA_JUSTIFY, firstLineIndent=20))
        styles.add(ParagraphStyle(name='TrMeta', fontName=self.font_name, fontSize=8, textColor=gray, alignment=TA_RIGHT))
        return styles

    def uret(self, kaynak_yol: str, cikti_yol: str, baslik="İcra Dosyası") -> NeatPDFRapor:
        import time
        start_time = time.time()
        
        if not REPORTLAB_OK:
            return NeatPDFRapor(hatalar=["ReportLab kütüphanesi eksik"])

        self.temp_dir = tempfile.mkdtemp()
        rapor = NeatPDFRapor(cikti_dosya=cikti_yol)
        
        try:
            # 1. Kaynağı Hazırla (ZIP ise aç)
            islem_dizini = os.path.join(self.temp_dir, "work")
            os.makedirs(islem_dizini, exist_ok=True)

            if os.path.isfile(kaynak_yol) and kaynak_yol.lower().endswith('.zip'):
                with zipfile.ZipFile(kaynak_yol, 'r') as zf:
                    zf.extractall(islem_dizini)
            elif os.path.isdir(kaynak_yol):
                # Klasör kopyala ki orijinal bozulmasın
                import distutils.dir_util
                distutils.dir_util.copy_tree(kaynak_yol, islem_dizini)
            else:
                # Tek dosya
                shutil.copy(kaynak_yol, islem_dizini)

            # 2. Dosyaları Topla ve Düzleştir
            dosyalar = self._dosyalari_topla_ve_duzlestir(islem_dizini)
            rapor.toplam_dosya = len(dosyalar)
            rapor.dosyalar = dosyalar

            # 3. PDF Üretim Hazırlığı
            styles = self._stiller_olustur()
            story = []
            
            # Kapak
            story.append(Spacer(1, 3*cm))
            story.append(Paragraph("<b>T.C.</b>", styles['TrBaslik']))
            story.append(Paragraph(f"<b>{baslik}</b>", styles['TrBaslik']))
            story.append(Spacer(1, 2*cm))
            story.append(Paragraph(f"Oluşturma Tarihi: {datetime.now().strftime('%d.%m.%Y %H:%M')}", styles['TrBaslik']))
            story.append(Paragraph(f"Toplam Evrak Sayısı: {len(dosyalar)}", styles['TrBaslik']))
            story.append(PageBreak())

            # İçindekiler
            story.append(Paragraph("<b>İÇİNDEKİLER</b>", styles['TrBaslik']))
            story.append(Spacer(1, 1*cm))
            for i, dosya in enumerate(dosyalar, 1):
                story.append(Paragraph(f"{i}. {dosya.orijinal_ad} ({dosya.dosya_turu}) - {dosya.tarih.strftime('%d.%m.%Y')}", styles['TrNormal']))
            story.append(PageBreak())

            # 4. İçerik İşleme (ReportLab Flowables oluşturma)
            # Not: PDF ve TIFF'leri sona PyPDF2 ile ekleyeceğiz, burada sadece UDF ve metinleri işliyoruz.
            # Ancak sayfa numarası tutarlılığı için araya "Ekli Dosya: X" sayfası koyabiliriz.
            
            temp_content_pdf = os.path.join(self.temp_dir, "temp_content.pdf")
            final_merger = PdfMerger()
            
            # Önce ReportLab içeriğini (UDF'ler ve Kapak) oluştur
            doc = SimpleDocTemplate(temp_content_pdf, pagesize=A4, rightMargin=2*cm, leftMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm)
            
            # Geçici bir liste tutacağız, her dosya için
            # Eğer UDF ise -> Story'ye ekle
            # Eğer PDF/TIFF ise -> Story'ye "Bkz: Sonraki Sayfa" ekle, sonra Merger'a dosyayı ekle
            
            # Bu karmaşık yapı yerine strateji değiştiriyoruz:
            # Her şeyi parçalı PDF yapıp en sonda birleştireceğiz.
            
            pdf_parcalari = [] # (PDF_PATH, KaynakDosyaAdi)
            
            # Kapak ve İçindekiler PDF'i
            cover_pdf = os.path.join(self.temp_dir, "000_cover.pdf")
            doc_cover = SimpleDocTemplate(cover_pdf, pagesize=A4)
            doc_cover.build(story)
            pdf_parcalari.append(cover_pdf)

            for i, dosya in enumerate(dosyalar, 1):
                print(f"İşleniyor: {dosya.orijinal_ad} ({dosya.dosya_turu})")
                
                # Her dosya için ayrı bir PDF oluşturup listeye ekleyeceğiz
                if dosya.dosya_turu == 'UDF' or dosya.dosya_turu == 'XML':
                    metin = self._udf_oku(dosya.tam_yol)
                    if metin:
                        udf_pdf_path = os.path.join(self.temp_dir, f"{i:03d}_udf.pdf")
                        udf_story = []
                        udf_story.append(Paragraph(f"<b>Evrak #{i}: {dosya.orijinal_ad}</b>", styles['TrBaslik']))
                        udf_story.append(Paragraph(f"Tarih: {dosya.tarih.strftime('%d.%m.%Y')}", styles['TrMeta']))
                        udf_story.append(Spacer(1, 0.5*cm))
                        
                        # Metni paragraflara böl ve ekle
                        for par in metin.split('\n'):
                            if par.strip():
                                # Basit formatlama: Eğer satır sonunda ":" varsa ve kısa ise (Etiket), bold yap
                                if par.strip().endswith(':') and len(par) < 30:
                                    udf_story.append(Paragraph(f"<b>{par}</b>", styles['TrNormal']))
                                else:
                                    udf_story.append(Paragraph(par, styles['TrNormal']))
                                udf_story.append(Spacer(1, 0.1*cm))
                        
                        try:
                            SimpleDocTemplate(udf_pdf_path, pagesize=A4).build(udf_story)
                            pdf_parcalari.append(udf_pdf_path)
                            rapor.islenen_dosya += 1
                        except Exception as e:
                            rapor.hatalar.append(f"{dosya.orijinal_ad} PDF'e çevrilemedi: {e}")

                elif dosya.dosya_turu == 'PDF':
                    # Orijinal PDF'i direkt kullan
                    # Ancak bozuksa kontrol et
                    try:
                        PdfReader(dosya.tam_yol) # Test read
                        pdf_parcalari.append(dosya.tam_yol)
                        rapor.islenen_dosya += 1
                    except:
                        rapor.hatalar.append(f"{dosya.orijinal_ad} bozuk PDF")

                elif dosya.dosya_turu == 'TIFF' or dosya.dosya_turu == 'IMG':
                    # Görüntüleri PDF yap
                    img_pdfs = self._tiff_to_pdf(dosya.tam_yol)
                    if img_pdfs:
                        pdf_parcalari.extend(img_pdfs)
                        rapor.islenen_dosya += 1
                    else:
                        rapor.hatalar.append(f"{dosya.orijinal_ad} dönüştürülemedi")

            # 5. Final Birleştirme
            for pdf in pdf_parcalari:
                try:
                    final_merger.append(pdf)
                except Exception as e:
                    print(f"Merge hatası ({pdf}): {e}")

            final_merger.write(cikti_yol)
            final_merger.close()
            
            # Sayfa sayısı
            try:
                reader = PdfReader(cikti_yol)
                rapor.toplam_sayfa = len(reader.pages)
            except:
                pass

        except Exception as e:
            rapor.hatalar.append(f"Kritik Hata: {str(e)}")
            import traceback
            traceback.print_exc()
        
        finally:
            # Temizlik
            if self.temp_dir and os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir, ignore_errors=True)
        
        rapor.sure_saniye = time.time() - start_time
        return rapor
