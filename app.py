#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
İCRA DOSYA ANALİZ SİSTEMİ - Web Arayüzü v11.0 (Production)
==========================================================
1. 89/1-2-3 Haciz İhbar Analizi (Banka + 3. Şahıs)
2. İcra Dosya Analizi (UYAP ZIP)

Author: Arda & Claude
"""

import streamlit as st
import pandas as pd
from datetime import datetime
import io
import os
import sys
import tempfile
import logging
import shutil

# Logging Setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# --- MODULE IMPORTS WITH ERROR HANDLING ---
try:
    from haciz_ihbar_analyzer import (
        HacizIhbarAnalyzer, CevapDurumu, MuhatapTuru
    )
    BANKA_ANALYZER_AVAILABLE = True
except ImportError as e:
    BANKA_ANALYZER_AVAILABLE = False
    logger.error(f"Haciz İhbar modülü yüklenemedi: {e}")

try:
    from uyap_dosya_analyzer import UYAPDosyaAnalyzer, IslemDurumu
    UYAP_ANALYZER_AVAILABLE = True
except ImportError as e:
    UYAP_ANALYZER_AVAILABLE = False
    logger.error(f"UYAP Dosya modülü yüklenemedi: {e}")

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="İcra Analiz v11",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- CSS STYLING ---
def load_css():
    st.markdown("""
    <style>
        .main-header {
            font-size: 2.0rem;
            font-weight: 700;
            color: #1E3A5F;
            text-align: center;
            padding: 1rem;
            border-bottom: 2px solid #eee;
            margin-bottom: 2rem;
        }
        .metric-card {
            background-color: #f8f9fa;
            border: 1px solid #e9ecef;
            border-radius: 0.5rem;
            padding: 1rem;
            text-align: center;
        }
        .kritik-box {
            background-color: #ffebee;
            border-left: 5px solid #d32f2f;
            padding: 1rem;
            margin: 0.5rem 0;
            border-radius: 4px;
        }
        .uyari-box {
            background-color: #fff3e0;
            border-left: 5px solid #f57c00;
            padding: 1rem;
            margin: 0.5rem 0;
            border-radius: 4px;
        }
        .basari-box {
            background-color: #e8f5e9;
            border-left: 5px solid #2e7d32;
            padding: 1rem;
            margin: 0.5rem 0;
            border-radius: 4px;
        }
        .bloke-box {
            background-color: #e8f5e9;
            border: 2px solid #2e7d32;
            padding: 1.5rem;
            margin: 1rem 0;
            border-radius: 8px;
            text-align: center;
        }
        /* Tablo iyileştirmeleri */
        .stDataFrame { border: 1px solid #ddd; }
    </style>
    """, unsafe_allow_html=True)

# --- STATE MANAGEMENT ---
def init_session_state():
    """Initialize session state variables if they don't exist."""
    if 'ihbar_sonuc' not in st.session_state:
        st.session_state.ihbar_sonuc = None
    if 'uyap_sonuc' not in st.session_state:
        st.session_state.uyap_sonuc = None

def reset_state():
    """Clear analysis results to start over."""
    st.session_state.ihbar_sonuc = None
    st.session_state.uyap_sonuc = None
    st.rerun()

# ============================================================================
# MODULE 1: 89/1-2-3 HACİZ İHBAR ANALİZİ
# ============================================================================
def banka_cevaplari_sayfasi():
    st.markdown('<div class="main-header">🏦 89/1-2-3 Haciz İhbar Analizi</div>', unsafe_allow_html=True)
    
    if not BANKA_ANALYZER_AVAILABLE:
        st.error("⚠️ Haciz İhbar Analyzer modülü bulunamadı. Lütfen 'haciz_ihbar_analyzer.py' dosyasını kontrol edin.")
        return

    # Sidebar Controls
    with st.sidebar:
        st.header("⚙️ Ayarlar")
        use_ocr = st.checkbox("Gelişmiş OCR (Deneysel)", value=False, help="Taranmış resim PDF'leri için (Yavaş çalışabilir)")
        
        st.header("📁 Dosya Yükle")
        uploaded_files = st.file_uploader(
            "ZIP veya PDF Seçin",
            type=['zip', 'pdf'],
            accept_multiple_files=True,
            key="ihbar_uploader"
        )
        
        if uploaded_files:
            if st.button("🔍 Analiz Et", type="primary"):
                with st.spinner("Dosyalar işleniyor... Bu işlem dosya boyutuna göre zaman alabilir."):
                    temp_dir = tempfile.mkdtemp()
                    temp_paths = []
                    try:
                        # 1. Save uploaded files to temp
                        for f in uploaded_files:
                            temp_path = os.path.join(temp_dir, f.name)
                            with open(temp_path, 'wb') as out:
                                out.write(f.getvalue())
                            temp_paths.append(temp_path)
                        
                        # 2. Analyze
                        analyzer = HacizIhbarAnalyzer() 
                        # Note: In future, pass use_ocr to analyzer here
                        sonuc = analyzer.batch_analiz(temp_paths)
                        st.session_state.ihbar_sonuc = sonuc
                        
                    except Exception as e:
                        logger.error(f"Analiz hatası: {e}")
                        st.error(f"Bir hata oluştu: {str(e)}")
                    finally:
                        # 3. Cleanup temp files strictly
                        shutil.rmtree(temp_dir, ignore_errors=True)
                st.rerun()
        
        if st.session_state.ihbar_sonuc:
            if st.button("🔄 Yeni Analiz", on_click=reset_state):
                pass

    # Main Content
    if st.session_state.ihbar_sonuc:
        sonuc = st.session_state.ihbar_sonuc
        
        # --- Top Metrics ---
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Toplam Muhatap", sonuc.toplam_muhatap)
        col2.metric("Banka Sayısı", sonuc.banka_sayisi)
        col3.metric("3. Şahıs Sayısı", sonuc.tuzel_kisi_sayisi + sonuc.gercek_kisi_sayisi)
        col4.metric("Toplam Bloke", f"{sonuc.toplam_bloke:,.2f} ₺", delta_color="normal")
        
        st.divider()

        # --- Tabs ---
        tabs = st.tabs(["💰 Bloke & Alacak", "📤 Aksiyonlar", "🏦 Bankalar", "🏢 3. Şahıslar", "📥 Raporlama"])

        with tabs[0]: # Bloke & Alacak
            toplam_tahsilat = sonuc.toplam_bloke + sonuc.toplam_alacak
            if toplam_tahsilat > 0:
                st.markdown(f"""
                <div class="bloke-box">
                    <h2 style="color: #2e7d32; margin:0;">💰 TOPLAM POTANSİYEL: {toplam_tahsilat:,.2f} TL</h2>
                    <p style="margin-top:5px;">(Banka Bloke: {sonuc.toplam_bloke:,.2f} TL + Cari Alacak: {sonuc.toplam_alacak:,.2f} TL)</p>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.info("Henüz herhangi bir bloke veya alacak tespiti yapılamadı.")

            # Detail Tables
            col_a, col_b = st.columns(2)
            with col_a:
                st.subheader("Bloke Koyan Bankalar")
                bloke_list = [c for c in sonuc.cevaplar if c.cevap_durumu == CevapDurumu.BLOKE_VAR]
                if bloke_list:
                    for item in bloke_list:
                        st.success(f"**{item.muhatap_adi}:** {item.bloke_tutari:,.2f} TL")
                else:
                    st.caption("Bloke kaydı yok.")

            with col_b:
                st.subheader("Alacak Bildirenler")
                alacak_list = [c for c in sonuc.cevaplar if c.cevap_durumu == CevapDurumu.ALACAK_VAR]
                if alacak_list:
                    for item in alacak_list:
                        st.success(f"**{item.muhatap_adi}:** {item.alacak_tutari:,.2f} TL")
                else:
                    st.caption("Alacak kaydı yok.")

        with tabs[1]: # Aksiyonlar
            if sonuc.eksik_ihbarlar:
                st.error(f"⚠️ {len(sonuc.eksik_ihbarlar)} adet takip edilmesi gereken işlem var!")
                df_eksik = pd.DataFrame(sonuc.eksik_ihbarlar)
                st.dataframe(
                    df_eksik.rename(columns={"muhatap": "Muhatap", "gonderilecek": "Sıradaki İşlem", "neden": "Gerekçe"}),
                    use_container_width=True,
                    hide_index=True
                )
            else:
                st.markdown('<div class="basari-box">✅ Tüm ihbar zinciri tamamlanmış. Ek işlem gerekmiyor.</div>', unsafe_allow_html=True)

        with tabs[2]: # Bankalar Detay
            bankalar = [c for c in sonuc.cevaplar if c.muhatap_turu == MuhatapTuru.BANKA]
            if bankalar:
                for b in bankalar:
                    color = "green" if b.cevap_durumu == CevapDurumu.BLOKE_VAR else "orange" if "YOK" in b.cevap_durumu.name else "blue"
                    with st.expander(f":{color}[{b.muhatap_adi}] - {b.ihbar_turu.value}"):
                        st.write(f"**Durum:** {b.cevap_durumu.value}")
                        st.write(f"**Tutar:** {b.bloke_tutari:,.2f} TL")
                        st.caption(f"Açıklama: {b.aciklama[:200]}..." if b.aciklama else "")
            else:
                st.info("Banka cevabı bulunamadı.")

        with tabs[3]: # 3. Şahıslar Detay
            sahislar = [c for c in sonuc.cevaplar if c.muhatap_turu != MuhatapTuru.BANKA]
            if sahislar:
                for s in sahislar:
                    icon = "🏢" if s.muhatap_turu == MuhatapTuru.TUZEL_KISI else "👤"
                    with st.expander(f"{icon} {s.muhatap_adi}"):
                        st.write(f"**Cevap:** {s.cevap_durumu.value}")
                        if s.alacak_tutari > 0:
                            st.success(f"**Alacak:** {s.alacak_tutari:,.2f} TL")
            else:
                st.info("3. Şahıs cevabı bulunamadı.")

        with tabs[4]: # Raporlama
            col_d1, col_d2 = st.columns(2)
            
            # Excel Generation
            excel_buffer = io.BytesIO()
            with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                # Sheet 1: Tüm Cevaplar
                data = [{
                    'Muhatap': c.muhatap_adi,
                    'Tür': c.muhatap_turu.value,
                    'İhbar Aşaması': c.ihbar_turu.value,
                    'Durum': c.cevap_durumu.value,
                    'Bloke Tutarı': c.bloke_tutari,
                    'Alacak Tutarı': c.alacak_tutari,
                    'Dosya': os.path.basename(c.kaynak_dosya) if c.kaynak_dosya else ""
                } for c in sonuc.cevaplar]
                pd.DataFrame(data).to_excel(writer, sheet_name='Analiz Sonuclari', index=False)
                
                # Sheet 2: Aksiyonlar
                if sonuc.eksik_ihbarlar:
                    pd.DataFrame(sonuc.eksik_ihbarlar).to_excel(writer, sheet_name='Aksiyon Listesi', index=False)
            
            with col_d1:
                st.download_button(
                    label="📥 Excel Raporunu İndir",
                    data=excel_buffer.getvalue(),
                    file_name=f"Haciz_Analiz_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
            
            with col_d2:
                st.download_button(
                    label="📄 Özet Metin Raporu (TXT)",
                    data=sonuc.ozet_rapor,
                    file_name=f"Analiz_Ozet_{datetime.now().strftime('%Y%m%d_%H%M')}.txt",
                    mime="text/plain",
                    use_container_width=True
                )

    else:
        # Empty State
        st.markdown("""
        <div style="text-align:center; margin-top:50px; color:#666;">
            <h3>👈 Sol menüden dosyalarınızı yükleyerek başlayın</h3>
            <p>Sistem 89/1, 89/2 ve 89/3 cevaplarını otomatik sınıflandırır.</p>
        </div>
        """, unsafe_allow_html=True)

# ============================================================================
# MODULE 2: UYAP DOSYA ANALİZİ
# ============================================================================
def icra_dosya_sayfasi():
    st.markdown('<div class="main-header">📁 UYAP Dosya Analizi (Tüm Dosya)</div>', unsafe_allow_html=True)
    
    if not UYAP_ANALYZER_AVAILABLE:
        st.error("⚠️ UYAP Dosya Analyzer modülü bulunamadı.")
        return

    with st.sidebar:
        st.header("📁 UYAP ZIP Yükle")
        uploaded_file = st.file_uploader(
            "UYAP 'Tüm Dosya' ZIP Seçin",
            type=['zip'],
            key="uyap_uploader"
        )
        
        if uploaded_file:
            if st.button("🔍 Dosyayı Analiz Et", type="primary"):
                with st.spinner("ZIP içeriği taranıyor ve sınıflandırılıyor..."):
                    # Create a named temp file that persists until we close it
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp_file:
                        tmp_file.write(uploaded_file.getvalue())
                        tmp_path = tmp_file.name
                    
                    try:
                        analyzer = UYAPDosyaAnalyzer()
                        sonuc = analyzer.analiz_et(tmp_path)
                        st.session_state.uyap_sonuc = sonuc
                    except Exception as e:
                        logger.error(f"UYAP analiz hatası: {e}")
                        st.error(f"Dosya okunamadı: {str(e)}")
                    finally:
                        # Clean up the specific temp file
                        if os.path.exists(tmp_path):
                            os.remove(tmp_path)
                st.rerun()

        if st.session_state.uyap_sonuc:
            st.button("🔄 Yeni Analiz", on_click=reset_state)

    if st.session_state.uyap_sonuc:
        sonuc = st.session_state.uyap_sonuc
        
        # --- Metrics ---
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Toplam Evrak", sonuc.toplam_evrak)
        m2.metric("Tebligat", len(sonuc.tebligatlar))
        m3.metric("Haciz İşlemi", len(sonuc.hacizler))
        m4.metric("Kritik Süreç", len([a for a in sonuc.aksiyonlar if a.oncelik == IslemDurumu.KRITIK]))
        m5.metric("Tespit Edilen Bloke", f"{sonuc.toplam_bloke:,.0f} ₺", help="89/1 cevaplarından tespit edilenler")

        st.divider()

        # --- Tabs ---
        tabs = st.tabs(["🚀 Aksiyon Planı", "📂 Evrak Envanteri", "📅 Kritik Tarihler", "📥 İndir"])

        with tabs[0]: # Aksiyon Planı
            st.subheader("Yapılması Gerekenler")
            if sonuc.aksiyonlar:
                for ax in sonuc.aksiyonlar:
                    style = "kritik-box" if ax.oncelik == IslemDurumu.KRITIK else "uyari-box" if ax.oncelik == IslemDurumu.UYARI else "bilgi-box"
                    icon = "🔥" if ax.oncelik == IslemDurumu.KRITIK else "⚠️" if ax.oncelik == IslemDurumu.UYARI else "ℹ️"
                    
                    st.markdown(f"""
                    <div class="{style}">
                        <strong>{icon} {ax.baslik}</strong><br>
                        {ax.aciklama}<br>
                        <small>📅 Son Tarih: {ax.son_tarih.strftime('%d.%m.%Y') if ax.son_tarih else 'Belirtilmemiş'}</small>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.success("Bu dosyada acil aksiyon gerektiren bir durum tespit edilmedi.")

        with tabs[1]: # Evraklar
            st.subheader("Sınıflandırılmış Evrak Listesi")
            if sonuc.evraklar:
                df_evrak = pd.DataFrame([{
                    'Tarih': e.tarih.strftime('%d.%m.%Y') if e.tarih else "-",
                    'Evrak Türü': e.evrak_turu.value,
                    'Dosya Adı': e.dosya_adi,
                } for e in sonuc.evraklar])
                st.dataframe(df_evrak, use_container_width=True, height=500)
        
        with tabs[2]: # Kritik Tarihler (Hacizler)
            st.subheader("Haciz Düşme Süreleri (İİK 106/110)")
            if sonuc.hacizler:
                haciz_data = []
                for h in sonuc.hacizler:
                    haciz_data.append({
                        'Varlık Tipi': h.tur.value if hasattr(h.tur, 'value') else str(h.tur),
                        'Haciz Tarihi': h.tarih.strftime('%d.%m.%Y') if h.tarih else "-",
                        'Kalan Gün': h.sure_106_110 if h.sure_106_110 is not None else "-",
                        'Durum': "KRİTİK" if (h.sure_106_110 and h.sure_106_110 < 30) else "Normal"
                    })
                st.dataframe(pd.DataFrame(haciz_data), use_container_width=True)
            else:
                st.info("Aktif haciz kaydı bulunamadı.")

        with tabs[3]: # İndir
            col_d1, col_d2 = st.columns(2)
            
            with col_d1:
                # Excel Generation logic handled in UI for safety
                excel_buffer = io.BytesIO()
                with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                    # Summary
                    pd.DataFrame([{'Toplam Evrak': sonuc.toplam_evrak, 'Analiz Tarihi': datetime.now()}]).to_excel(writer, sheet_name='Ozet', index=False)
                    # Inventory
                    if sonuc.evraklar:
                        pd.DataFrame([{'Tarih': e.tarih, 'Tur': e.evrak_turu.value, 'Dosya': e.dosya_adi} for e in sonuc.evraklar]).to_excel(writer, sheet_name='Evraklar', index=False)
                    # Actions
                    if sonuc.aksiyonlar:
                        pd.DataFrame([{'Baslik': a.baslik, 'Aciklama': a.aciklama, 'Oncelik': a.oncelik.value} for a in sonuc.aksiyonlar]).to_excel(writer, sheet_name='Yapilacaklar', index=False)
                
                st.download_button(
                    label="📊 Excel Raporu İndir",
                    data=excel_buffer.getvalue(),
                    file_name=f"Dosya_Analiz_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )

            with col_d2:
                st.download_button(
                    label="📄 Detaylı Rapor (TXT)",
                    data=sonuc.ozet_rapor,
                    file_name=f"Rapor_{datetime.now().strftime('%Y%m%d_%H%M')}.txt",
                    mime="text/plain",
                    use_container_width=True
                )

    else:
        st.markdown("""
        <div style="text-align:center; margin-top:50px; color:#666;">
            <h3>👈 UYAP'tan indirdiğiniz ZIP dosyasını yükleyin</h3>
            <p>Sistem tüm evrakları okur, tarih sırasına dizer ve yapılacak işleri çıkarır.</p>
        </div>
        """, unsafe_allow_html=True)


# ============================================================================
# MAIN APP ENTRY
# ============================================================================
def main():
    load_css()
    init_session_state()
    
    st.sidebar.title("⚖️ İcra Analiz v11")
    st.sidebar.caption("Domain Expert: Arda | Tech: Claude")
    st.sidebar.markdown("---")
    
    modul = st.sidebar.radio(
        "Modül Seçimi",
        ["🏦 89/1-2-3 Haciz İhbar", "📁 İcra Dosya Analizi"],
        index=0
    )
    st.sidebar.markdown("---")
    
    if modul == "🏦 89/1-2-3 Haciz İhbar":
        banka_cevaplari_sayfasi()
    else:
        icra_dosya_sayfasi()

if __name__ == "__main__":
    main()
