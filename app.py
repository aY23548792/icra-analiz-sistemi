#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
İCRA ANALİZ SİSTEMİ v11 - Oracle Dashboard (Vision v4.0)
========================================================
Unified interface for Enforcement Law Automation.
Features:
- Global Session State: Upload once, analyze everywhere.
- Neat PDF Merger: Documents + UDFs to clean PDF.
- 89/1-2-3 Bank Analysis.
- UYAP Dossier & Deadline Analysis.
"""

import streamlit as st
import pandas as pd
from datetime import datetime, date
import tempfile
import os
import shutil
import sys

# --- MODÜL İMPORTLARI ---
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from icra_analiz_v2 import IcraUtils, MalTuru, RiskSeviyesi
from haciz_ihbar_analyzer import HacizIhbarAnalyzer, CevapDurumu
from uyap_dosya_analyzer import UyapDosyaAnalyzer
from neat_pdf_uretici import NeatPDFUretici, REPORTLAB_OK

# --- CONFIG ---
st.set_page_config(
    page_title="İcra Analiz Pro v11",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- CUSTOM CSS ---
def load_css():
    st.markdown("""
    <style>
        .main-header { font-size: 2.2rem; font-weight: 800; color: #1E3A5F; text-align: center; margin-bottom: 25px; }
        .stMetric { background-color: #f8f9fa; border-radius: 10px; padding: 15px; border: 1px solid #e9ecef; }
        .risk-box { padding: 20px; border-radius: 12px; margin-bottom: 15px; border-left: 8px solid; }
        .risk-DUSMUS { background-color: #fce4ec; border-left-color: #c2185b; color: #880e4f; }
        .risk-KRITIK { background-color: #fff3e0; border-left-color: #ef6c00; color: #e65100; }
        .risk-GUVENLI { background-color: #e8f5e9; border-left-color: #2e7d32; color: #1b5e20; }
        .title-sub { color: #666; font-size: 0.9rem; margin-top: -20px; margin-bottom: 20px; text-align: center; }
    </style>
    """, unsafe_allow_html=True)

load_css()

# --- SESSION STATE BAŞLATMA ---
if 'master_file' not in st.session_state:
    st.session_state.master_file = None
if 'master_filename' not in st.session_state:
    st.session_state.master_filename = None
if 'analiz_sonuclari' not in st.session_state:
    st.session_state.analiz_sonuclari = {
        'ihbar': None,
        'dosya': None,
        'pdf_rapor': None,
        'pdf_bytes': None
    }

# ============================================================================
# MERKEZİ DOSYA YÖNETİCİSİ (SIDEBAR)
# ============================================================================
with st.sidebar:
    st.image("https://img.icons8.com/wired/128/null/law.png", width=80)
    st.title("İcra Analiz v11")
    
    st.markdown("### 1. Dosya Yükle (Global)")
    st.info("ZIP, UDF veya PDF yükleyin. Modül değiştirseniz bile dosya silinmez.")
    
    uploaded_file = st.file_uploader(
        "Analiz Dosyası:",
        type=['zip', 'udf', 'pdf', 'xml'],
        key="master_uploader"
    )
    
    # State Update
    if uploaded_file is not None:
        if st.session_state.master_filename != uploaded_file.name:
            st.session_state.master_file = uploaded_file.getvalue()
            st.session_state.master_filename = uploaded_file.name
            # Reset results on new file
            st.session_state.analiz_sonuclari = {
                'ihbar': None, 'dosya': None, 'pdf_rapor': None, 'pdf_bytes': None
            }
            st.toast("Yeni dosya algılandı. Analizler temizlendi.", icon="🔄")
    
    if st.session_state.master_file:
        st.success(f"📂 Aktif: {st.session_state.master_filename}")
        if st.button("🗑️ Dosyayı Kaldır"):
            st.session_state.master_file = None
            st.session_state.master_filename = None
            st.session_state.analiz_sonuclari = {
                'ihbar': None, 'dosya': None, 'pdf_rapor': None, 'pdf_bytes': None
            }
            st.rerun()
    
    st.markdown("---")
    st.markdown("### 2. İşlem Seç")
    menu = st.radio(
        "Yazılım Modülü:",
        ["📄 Neat PDF (Birleştir)", "🏦 Banka Haciz Analizi", "📁 UYAP Dosya Analizi", "🧮 Haciz Süre Hesaplayıcı"]
    )
    
    st.markdown("---")
    st.caption("v11.0 Vision 4.0 | Oracle Engine")

# --- UTILITY: TEMP FILE ASSISTANT ---
def get_master_path():
    if not st.session_state.master_file:
        return None, None
    temp_dir = tempfile.mkdtemp()
    file_path = os.path.join(temp_dir, st.session_state.master_filename)
    with open(file_path, "wb") as f:
        f.write(st.session_state.master_file)
    return file_path, temp_dir

# -----------------------------------------------------------------------------
# MODUL 1: NEAT PDF
# -----------------------------------------------------------------------------
if menu.startswith("📄"):
    st.markdown('<div class="main-header">📄 Neat PDF Oluşturucu</div>', unsafe_allow_html=True)
    
    if not st.session_state.master_file:
        st.info("👈 Lütfen sol menüden bir dosya (ZIP veya UDF) yükleyin.")
    else:
        col1, col2 = st.columns([2, 1])
        with col1:
            baslik = st.text_input("PDF Kapak Başlığı", value="İCRA DOSYASI ANALİZİ")
        with col2:
            st.write("&nbsp;")
            btn_run = st.button("Dönüştürmeyi Başlat", type="primary", use_container_width=True)

        if btn_run:
            with st.spinner("Dosyalar UYAP formatına uygun dönüştürülüyor..."):
                file_path, temp_dir = get_master_path()
                try:
                    uretici = NeatPDFUretici()
                    cikti_path = os.path.join(temp_dir, "NEAT_DOSYA.pdf")
                    rapor = uretici.uret(file_path, cikti_path, baslik=baslik)
                    
                    st.session_state.analiz_sonuclari['pdf_rapor'] = rapor
                    if os.path.exists(cikti_path):
                        with open(cikti_path, "rb") as f:
                            st.session_state.analiz_sonuclari['pdf_bytes'] = f.read()
                finally:
                    shutil.rmtree(temp_dir, ignore_errors=True)
                st.rerun()

        if st.session_state.analiz_sonuclari['pdf_rapor']:
            r = st.session_state.analiz_sonuclari['pdf_rapor']
            st.success(f"✅ Hazır! {r.islenen_dosya} evrak birleştirildi.")
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Toplam Sayfa", r.toplam_sayfa)
            c2.metric("İşlem Süresi", f"{r.sure_saniye:.1f}s")
            c3.download_button("📥 İNDİR", st.session_state.analiz_sonuclari['pdf_bytes'], 
                              f"Neat_{st.session_state.master_filename}.pdf", "application/pdf")

# -----------------------------------------------------------------------------
# MODUL 2: BANKA HACİZ (İİK 89)
# -----------------------------------------------------------------------------
elif menu.startswith("🏦"):
    st.markdown('<div class="main-header">🏦 Banka Haciz Analiz Merkezi</div>', unsafe_allow_html=True)
    
    if not st.session_state.master_file:
        st.info("👈 Lütfen Banka Cevaplarını (ZIP/UDF/PDF) sol menüden yükleyin.")
    else:
        if st.button("Derin Analizi Başlat", type="primary", use_container_width=True):
            with st.spinner("Negative-First algoritması çalışıyor..."):
                file_path, temp_dir = get_master_path()
                try:
                    analyzer = HacizIhbarAnalyzer()
                    sonuc = analyzer.batch_analiz([file_path])
                    st.session_state.analiz_sonuclari['ihbar'] = sonuc
                finally:
                    shutil.rmtree(temp_dir, ignore_errors=True)
            st.rerun()

        if st.session_state.analiz_sonuclari['ihbar']:
            s = st.session_state.analiz_sonuclari['ihbar']
            m1, m2, m3 = st.columns(3)
            m1.metric("Toplam Belge", s.toplam_dosya)
            m2.metric("💰 Toplam Bloke", f"{s.toplam_bloke:,.2f} TL")
            m3.metric("Banka Sayısı", s.banka_sayisi)
            
            df = pd.DataFrame([{
                "Banka": c.muhatap,
                "Durum": c.durum.value,
                "Tutar": c.bloke_tutari,
                "Sonraki Adım": c.sonraki_adim
            } for c in s.cevaplar])
            st.dataframe(df, use_container_width=True, hide_index=True)

# -----------------------------------------------------------------------------
# MODUL 3: UYAP DOSYA ANALİZİ
# -----------------------------------------------------------------------------
elif menu.startswith("📁"):
    st.markdown('<div class="main-header">📁 UYAP Dosya & Talimat Analizi</div>', unsafe_allow_html=True)
    
    if not st.session_state.master_file:
        st.info("👈 Lütfen UYAP ZIP dosyasını sol menüden yükleyin.")
    else:
        if st.button("Dossier Taramasını Başlat", type="primary", use_container_width=True):
            analyzer = UyapDosyaAnalyzer()
            file_path, temp_dir = get_master_path()
            try:
                sonuc = analyzer.analyze_zip(file_path)
                st.session_state.analiz_sonuclari['dosya'] = sonuc
            finally:
                shutil.rmtree(temp_dir, ignore_errors=True)
            st.rerun()

        if st.session_state.analiz_sonuclari['dosya']:
            res = st.session_state.analiz_sonuclari['dosya']
            if res.get("talimat_uyarilari"):
                st.warning("🚨 Talimat Masraf Riski Tespit Edildi!")
                for u in res["talimat_uyarilari"]: st.error(u["mesaj"])
            
            if res.get("hacizler"):
                st.subheader("⏳ Haciz Süreleri")
                st.dataframe(pd.DataFrame(res["hacizler"]), use_container_width=True)

# -----------------------------------------------------------------------------
# MODUL 4: QUICK CALCULATOR
# -----------------------------------------------------------------------------
elif menu.startswith("🧮"):
    st.markdown('<div class="main-header">🧮 Süre Hesaplayıcı (Oracle Engine)</div>', unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    h_date = c1.date_input("Haciz Tarihi", value=date(2021, 6, 15))
    m_turu = c2.selectbox("Mal Türü", ["TASINIR", "TASINMAZ", "BANKA_HESABI"])
    avans = st.toggle("Satış Avansı Yatırıldı mı?")
    
    if st.button("Hesapla", use_container_width=True):
        h_dt = datetime.combine(h_date, datetime.min.time())
        res = IcraUtils.haciz_sure_hesapla(h_dt, m_turu, avans)
        
        risk_class = "risk-GUVENLI"
        if res.risk_seviyesi == RiskSeviyesi.DUSMUS: risk_class = "risk-DUSMUS"
        elif res.risk_seviyesi in [RiskSeviyesi.KRITIK, RiskSeviyesi.YUKSEK]: risk_class = "risk-KRITIK"
        
        st.markdown(f'<div class="risk-box {risk_class}"><h2>{res.durum} ({res.risk_seviyesi.value})</h2><p>Son Gün: {res.son_gun.strftime("%d.%m.%Y")}</p><p>Öneri: {res.onerilen_aksiyon}</p></div>', unsafe_allow_html=True)
