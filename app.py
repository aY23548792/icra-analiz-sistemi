#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
İCRA ANALİZ PRO v12.0
=====================
Profesyonel icra dosya analiz arayüzü.

Modüller:
1. 🏦 Banka Haciz İhbar Analizi (89/1-2-3)
2. 📄 Neat PDF Üretici (UDF→PDF)
3. 📁 UYAP Dosya Analizi

Author: Arda & Claude
"""

import streamlit as st
import tempfile
import os
import shutil
import io
from datetime import datetime

# === MODULE IMPORTS ===
try:
    from haciz_ihbar_analyzer import HacizIhbarAnalyzer, CevapDurumu, HacizIhbarAnalizSonucu
    BANKA_OK = True
except ImportError as e:
    BANKA_OK = False
    st.error(f"Haciz İhbar modülü yüklenemedi: {e}")

try:
    from neat_pdf_uretici import NeatPDFUretici, REPORTLAB_OK
    PDF_OK = REPORTLAB_OK
except ImportError:
    PDF_OK = False

try:
    from uyap_dosya_analyzer import UYAPDosyaAnalyzer
    UYAP_OK = True
except ImportError:
    UYAP_OK = False

try:
    import pandas as pd
    PANDAS_OK = True
except ImportError:
    PANDAS_OK = False

# === PAGE CONFIG ===
st.set_page_config(
    page_title="İcra Analiz Pro v12",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# === CUSTOM CSS ===
st.markdown("""
<style>
    .main-header {
        font-size: 2rem;
        font-weight: 700;
        color: #1E3A5F;
        text-align: center;
        padding: 1rem;
        border-bottom: 3px solid #2C5282;
        margin-bottom: 2rem;
    }
    .bloke-box {
        background: linear-gradient(135deg, #48BB78 0%, #38A169 100%);
        color: white;
        padding: 1.5rem;
        border-radius: 10px;
        text-align: center;
        margin: 1rem 0;
    }
    .bloke-box h2 { margin: 0; font-size: 1.8rem; }
    .kritik-box {
        background-color: #FED7D7;
        border-left: 5px solid #E53E3E;
        padding: 1rem;
        margin: 0.5rem 0;
        border-radius: 4px;
    }
    .uyari-box {
        background-color: #FEEBC8;
        border-left: 5px solid #DD6B20;
        padding: 1rem;
        margin: 0.5rem 0;
        border-radius: 4px;
    }
    .basari-box {
        background-color: #C6F6D5;
        border-left: 5px solid #38A169;
        padding: 1rem;
        margin: 0.5rem 0;
        border-radius: 4px;
    }
    .stMetric {
        background-color: #F7FAFC;
        padding: 1rem;
        border-radius: 8px;
        border: 1px solid #E2E8F0;
    }
</style>
""", unsafe_allow_html=True)

# === SESSION STATE ===
if 'banka_sonuc' not in st.session_state:
    st.session_state.banka_sonuc = None
if 'pdf_rapor' not in st.session_state:
    st.session_state.pdf_rapor = None
if 'uyap_sonuc' not in st.session_state:
    st.session_state.uyap_sonuc = None

def reset_state():
    st.session_state.banka_sonuc = None
    st.session_state.pdf_rapor = None
    st.session_state.uyap_sonuc = None

# === SIDEBAR ===
with st.sidebar:
    st.title("⚖️ İcra Analiz Pro")
    st.caption("v12.0 | Arda & Claude")
    st.divider()
    
    modul = st.radio(
        "📂 Modül Seçin",
        ["🏦 Banka Analizi", "📄 Neat PDF", "📁 Dosya Analizi"],
        index=0
    )
    
    st.divider()
    
    # Durum göstergeleri
    st.caption("📊 Modül Durumu")
    st.write(f"{'✅' if BANKA_OK else '❌'} Haciz İhbar")
    st.write(f"{'✅' if PDF_OK else '❌'} PDF Üretici")
    st.write(f"{'✅' if UYAP_OK else '❌'} UYAP Analiz")
    st.write(f"{'✅' if PANDAS_OK else '❌'} Excel Export")

# ============================================================================
# MODÜL 1: BANKA HACİZ İHBAR ANALİZİ
# ============================================================================
if modul == "🏦 Banka Analizi":
    st.markdown('<div class="main-header">🏦 89/1-2-3 Haciz İhbar Analizi</div>', unsafe_allow_html=True)
    
    if not BANKA_OK:
        st.error("Haciz İhbar Analyzer modülü yüklenemedi!")
        st.stop()
    
    # Dosya yükleme
    uploaded_files = st.file_uploader(
        "Banka cevap dosyalarını yükleyin (ZIP, PDF, UDF)",
        type=['zip', 'pdf', 'udf'],
        accept_multiple_files=True,
        key="banka_uploader"
    )
    
    col1, col2 = st.columns([3, 1])
    with col1:
        if uploaded_files:
            st.info(f"📁 {len(uploaded_files)} dosya seçildi")
    with col2:
        if st.session_state.banka_sonuc:
            if st.button("🔄 Temizle", use_container_width=True):
                reset_state()
                st.rerun()
    
    # Analiz butonu
    if uploaded_files and st.button("🔍 Analiz Et", type="primary", use_container_width=True):
        with st.spinner("Dosyalar analiz ediliyor..."):
            temp_dir = tempfile.mkdtemp()
            temp_paths = []
            
            try:
                # Dosyaları kaydet
                for f in uploaded_files:
                    temp_path = os.path.join(temp_dir, f.name)
                    with open(temp_path, 'wb') as out:
                        out.write(f.getvalue())
                    temp_paths.append(temp_path)
                
                # Analiz
                analyzer = HacizIhbarAnalyzer()
                sonuc = analyzer.batch_analiz(temp_paths)
                st.session_state.banka_sonuc = sonuc
                
            except Exception as e:
                st.error(f"Analiz hatası: {str(e)}")
            finally:
                shutil.rmtree(temp_dir, ignore_errors=True)
        
        st.rerun()
    
    # Sonuçları göster
    if st.session_state.banka_sonuc:
        sonuc = st.session_state.banka_sonuc
        
        # Metrikler
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Toplam Muhatap", sonuc.toplam_muhatap)
        col2.metric("🏦 Banka", sonuc.banka_sayisi)
        col3.metric("🏢 Şirket", sonuc.tuzel_kisi_sayisi)
        col4.metric("💰 Toplam Bloke", f"{sonuc.toplam_bloke:,.2f} ₺")
        
        # Büyük bloke göstergesi
        if sonuc.toplam_bloke > 0:
            st.markdown(f"""
            <div class="bloke-box">
                <h2>💰 {sonuc.toplam_bloke:,.2f} TL</h2>
                <p>Toplam Bloke Edilen Tutar</p>
            </div>
            """, unsafe_allow_html=True)
        
        st.divider()
        
        # Tabs
        tab1, tab2, tab3 = st.tabs(["📊 Detay", "📋 Tablo", "📥 İndir"])
        
        with tab1:
            st.subheader("Cevap Detayları")
            for c in sonuc.cevaplar:
                if c.cevap_durumu == CevapDurumu.BLOKE_VAR:
                    st.success(f"✅ **{c.muhatap_adi}**: {c.bloke_tutari:,.2f} TL bloke → {c.sonraki_adim}")
                elif c.cevap_durumu == CevapDurumu.HESAP_YOK:
                    st.error(f"❌ **{c.muhatap_adi}**: Hesap bulunamadı → {c.sonraki_adim}")
                elif c.cevap_durumu == CevapDurumu.HESAP_VAR_BAKIYE_YOK:
                    st.warning(f"⚠️ **{c.muhatap_adi}**: Bakiye yok → {c.sonraki_adim}")
                else:
                    st.info(f"ℹ️ **{c.muhatap_adi}**: {c.cevap_durumu.value}")
        
        with tab2:
            if PANDAS_OK:
                df = pd.DataFrame([{
                    'Muhatap': c.muhatap_adi,
                    'Tür': c.muhatap_turu.value,
                    'Durum': c.cevap_durumu.value,
                    'Bloke': f"{c.bloke_tutari:,.2f}",
                    'Aksiyon': c.sonraki_adim
                } for c in sonuc.cevaplar])
                st.dataframe(df, use_container_width=True, hide_index=True)
        
        with tab3:
            # Excel indirme
            if PANDAS_OK:
                excel_buffer = io.BytesIO()
                with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                    df = pd.DataFrame([{
                        'Muhatap': c.muhatap_adi,
                        'Tür': c.muhatap_turu.value,
                        'Durum': c.cevap_durumu.value,
                        'Bloke Tutarı': c.bloke_tutari,
                        'Alacak Tutarı': c.alacak_tutari,
                        'Sonraki Adım': c.sonraki_adim
                    } for c in sonuc.cevaplar])
                    df.to_excel(writer, sheet_name='Analiz', index=False)
                
                st.download_button(
                    "📥 Excel İndir",
                    excel_buffer.getvalue(),
                    f"Haciz_Analiz_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
            
            # TXT indirme
            st.download_button(
                "📄 Rapor İndir (TXT)",
                sonuc.ozet_rapor,
                f"Rapor_{datetime.now().strftime('%Y%m%d_%H%M')}.txt",
                "text/plain",
                use_container_width=True
            )

# ============================================================================
# MODÜL 2: NEAT PDF ÜRETİCİ
# ============================================================================
elif modul == "📄 Neat PDF":
    st.markdown('<div class="main-header">📄 Profesyonel PDF Üretici</div>', unsafe_allow_html=True)
    
    if not PDF_OK:
        st.error("ReportLab kütüphanesi yüklü değil! `pip install reportlab PyPDF2`")
        st.stop()
    
    st.info("UDF dosyalarını profesyonel, okunabilir PDF'lere dönüştürün.")
    
    # Dosya yükleme
    uploaded_file = st.file_uploader(
        "ZIP veya UDF dosyası yükleyin",
        type=['zip', 'udf'],
        key="pdf_uploader"
    )
    
    # Başlık girişi
    pdf_baslik = st.text_input("PDF Başlığı", value="İcra Dosyası", key="pdf_baslik")
    
    if uploaded_file and st.button("🔄 PDF Üret", type="primary", use_container_width=True):
        with st.spinner("PDF oluşturuluyor..."):
            temp_dir = tempfile.mkdtemp()
            
            try:
                # Dosyayı kaydet
                input_path = os.path.join(temp_dir, uploaded_file.name)
                with open(input_path, 'wb') as f:
                    f.write(uploaded_file.getvalue())
                
                # PDF üret
                output_path = os.path.join(temp_dir, "cikti.pdf")
                uretici = NeatPDFUretici()
                rapor = uretici.uret(input_path, output_path, pdf_baslik)
                
                if rapor and os.path.exists(output_path):
                    st.session_state.pdf_rapor = rapor
                    
                    # PDF'i oku
                    with open(output_path, 'rb') as f:
                        pdf_data = f.read()
                    
                    st.success(f"✅ PDF başarıyla oluşturuldu! ({rapor.toplam_sayfa} sayfa)")
                    
                    col1, col2 = st.columns(2)
                    col1.metric("Sayfa Sayısı", rapor.toplam_sayfa)
                    col2.metric("İşlenen Dosya", rapor.islenen_dosya)
                    
                    st.download_button(
                        "📥 PDF İndir",
                        pdf_data,
                        f"{pdf_baslik.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.pdf",
                        "application/pdf",
                        use_container_width=True
                    )
                    
                    if rapor.hatalar:
                        with st.expander("⚠️ Uyarılar"):
                            for h in rapor.hatalar:
                                st.warning(h)
                else:
                    st.error("PDF oluşturulamadı!")
                    
            except Exception as e:
                st.error(f"Hata: {str(e)}")
            finally:
                shutil.rmtree(temp_dir, ignore_errors=True)

# ============================================================================
# MODÜL 3: UYAP DOSYA ANALİZİ
# ============================================================================
elif modul == "📁 Dosya Analizi":
    st.markdown('<div class="main-header">📁 UYAP Dosya Analizi</div>', unsafe_allow_html=True)
    
    if not UYAP_OK:
        st.error("UYAP Analyzer modülü yüklenemedi!")
        st.stop()
    
    st.info("UYAP'tan indirdiğiniz ZIP dosyasını yükleyin. Tüm evraklar taranıp sınıflandırılacak.")
    
    # Dosya yükleme
    uploaded_file = st.file_uploader(
        "UYAP ZIP dosyası yükleyin",
        type=['zip'],
        key="uyap_uploader"
    )
    
    if uploaded_file and st.button("🔍 Taramayı Başlat", type="primary", use_container_width=True):
        with st.spinner("Dosyalar taranıyor..."):
            temp_dir = tempfile.mkdtemp()
            
            try:
                # Dosyayı kaydet
                input_path = os.path.join(temp_dir, uploaded_file.name)
                with open(input_path, 'wb') as f:
                    f.write(uploaded_file.getvalue())
                
                # Analiz
                analyzer = UYAPDosyaAnalyzer()
                sonuc = analyzer.analiz_et(input_path)
                st.session_state.uyap_sonuc = sonuc
                
            except Exception as e:
                st.error(f"Analiz hatası: {str(e)}")
            finally:
                shutil.rmtree(temp_dir, ignore_errors=True)
        
        st.rerun()
    
    # Sonuçları göster
    if st.session_state.uyap_sonuc:
        sonuc = st.session_state.uyap_sonuc
        
        # Metrikler
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Toplam Evrak", sonuc.toplam_evrak)
        col2.metric("Tebligat", len(sonuc.tebligatlar))
        col3.metric("Haciz", len(sonuc.hacizler))
        col4.metric("Aksiyon", len(sonuc.aksiyonlar))
        
        st.divider()
        
        # Tabs
        tab1, tab2, tab3 = st.tabs(["⚡ Aksiyonlar", "📊 Dağılım", "📄 Rapor"])
        
        with tab1:
            if sonuc.aksiyonlar:
                for a in sonuc.aksiyonlar:
                    if "KRİTİK" in str(a.oncelik):
                        st.markdown(f'<div class="kritik-box">🔴 <b>{a.baslik}</b><br>{a.aciklama}</div>', unsafe_allow_html=True)
                    elif "UYARI" in str(a.oncelik):
                        st.markdown(f'<div class="uyari-box">⚠️ <b>{a.baslik}</b><br>{a.aciklama}</div>', unsafe_allow_html=True)
                    else:
                        st.info(f"ℹ️ **{a.baslik}**: {a.aciklama}")
            else:
                st.markdown('<div class="basari-box">✅ Acil aksiyon gerektiren durum yok.</div>', unsafe_allow_html=True)
        
        with tab2:
            if sonuc.evrak_dagilimi:
                if PANDAS_OK:
                    df = pd.DataFrame([
                        {'Evrak Türü': k, 'Adet': v}
                        for k, v in sorted(sonuc.evrak_dagilimi.items(), key=lambda x: -x[1])
                    ])
                    st.bar_chart(df.set_index('Evrak Türü'))
                else:
                    for k, v in sorted(sonuc.evrak_dagilimi.items(), key=lambda x: -x[1]):
                        st.write(f"**{k}**: {v}")
        
        with tab3:
            st.text(sonuc.ozet_rapor)
            st.download_button(
                "📥 Rapor İndir",
                sonuc.ozet_rapor,
                f"UYAP_Analiz_{datetime.now().strftime('%Y%m%d_%H%M')}.txt",
                "text/plain",
                use_container_width=True
            )

# === FOOTER ===
st.divider()
st.caption("⚖️ İcra Analiz Pro v12.0 | Domain Expert: Arda | Tech: Claude | 2026")
