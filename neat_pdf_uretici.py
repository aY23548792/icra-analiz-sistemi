#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NEAT PDF ÜRETİCİ v1.0
=====================
UYAP ZIP dosyalarını düzgün, profesyonel, tek PDF'e dönüştürür.

Özellikler:
- ZIP/RAR içindeki tüm dosyaları aç
- UDF → Metin çıkar → PDF sayfası
- TIFF/PNG/JPG → PDF sayfası
- PDF → Doğrudan ekle
- Sayfa numaraları
- Başlık ve kaynak bilgisi
- İçindekiler sayfası
- Tarih damgası
"""

import os
import re
import zipfile
import tempfile
import shutil
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from pathlib import Path
import xml.etree.ElementTree as ET
import io

# Kütüphane kontrolleri
REPORTLAB_OK = False
PYPDF2_OK = False
PIL_OK = False
PDFPLUMBER_OK = False

# PDF oluşturma - reportlab
try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm, mm
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
    from reportlab.lib.colors import HexColor, black, gray, white
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, PageBreak, 
        Table, TableStyle, Image as RLImage, KeepTogether
    )
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    REPORTLAB_OK = True
except ImportError as e:
    print(f"⚠️ reportlab yüklenemedi: {e}")
except Exception as e:
    print(f"⚠️ reportlab hatası: {e}")

# PDF birleştirme - PyPDF2
try:
    from PyPDF2 import PdfMerger, PdfReader, PdfWriter
    PYPDF2_OK = True
except ImportError as e:
    print(f"⚠️ PyPDF2 yüklenemedi: {e}")
except Exception as e:
    print(f"⚠️ PyPDF2 hatası: {e}")

# Görüntü işleme - Pillow
try:
    from PIL import Image
    PIL_OK = True
except ImportError as e:
    print(f"⚠️ Pillow yüklenemedi: {e}")
except Exception as e:
    print(f"⚠️ Pillow hatası: {e}")

# PDF okuma - pdfplumber
try:
    import pdfplumber
    PDFPLUMBER_OK = True
except ImportError as e:
    print(f"⚠️ pdfplumber yüklenemedi: {e}")
except Exception as e:
    print(f"⚠️ pdfplumber hatası: {e}")


# ============================================================================
# VERİ YAPILARI
# ============================================================================

@dataclass
class DosyaBilgisi:
    """İşlenen dosya bilgisi"""
    orijinal_ad: str
    dosya_turu: str  # UDF, PDF, TIFF, IMG, XML, TXT
    sayfa_sayisi: int = 1
    boyut_kb: float = 0
    metin_uzunluk: int = 0
    baslik: str = ""
    tarih: Optional[datetime] = None
    hata: Optional[str] = None
    islendi: bool = False


@dataclass 
class NeatPDFRapor:
    """PDF üretim raporu"""
    cikti_dosya: str = ""
    toplam_dosya: int = 0
    islenen_dosya: int = 0
    atlanan_dosya: int = 0
    hatali_dosya: int = 0
    toplam_sayfa: int = 0
    dosyalar: List[DosyaBilgisi] = field(default_factory=list)
    hatalar: List[str] = field(default_factory=list)
    sure_saniye: float = 0


# ============================================================================
# NEAT PDF ÜRETİCİ
# ============================================================================

class NeatPDFUretici:
    """UYAP dosyalarını düzgün PDF'e dönüştürür"""
    
    # Desteklenen dosya türleri
    UDF_UZANTILAR = ['.udf']
    PDF_UZANTILAR = ['.pdf']
    IMG_UZANTILAR = ['.tiff', '.tif', '.png', '.jpg', '.jpeg', '.bmp', '.gif']
    TXT_UZANTILAR = ['.txt', '.xml', '.html', '.htm']
    
    # Renkler
    HEADER_COLOR = HexColor('#1E3A5F')
    ACCENT_COLOR = HexColor('#2196F3')
    LIGHT_BG = HexColor('#F5F5F5')
    
    def __init__(self):
        self.temp_dir = None
        self.sayac = 0
        self._font_ayarla()
    
    def _font_ayarla(self):
        """Türkçe karakter destekli font ayarla"""
        # Sistem fontlarını dene
        font_yollari = [
            '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
            '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',
            '/usr/share/fonts/truetype/freefont/FreeSans.ttf',
            'C:/Windows/Fonts/arial.ttf',
            'C:/Windows/Fonts/segoeui.ttf',
        ]
        
        self.font_adi = 'Helvetica'  # Varsayılan
        
        if REPORTLAB_OK:
            for font_yolu in font_yollari:
                if os.path.exists(font_yolu):
                    try:
                        pdfmetrics.registerFont(TTFont('TurkceFont', font_yolu))
                        self.font_adi = 'TurkceFont'
                        break
                    except:
                        continue
    
    def _stiller_olustur(self):
        """PDF stilleri oluştur"""
        stiller = getSampleStyleSheet()
        
        # Ana başlık
        stiller.add(ParagraphStyle(
            name='AnaBaslik',
            fontName=self.font_adi,
            fontSize=18,
            textColor=self.HEADER_COLOR,
            alignment=TA_CENTER,
            spaceAfter=20,
            spaceBefore=10,
        ))
        
        # Alt başlık
        stiller.add(ParagraphStyle(
            name='AltBaslik',
            fontName=self.font_adi,
            fontSize=14,
            textColor=self.HEADER_COLOR,
            alignment=TA_LEFT,
            spaceAfter=10,
            spaceBefore=15,
            borderColor=self.ACCENT_COLOR,
            borderWidth=0,
            borderPadding=5,
        ))
        
        # Dosya başlığı
        stiller.add(ParagraphStyle(
            name='DosyaBaslik',
            fontName=self.font_adi,
            fontSize=12,
            textColor=white,
            backColor=self.HEADER_COLOR,
            alignment=TA_LEFT,
            spaceAfter=5,
            spaceBefore=10,
            leftIndent=5,
            rightIndent=5,
            borderPadding=8,
        ))
        
        # Normal metin
        stiller.add(ParagraphStyle(
            name='NormalMetin',
            fontName=self.font_adi,
            fontSize=10,
            textColor=black,
            alignment=TA_JUSTIFY,
            spaceAfter=6,
            spaceBefore=3,
            leading=14,
        ))
        
        # Küçük metin (kaynak bilgisi)
        stiller.add(ParagraphStyle(
            name='KucukMetin',
            fontName=self.font_adi,
            fontSize=8,
            textColor=gray,
            alignment=TA_LEFT,
            spaceAfter=3,
        ))
        
        # İçindekiler
        stiller.add(ParagraphStyle(
            name='Icindekiler',
            fontName=self.font_adi,
            fontSize=10,
            textColor=black,
            alignment=TA_LEFT,
            spaceAfter=4,
            leftIndent=10,
        ))
        
        return stiller
    
    # ========================================================================
    # DOSYA OKUMA
    # ========================================================================
    
    def _udf_oku(self, dosya_yolu: str) -> Tuple[str, str]:
        """
        UDF dosyasından metin çıkar
        Returns: (metin, baslik)
        """
        metin = ""
        baslik = os.path.basename(dosya_yolu)
        
        try:
            # UDF aslında bir ZIP
            with zipfile.ZipFile(dosya_yolu, 'r') as zf:
                for name in zf.namelist():
                    if name.endswith('.xml'):
                        with zf.open(name) as f:
                            content = f.read().decode('utf-8', errors='ignore')
                            
                            # XML parse et
                            try:
                                root = ET.fromstring(content)
                                
                                # Başlık bul
                                for tag in ['baslik', 'title', 'konu', 'subject']:
                                    elem = root.find(f'.//{tag}')
                                    if elem is not None and elem.text:
                                        baslik = elem.text.strip()
                                        break
                                
                                # Metin çıkar
                                for elem in root.iter():
                                    if elem.text and elem.text.strip():
                                        metin += elem.text.strip() + "\n"
                                    if elem.tail and elem.tail.strip():
                                        metin += elem.tail.strip() + "\n"
                            except ET.ParseError:
                                # XML değilse düz metin olarak al
                                metin = content
                    
                    elif name.endswith('.txt'):
                        with zf.open(name) as f:
                            metin += f.read().decode('utf-8', errors='ignore')
        except zipfile.BadZipFile:
            # UDF değilse düz dosya olarak dene
            try:
                with open(dosya_yolu, 'r', encoding='utf-8', errors='ignore') as f:
                    metin = f.read()
            except:
                pass
        except Exception as e:
            metin = f"[Dosya okunamadı: {str(e)}]"
        
        return metin.strip(), baslik
    
    def _pdf_sayfa_sayisi(self, dosya_yolu: str) -> int:
        """PDF sayfa sayısını al"""
        try:
            if PYPDF2_OK:
                reader = PdfReader(dosya_yolu)
                return len(reader.pages)
        except:
            pass
        return 1
    
    def _img_to_pdf_bytes(self, dosya_yolu: str) -> Optional[bytes]:
        """Görüntüyü PDF'e dönüştür"""
        if not PIL_OK:
            return None
        
        try:
            img = Image.open(dosya_yolu)
            
            # RGBA ise RGB'ye çevir
            if img.mode == 'RGBA':
                bg = Image.new('RGB', img.size, (255, 255, 255))
                bg.paste(img, mask=img.split()[3])
                img = bg
            elif img.mode != 'RGB':
                img = img.convert('RGB')
            
            # Multi-page TIFF kontrolü
            sayfalar = []
            try:
                while True:
                    frame = img.copy()
                    if frame.mode != 'RGB':
                        frame = frame.convert('RGB')
                    sayfalar.append(frame)
                    img.seek(img.tell() + 1)
            except EOFError:
                pass
            
            if not sayfalar:
                sayfalar = [img]
            
            # PDF'e kaydet
            buffer = io.BytesIO()
            if len(sayfalar) == 1:
                sayfalar[0].save(buffer, 'PDF', resolution=150)
            else:
                sayfalar[0].save(buffer, 'PDF', resolution=150, save_all=True, append_images=sayfalar[1:])
            
            return buffer.getvalue()
        except Exception as e:
            print(f"Görüntü dönüştürme hatası: {e}")
            return None
    
    def _txt_oku(self, dosya_yolu: str) -> str:
        """Metin dosyası oku"""
        try:
            with open(dosya_yolu, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read()
        except:
            return ""
    
    # ========================================================================
    # DOSYA TÜRLERİNİ SINIFLANDIR
    # ========================================================================
    
    def _dosya_turu_belirle(self, dosya_adi: str) -> str:
        """Dosya türünü belirle"""
        ext = os.path.splitext(dosya_adi)[1].lower()
        
        if ext in self.UDF_UZANTILAR:
            return 'UDF'
        elif ext in self.PDF_UZANTILAR:
            return 'PDF'
        elif ext in self.IMG_UZANTILAR:
            return 'IMG'
        elif ext in self.TXT_UZANTILAR:
            return 'TXT'
        else:
            return 'DIGER'
    
    def _dosya_baslik_cikar(self, dosya_adi: str) -> str:
        """Dosya adından okunabilir başlık çıkar"""
        # Uzantıyı kaldır
        baslik = os.path.splitext(dosya_adi)[0]
        
        # Alt çizgileri ve tireleri boşluğa çevir
        baslik = baslik.replace('_', ' ').replace('-', ' ')
        
        # Evrak numaralarını temizle
        baslik = re.sub(r'evrak_?\d+', '', baslik, flags=re.IGNORECASE)
        
        # Fazla boşlukları temizle
        baslik = ' '.join(baslik.split())
        
        return baslik.strip() or dosya_adi
    
    # ========================================================================
    # ANA ÜRETİM FONKSİYONU
    # ========================================================================
    
    def uret(self, kaynak: str, cikti_yolu: str = None, 
             baslik: str = "İCRA DOSYASI", 
             icindekiler: bool = True) -> NeatPDFRapor:
        """
        Kaynaktan (ZIP veya klasör) neat PDF üret
        
        Args:
            kaynak: ZIP dosyası veya klasör yolu
            cikti_yolu: Çıktı PDF yolu (None ise otomatik)
            baslik: PDF ana başlığı
            icindekiler: İçindekiler sayfası ekle
        
        Returns:
            NeatPDFRapor
        """
        if not REPORTLAB_OK:
            return NeatPDFRapor(hatalar=["reportlab kütüphanesi yüklü değil"])
        
        baslangic = datetime.now()
        rapor = NeatPDFRapor()
        
        # Geçici dizin oluştur
        self.temp_dir = tempfile.mkdtemp(prefix="neat_pdf_")
        
        try:
            # Kaynağı aç
            dosya_listesi = self._kaynak_ac(kaynak)
            rapor.toplam_dosya = len(dosya_listesi)
            
            if not dosya_listesi:
                rapor.hatalar.append("Hiç dosya bulunamadı")
                return rapor
            
            # Çıktı yolu
            if cikti_yolu is None:
                cikti_yolu = os.path.join(
                    os.path.dirname(kaynak) if os.path.isfile(kaynak) else kaynak,
                    f"BIRLESIK_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
                )
            
            # PDF oluştur
            story = []
            stiller = self._stiller_olustur()
            
            # Kapak sayfası
            story.extend(self._kapak_olustur(baslik, rapor.toplam_dosya, stiller))
            story.append(PageBreak())
            
            # İçindekiler için bilgi topla
            icindekiler_bilgi = []
            
            # Her dosyayı işle
            for dosya_yolu in sorted(dosya_listesi):
                dosya_adi = os.path.basename(dosya_yolu)
                dosya_turu = self._dosya_turu_belirle(dosya_adi)
                
                bilgi = DosyaBilgisi(
                    orijinal_ad=dosya_adi,
                    dosya_turu=dosya_turu,
                    baslik=self._dosya_baslik_cikar(dosya_adi)
                )
                
                try:
                    # Dosya boyutu
                    bilgi.boyut_kb = os.path.getsize(dosya_yolu) / 1024
                    
                    # Türe göre işle
                    if dosya_turu == 'UDF':
                        metin, udf_baslik = self._udf_oku(dosya_yolu)
                        if udf_baslik and udf_baslik != dosya_adi:
                            bilgi.baslik = udf_baslik
                        
                        if metin:
                            bilgi.metin_uzunluk = len(metin)
                            bilgi.islendi = True
                            
                            # PDF'e ekle
                            icindekiler_bilgi.append((bilgi.baslik, len(story)))
                            story.extend(self._metin_sayfasi_olustur(metin, bilgi, stiller))
                            story.append(PageBreak())
                            rapor.islenen_dosya += 1
                        else:
                            bilgi.hata = "Metin çıkarılamadı"
                            rapor.atlanan_dosya += 1
                    
                    elif dosya_turu == 'PDF':
                        # PDF'leri sonra birleştireceğiz
                        sayfa = self._pdf_sayfa_sayisi(dosya_yolu)
                        bilgi.sayfa_sayisi = sayfa
                        bilgi.islendi = True
                        icindekiler_bilgi.append((bilgi.baslik, f"PDF-{dosya_yolu}"))
                        rapor.islenen_dosya += 1
                        rapor.toplam_sayfa += sayfa
                    
                    elif dosya_turu == 'IMG':
                        # Görüntüyü PDF'e dönüştür
                        pdf_bytes = self._img_to_pdf_bytes(dosya_yolu)
                        if pdf_bytes:
                            # Geçici PDF olarak kaydet
                            temp_pdf = os.path.join(self.temp_dir, f"img_{self.sayac}.pdf")
                            self.sayac += 1
                            with open(temp_pdf, 'wb') as f:
                                f.write(pdf_bytes)
                            
                            bilgi.islendi = True
                            icindekiler_bilgi.append((bilgi.baslik, f"PDF-{temp_pdf}"))
                            rapor.islenen_dosya += 1
                        else:
                            bilgi.hata = "Görüntü dönüştürülemedi"
                            rapor.atlanan_dosya += 1
                    
                    elif dosya_turu == 'TXT':
                        metin = self._txt_oku(dosya_yolu)
                        if metin:
                            bilgi.metin_uzunluk = len(metin)
                            bilgi.islendi = True
                            
                            icindekiler_bilgi.append((bilgi.baslik, len(story)))
                            story.extend(self._metin_sayfasi_olustur(metin, bilgi, stiller))
                            story.append(PageBreak())
                            rapor.islenen_dosya += 1
                        else:
                            bilgi.hata = "Boş dosya"
                            rapor.atlanan_dosya += 1
                    
                    else:
                        bilgi.hata = "Desteklenmeyen format"
                        rapor.atlanan_dosya += 1
                
                except Exception as e:
                    bilgi.hata = str(e)
                    rapor.hatali_dosya += 1
                    rapor.hatalar.append(f"{dosya_adi}: {str(e)}")
                
                rapor.dosyalar.append(bilgi)
            
            # İçindekiler ekle (başa)
            if icindekiler and icindekiler_bilgi:
                icindekiler_story = self._icindekiler_olustur(icindekiler_bilgi, stiller)
                # Kapak + içindekiler + içerik
                story = story[:2] + icindekiler_story + [PageBreak()] + story[2:]
            
            # Ana PDF'i oluştur
            ana_pdf = os.path.join(self.temp_dir, "ana.pdf")
            doc = SimpleDocTemplate(
                ana_pdf,
                pagesize=A4,
                rightMargin=2*cm,
                leftMargin=2*cm,
                topMargin=2*cm,
                bottomMargin=2*cm
            )
            
            # Sayfa numarası callback
            def sayfa_numarasi(canvas, doc):
                canvas.saveState()
                canvas.setFont(self.font_adi, 8)
                canvas.setFillColor(gray)
                sayfa_no = f"Sayfa {doc.page}"
                canvas.drawCentredString(A4[0]/2, 1*cm, sayfa_no)
                # Tarih damgası
                tarih = datetime.now().strftime('%d.%m.%Y %H:%M')
                canvas.drawRightString(A4[0] - 2*cm, 1*cm, tarih)
                canvas.restoreState()
            
            doc.build(story, onFirstPage=sayfa_numarasi, onLaterPages=sayfa_numarasi)
            
            # PDF'leri birleştir
            if PYPDF2_OK:
                merger = PdfMerger()
                merger.append(ana_pdf)
                
                # Ek PDF'leri ekle
                for baslik, ref in icindekiler_bilgi:
                    if isinstance(ref, str) and ref.startswith('PDF-'):
                        pdf_yolu = ref[4:]
                        if os.path.exists(pdf_yolu):
                            try:
                                merger.append(pdf_yolu)
                            except Exception as e:
                                rapor.hatalar.append(f"PDF birleştirme: {baslik} - {e}")
                
                # Kaydet
                merger.write(cikti_yolu)
                merger.close()
            else:
                # Sadece ana PDF'i kopyala
                shutil.copy(ana_pdf, cikti_yolu)
            
            rapor.cikti_dosya = cikti_yolu
            
            # Sayfa sayısını güncelle
            if os.path.exists(cikti_yolu):
                rapor.toplam_sayfa = self._pdf_sayfa_sayisi(cikti_yolu)
        
        finally:
            # Temizlik
            if self.temp_dir and os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir, ignore_errors=True)
                self.temp_dir = None
        
        rapor.sure_saniye = (datetime.now() - baslangic).total_seconds()
        return rapor
    
    def _kaynak_ac(self, kaynak: str) -> List[str]:
        """Kaynağı aç ve dosya listesi döndür"""
        dosyalar = []
        
        if kaynak.lower().endswith('.zip'):
            # ZIP aç
            try:
                with zipfile.ZipFile(kaynak, 'r') as zf:
                    zf.extractall(self.temp_dir)
                
                # Tüm dosyaları bul
                for root, dirs, files in os.walk(self.temp_dir):
                    for f in files:
                        dosyalar.append(os.path.join(root, f))
            except Exception as e:
                print(f"ZIP açma hatası: {e}")
        
        elif os.path.isdir(kaynak):
            # Klasör tara
            for root, dirs, files in os.walk(kaynak):
                for f in files:
                    dosyalar.append(os.path.join(root, f))
        
        elif os.path.isfile(kaynak):
            dosyalar.append(kaynak)
        
        return dosyalar
    
    def _kapak_olustur(self, baslik: str, dosya_sayisi: int, stiller) -> List:
        """Kapak sayfası oluştur"""
        elements = []
        
        elements.append(Spacer(1, 3*cm))
        
        # Logo/başlık kutusu
        elements.append(Paragraph(
            f"<b>⚖️ {baslik}</b>",
            stiller['AnaBaslik']
        ))
        
        elements.append(Spacer(1, 1*cm))
        
        # Bilgi tablosu
        tarih = datetime.now().strftime('%d.%m.%Y %H:%M')
        bilgiler = [
            ['Oluşturma Tarihi:', tarih],
            ['Toplam Dosya:', str(dosya_sayisi)],
            ['Oluşturan:', 'İcra Dosya Analiz Sistemi'],
        ]
        
        tablo = Table(bilgiler, colWidths=[5*cm, 8*cm])
        tablo.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), self.font_adi),
            ('FONTSIZE', (0, 0), (-1, -1), 11),
            ('TEXTCOLOR', (0, 0), (0, -1), self.HEADER_COLOR),
            ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
            ('ALIGN', (1, 0), (1, -1), 'LEFT'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ]))
        
        elements.append(tablo)
        
        elements.append(Spacer(1, 2*cm))
        
        # Alt bilgi
        elements.append(Paragraph(
            "<i>Bu belge otomatik olarak oluşturulmuştur.</i>",
            stiller['KucukMetin']
        ))
        
        return elements
    
    def _icindekiler_olustur(self, bilgiler: List[Tuple], stiller) -> List:
        """İçindekiler sayfası oluştur"""
        elements = []
        
        elements.append(Paragraph(
            "<b>📑 İÇİNDEKİLER</b>",
            stiller['AltBaslik']
        ))
        
        elements.append(Spacer(1, 0.5*cm))
        
        for i, (baslik, ref) in enumerate(bilgiler, 1):
            # Başlığı kısalt
            if len(baslik) > 60:
                baslik = baslik[:57] + "..."
            
            elements.append(Paragraph(
                f"{i}. {baslik}",
                stiller['Icindekiler']
            ))
        
        return elements
    
    def _metin_sayfasi_olustur(self, metin: str, bilgi: DosyaBilgisi, stiller) -> List:
        """Metin içeriği için sayfa oluştur"""
        elements = []
        
        # Dosya başlığı
        baslik_text = f"📄 {bilgi.baslik}"
        if len(baslik_text) > 80:
            baslik_text = baslik_text[:77] + "..."
        
        elements.append(Paragraph(baslik_text, stiller['DosyaBaslik']))
        
        # Kaynak bilgisi
        kaynak_text = f"Kaynak: {bilgi.orijinal_ad} | Tür: {bilgi.dosya_turu} | Boyut: {bilgi.boyut_kb:.1f} KB"
        elements.append(Paragraph(kaynak_text, stiller['KucukMetin']))
        
        elements.append(Spacer(1, 0.3*cm))
        
        # Metin içeriği
        # Satırları paragraf olarak ekle
        satirlar = metin.split('\n')
        for satir in satirlar:
            satir = satir.strip()
            if satir:
                # Özel karakterleri escape et
                satir = satir.replace('&', '&amp;')
                satir = satir.replace('<', '&lt;')
                satir = satir.replace('>', '&gt;')
                
                try:
                    elements.append(Paragraph(satir, stiller['NormalMetin']))
                except:
                    # Hatalı karakterler varsa atla
                    continue
        
        return elements
    
    # ========================================================================
    # KOLAY KULLANIM
    # ========================================================================
    
    def zip_to_pdf(self, zip_yolu: str, cikti_yolu: str = None) -> str:
        """
        ZIP'i PDF'e dönüştür (kolay kullanım)
        Returns: Çıktı PDF yolu
        """
        rapor = self.uret(zip_yolu, cikti_yolu)
        return rapor.cikti_dosya


# ============================================================================
# TEST
# ============================================================================

if __name__ == "__main__":
    print("=" * 50)
    print("NEAT PDF ÜRETİCİ TEST")
    print("=" * 50)
    
    print(f"\n📦 Kütüphane Durumu:")
    print(f"  ReportLab: {'✅' if REPORTLAB_OK else '❌'}")
    print(f"  PyPDF2: {'✅' if PYPDF2_OK else '❌'}")
    print(f"  Pillow: {'✅' if PIL_OK else '❌'}")
    print(f"  pdfplumber: {'✅' if PDFPLUMBER_OK else '❌'}")
    
    if REPORTLAB_OK:
        print("\n✅ Neat PDF Üretici kullanılabilir!")
        print("\nKullanım:")
        print("  uretici = NeatPDFUretici()")
        print("  rapor = uretici.uret('dosya.zip', 'cikti.pdf')")
    else:
        print("\n❌ ReportLab gerekli: pip install reportlab")
