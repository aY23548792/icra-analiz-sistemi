#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PROFESYONEL RAPOR ÜRETİCİ v12.5
================================
Banka haciz ihbar analiz sonuçlarını profesyonel PDF raporuna dönüştürür.

Özellikler:
- Kapak sayfası
- Yönetici özeti
- Detaylı analiz tabloları
- Grafik/chart desteği
- Türkçe karakter desteği

Author: Arda & Claude
"""

import os
from datetime import datetime
from typing import List, Optional
from dataclasses import dataclass

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, PageBreak, 
        Table, TableStyle, Image
    )
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    from reportlab.lib import colors
    from reportlab.lib.units import cm, mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    REPORTLAB_OK = True
except ImportError:
    REPORTLAB_OK = False


class ProfesyonelRaporUretici:
    """
    Banka Analiz Sonuçlarını Profesyonel PDF Raporuna Dönüştürür
    
    Kullanım:
        from rapor_uretici import ProfesyonelRaporUretici
        from haciz_ihbar_analyzer import HacizIhbarAnalyzer
        
        analyzer = HacizIhbarAnalyzer()
        sonuc = analyzer.batch_analiz(dosyalar)
        
        rapor = ProfesyonelRaporUretici()
        rapor.uret_banka_raporu(sonuc, "rapor.pdf", "Ziraat Bank - Q4 2024")
    """
    
    # Türkçe font arama yolları
    FONT_PATHS = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "C:\\Windows\\Fonts\\arial.ttf",
        "C:\\Windows\\Fonts\\arialbd.ttf",
    ]
    
    def __init__(self):
        self.font_normal = "Helvetica"
        self.font_bold = "Helvetica-Bold"
        self._yukle_font()
        self.styles = self._olustur_stiller()
    
    def _yukle_font(self):
        """Türkçe destekli font yükle"""
        if not REPORTLAB_OK:
            return
        
        for path in self.FONT_PATHS:
            if os.path.exists(path):
                try:
                    if "Bold" in path or "bd" in path.lower():
                        pdfmetrics.registerFont(TTFont('TRBold', path))
                        self.font_bold = 'TRBold'
                    else:
                        pdfmetrics.registerFont(TTFont('TRNormal', path))
                        self.font_normal = 'TRNormal'
                except:
                    pass
    
    def _olustur_stiller(self) -> dict:
        """Rapor stilleri"""
        if not REPORTLAB_OK:
            return {}
        
        styles = getSampleStyleSheet()
        
        return {
            'title': ParagraphStyle(
                'Title',
                parent=styles['Heading1'],
                fontName=self.font_bold,
                fontSize=24,
                textColor=colors.HexColor('#1a365d'),
                alignment=TA_CENTER,
                spaceAfter=30
            ),
            'subtitle': ParagraphStyle(
                'Subtitle',
                parent=styles['Heading2'],
                fontName=self.font_normal,
                fontSize=14,
                textColor=colors.HexColor('#4a5568'),
                alignment=TA_CENTER,
                spaceAfter=20
            ),
            'heading': ParagraphStyle(
                'Heading',
                parent=styles['Heading2'],
                fontName=self.font_bold,
                fontSize=14,
                textColor=colors.HexColor('#2d3748'),
                spaceBefore=20,
                spaceAfter=10
            ),
            'body': ParagraphStyle(
                'Body',
                parent=styles['Normal'],
                fontName=self.font_normal,
                fontSize=10,
                leading=14,
                spaceAfter=8
            ),
            'highlight': ParagraphStyle(
                'Highlight',
                parent=styles['Normal'],
                fontName=self.font_bold,
                fontSize=28,
                textColor=colors.HexColor('#38a169'),
                alignment=TA_CENTER,
                spaceBefore=10,
                spaceAfter=10
            ),
            'warning': ParagraphStyle(
                'Warning',
                parent=styles['Normal'],
                fontName=self.font_bold,
                fontSize=12,
                textColor=colors.HexColor('#c53030'),
                alignment=TA_LEFT,
                spaceBefore=5,
                spaceAfter=5
            ),
            'footer': ParagraphStyle(
                'Footer',
                parent=styles['Normal'],
                fontName=self.font_normal,
                fontSize=8,
                textColor=colors.grey,
                alignment=TA_CENTER
            )
        }
    
    def uret_banka_raporu(self, analiz_sonucu, cikti_yol: str, 
                          baslik: str = "Haciz İhbar Analiz Raporu",
                          firma_adi: str = "") -> bool:
        """
        Banka haciz ihbar analiz sonuçlarını profesyonel PDF'e dönüştür
        
        Args:
            analiz_sonucu: BatchAnalizSonucu objesi
            cikti_yol: Çıktı PDF dosya yolu
            baslik: Rapor başlığı
            firma_adi: Opsiyonel firma adı
        
        Returns:
            bool: Başarılı ise True
        """
        if not REPORTLAB_OK:
            print("❌ ReportLab yüklü değil!")
            return False
        
        try:
            doc = SimpleDocTemplate(
                cikti_yol,
                pagesize=A4,
                leftMargin=2*cm,
                rightMargin=2*cm,
                topMargin=2*cm,
                bottomMargin=2*cm
            )
            
            story = []
            
            # === KAPAK SAYFASI ===
            story.extend(self._olustur_kapak(baslik, firma_adi, analiz_sonucu))
            
            # === YÖNETİCİ ÖZETİ ===
            story.extend(self._olustur_yonetici_ozeti(analiz_sonucu))
            
            # === DETAYLI TABLO ===
            story.extend(self._olustur_detay_tablosu(analiz_sonucu))
            
            # === AKSİYON ÖNERİLERİ ===
            story.extend(self._olustur_aksiyonlar(analiz_sonucu))
            
            # === FOOTER ===
            story.append(Spacer(1, 50))
            story.append(Paragraph(
                f"Bu rapor İcra Analiz Pro v12.5 ile {datetime.now().strftime('%d.%m.%Y %H:%M')} tarihinde oluşturulmuştur.",
                self.styles['footer']
            ))
            
            doc.build(story)
            return True
            
        except Exception as e:
            print(f"❌ Rapor oluşturma hatası: {e}")
            return False
    
    def _olustur_kapak(self, baslik: str, firma_adi: str, sonuc) -> list:
        """Kapak sayfası"""
        story = []
        
        story.append(Spacer(1, 3*cm))
        
        # Logo placeholder
        story.append(Paragraph("⚖️", ParagraphStyle(
            'Logo', fontSize=48, alignment=TA_CENTER
        )))
        
        story.append(Spacer(1, 1*cm))
        story.append(Paragraph(baslik, self.styles['title']))
        
        if firma_adi:
            story.append(Paragraph(firma_adi, self.styles['subtitle']))
        
        story.append(Spacer(1, 2*cm))
        
        # Ana metrik - büyük bloke tutarı
        story.append(Paragraph("TOPLAM TESPİT EDİLEN BLOKE", self.styles['subtitle']))
        story.append(Paragraph(
            f"₺ {sonuc.toplam_bloke:,.2f}",
            self.styles['highlight']
        ))
        
        story.append(Spacer(1, 1*cm))
        
        # Özet kutusu
        ozet_data = [
            ["Toplam Muhatap", str(sonuc.toplam_muhatap)],
            ["Banka Sayısı", str(sonuc.banka_sayisi)],
            ["Tüzel Kişi", str(sonuc.tuzel_kisi_sayisi)],
            ["Gerçek Kişi", str(sonuc.gercek_kisi_sayisi)],
        ]
        
        ozet_table = Table(ozet_data, colWidths=[8*cm, 4*cm])
        ozet_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), self.font_normal),
            ('FONTSIZE', (0, 0), (-1, -1), 11),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#2d3748')),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
            ('TOPPADDING', (0, 0), (-1, -1), 10),
        ]))
        story.append(ozet_table)
        
        story.append(Spacer(1, 2*cm))
        story.append(Paragraph(
            f"Rapor Tarihi: {datetime.now().strftime('%d.%m.%Y')}",
            self.styles['footer']
        ))
        
        story.append(PageBreak())
        return story
    
    def _olustur_yonetici_ozeti(self, sonuc) -> list:
        """Yönetici özeti sayfası"""
        story = []
        
        story.append(Paragraph("📊 YÖNETİCİ ÖZETİ", self.styles['heading']))
        story.append(Spacer(1, 0.5*cm))
        
        # Durum dağılımı
        bloke_var = len([c for c in sonuc.cevaplar if c.cevap_durumu.value == "💰 BLOKE VAR"])
        hesap_yok = len([c for c in sonuc.cevaplar if c.cevap_durumu.value == "❌ HESAP YOK"])
        bakiye_yok = len([c for c in sonuc.cevaplar if c.cevap_durumu.value == "⚠️ BAKİYE YOK"])
        belirsiz = sonuc.toplam_muhatap - bloke_var - hesap_yok - bakiye_yok
        
        story.append(Paragraph(
            f"Analiz edilen <b>{sonuc.toplam_muhatap}</b> muhatap cevabından:",
            self.styles['body']
        ))
        
        ozet_text = f"""
        • <b>{bloke_var}</b> muhataptan <font color="green"><b>BLOKE</b></font> tespit edildi
        • <b>{hesap_yok}</b> muhataptan <font color="red">HESAP YOK</font> cevabı alındı
        • <b>{bakiye_yok}</b> muhataptan <font color="orange">BAKİYE YOK</font> cevabı alındı
        • <b>{belirsiz}</b> muhatap manuel inceleme gerektiriyor
        """
        story.append(Paragraph(ozet_text, self.styles['body']))
        
        story.append(Spacer(1, 1*cm))
        
        # Bloke bulunan bankalar
        if bloke_var > 0:
            story.append(Paragraph("💰 BLOKE TESPİT EDİLEN MUHATAPLAR", self.styles['heading']))
            
            bloke_data = [["Muhatap", "Tutar (TL)", "Sonraki Adım"]]
            for c in sonuc.cevaplar:
                if c.cevap_durumu.value == "💰 BLOKE VAR" and c.bloke_tutari > 0:
                    bloke_data.append([
                        c.muhatap_adi,
                        f"{c.bloke_tutari:,.2f}",
                        c.sonraki_adim
                    ])
            
            if len(bloke_data) > 1:
                bloke_table = Table(bloke_data, colWidths=[6*cm, 4*cm, 6*cm])
                bloke_table.setStyle(TableStyle([
                    ('FONTNAME', (0, 0), (-1, 0), self.font_bold),
                    ('FONTNAME', (0, 1), (-1, -1), self.font_normal),
                    ('FONTSIZE', (0, 0), (-1, -1), 9),
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#38a169')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                    ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f7fafc')]),
                    ('TOPPADDING', (0, 0), (-1, -1), 8),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                ]))
                story.append(bloke_table)
        
        story.append(PageBreak())
        return story
    
    def _olustur_detay_tablosu(self, sonuc) -> list:
        """Detaylı analiz tablosu"""
        story = []
        
        story.append(Paragraph("📋 TÜM MUHATAP ANALİZİ", self.styles['heading']))
        story.append(Spacer(1, 0.5*cm))
        
        # Tablo verileri
        data = [["#", "Muhatap", "Tür", "Durum", "Tutar (TL)", "Aksiyon"]]
        
        for i, c in enumerate(sonuc.cevaplar, 1):
            # Durum rengini belirle
            durum_text = c.cevap_durumu.value.replace("💰 ", "").replace("❌ ", "").replace("⚠️ ", "").replace("❓ ", "")
            
            data.append([
                str(i),
                c.muhatap_adi[:25],  # Kısalt
                c.muhatap_turu.value,
                durum_text,
                f"{c.bloke_tutari:,.2f}" if c.bloke_tutari > 0 else "-",
                c.sonraki_adim[:20]
            ])
        
        # Tablo oluştur
        table = Table(data, colWidths=[1*cm, 5*cm, 2.5*cm, 3*cm, 2.5*cm, 3*cm])
        table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, 0), self.font_bold),
            ('FONTNAME', (0, 1), (-1, -1), self.font_normal),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2d3748')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (0, -1), 'CENTER'),
            ('ALIGN', (4, 0), (4, -1), 'RIGHT'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f7fafc')]),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        story.append(table)
        
        story.append(PageBreak())
        return story
    
    def _olustur_aksiyonlar(self, sonuc) -> list:
        """Aksiyon önerileri"""
        story = []
        
        story.append(Paragraph("⚡ ÖNERİLEN AKSİYONLAR", self.styles['heading']))
        story.append(Spacer(1, 0.5*cm))
        
        # Bloke varsa
        bloke_var = [c for c in sonuc.cevaplar if c.cevap_durumu.value == "💰 BLOKE VAR"]
        if bloke_var:
            story.append(Paragraph(
                f"<font color='green'><b>✅ {len(bloke_var)} muhataptan bloke tespit edildi</b></font>",
                self.styles['body']
            ))
            story.append(Paragraph(
                "→ Mahsup/Tahsil talepleri derhal gönderilmelidir.",
                self.styles['body']
            ))
            story.append(Spacer(1, 0.3*cm))
        
        # Bakiye yok
        bakiye_yok = [c for c in sonuc.cevaplar if c.cevap_durumu.value == "⚠️ BAKİYE YOK"]
        if bakiye_yok:
            story.append(Paragraph(
                f"<font color='orange'><b>⚠️ {len(bakiye_yok)} muhataptan bakiye yok cevabı</b></font>",
                self.styles['body']
            ))
            story.append(Paragraph(
                "→ 89/2 (2. haciz ihbarnamesi) gönderilmeli, hesap hareketleri takip edilmeli.",
                self.styles['body']
            ))
            story.append(Spacer(1, 0.3*cm))
        
        # Belirsiz
        belirsiz = [c for c in sonuc.cevaplar if c.cevap_durumu.value == "❓ İNCELENMELİ"]
        if belirsiz:
            story.append(Paragraph(
                f"<font color='blue'><b>❓ {len(belirsiz)} muhatap manuel inceleme gerektiriyor</b></font>",
                self.styles['body']
            ))
            story.append(Paragraph(
                "→ Bu cevaplar otomatik sınıflandırılamadı, avukat incelemesi önerilir.",
                self.styles['body']
            ))
        
        return story


# === TEST ===
if __name__ == "__main__":
    print("🧪 ProfesyonelRaporUretici Test")
    print("=" * 50)
    
    if not REPORTLAB_OK:
        print("❌ ReportLab yüklü değil!")
    else:
        print("✅ ReportLab yüklü")
        
        uretici = ProfesyonelRaporUretici()
        print(f"✅ Font: {uretici.font_normal}")
    
    print("\n✅ Testler tamamlandı")
