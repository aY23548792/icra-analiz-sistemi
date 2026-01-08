#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
İCRA ANALİZ SİSTEMİ v11 - Oracle Dashboard
==========================================
Unified interface for Enforcement Law Automation.
Modules:
1. Bank Selection & Bloke Analysis (İİK 89)
2. UYAP Dossier Analysis & Deadline Tracker (İİK 106-110)
3. Standalone Legal Calculators (Oracle Engine)
"""

import streamlit as st
import pandas as pd
from datetime import datetime, date
import tempfile
import os

# Import Oracle Modules
from icra_analiz_v2 import IcraUtils, MalTuru, RiskSeviyesi
from haciz_ihbar_analyzer import HacizIhbarAnalyzer, CevapDurumu
from uyap_dosya_analyzer import UyapDosyaAnalyzer

# --- CONFIG ---
st.set_page_config(
    page_title="İcra Hukuk Oracle v11",
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

# --- SIDEBAR NAVIGATION ---
st.sidebar.image("https://img.icons8.com/wired/128/null/law.png", width=80)
st.sidebar.title("İcra Analiz v11")
st.sidebar.markdown("---")

menu = st.sidebar.radio(
    "Operasyon Merkezi",
    ["🏦 Banka Haciz Analizi", "📁 UYAP Dosya Analizi", "🧮 Haciz Süre Hesaplayıcı", "📜 Masraf & Faiz Araçları"]
)

st.sidebar.markdown("---")
st.sidebar.caption("v11.0 Oracle Edition | Law 7343 Compliant")

# -----------------------------------------------------------------------------
# MODULE 1: BANK RESPONSE ANALYSIS (İİK 89)
# -----------------------------------------------------------------------------
if menu.startswith("🏦"):
    st.markdown('<div class="main-header">🏦 Banka Haciz İhbar Analiz Merkezi</div>', unsafe_allow_html=True)
    st.markdown('<div class="title-sub">İİK 89/1-2-3 Yanıtlarının Akıllı Analizi ve Bloke Tespiti</div>', unsafe_allow_html=True)
    
    col1, col2 = st.columns([2, 1])
    with col1:
        uploaded_files = st.file_uploader("Banka yanıtlarını (PDF) yükleyin", accept_multiple_files=True, type=['pdf'])
    with col2:
        st.info("💡 **İpucu:** 'Negative-First' algoritması sayesinde yanlış bakiye tespitleri %99 oranında engellenir.")

    if uploaded_files:
        if st.button("Analizi Başlat", use_container_width=True):
            analyzer = HacizIhbarAnalyzer()
            
            with tempfile.TemporaryDirectory() as tmpdir:
                paths = []
                for uf in uploaded_files:
                    p = os.path.join(tmpdir, uf.name)
                    with open(p, "wb") as f: f.write(uf.getbuffer())
                    paths.append(p)
                
                results = analyzer.batch_process(paths)
                
                # Metrics Row
                m1, m2, m3 = st.columns(3)
                m1.metric("Toplam Belge", results["count"])
                m2.metric("💰 Tespit Edilen Bloke", f"{results['total_bloke']:,.2f} TL")
                m3.metric("Hesap Sayısı", results["bloke_count"])
                
                # Table
                data = []
                for r in results["results"]:
                    data.append({
                        "Banka / Muhatap": r.muhatap,
                        "Durum": r.durum.value,
                        "Tutar (TL)": f"{r.tutar:,.2f}",
                        "Sonraki Adım": r.sonraki_adim,
                        "Dosya No": r.dosya_no or "Tespiti Zor"
                    })
                
                df = pd.DataFrame(data)
                st.dataframe(df, use_container_width=True, hide_index=True)
                
                if results["total_bloke"] > 0:
                    st.success(f"Tebrikler! Toplam {results['total_bloke']:,.2f} TL tahsilat potansiyeli tespit edildi. Lütfen Mahsup Taleplerini hazırlayın.")

# -----------------------------------------------------------------------------
# MODULE 2: UYAP DOSSIER ANALYSIS
# -----------------------------------------------------------------------------
elif menu.startswith("📁"):
    st.markdown('<div class="main-header">📁 UYAP Dosya & Talimat Analizi</div>', unsafe_allow_html=True)
    st.markdown('<div class="title-sub">UYAP ZIP Paketlerinden Süre Analizi ve Masraf Risk Tespiti</div>', unsafe_allow_html=True)
    
    uf = st.file_uploader("UYAP'tan indirilen 'Dosya_Evrak.zip' dosyasını yükleyin", type="zip")
    
    if uf:
        if st.button("Dossier Taramasını Başlat", use_container_width=True):
            analyzer = UyapDosyaAnalyzer()
            
            with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp:
                tmp.write(uf.getbuffer())
                zip_path = tmp.name
            
            try:
                res = analyzer.analyze_zip(zip_path)
                
                # 1. Critical Warnings (Talimat Costs)
                if res["talimat_uyarilari"]:
                    st.warning("🚨 Kritik Uyarı: Talimat Dosyalarında Eksik Masraf Riski")
                    for u in res["talimat_uyarilari"]:
                        st.error(f"**{u['dosya']}**: {u['mesaj']}")
                
                # 2. Seizure Deadlines
                if res["hacizler"]:
                    st.subheader("⏳ Haciz Süre Analizi (İİK 106-110)")
                    h_df = pd.DataFrame([vars(h) for h in res["hacizler"]])
                    st.dataframe(h_df, use_container_width=True, hide_index=True)
                
                # 3. Document Summary
                with st.expander("📂 Evrak Listesi ve Sınıflandırma"):
                    st.table(res["evraklar"])
                    
                if not res["hacizler"] and not res["talimat_uyarilari"]:
                    st.info("Dosya içerisinde aktif bir risk veya haciz tutanağı tespit edilemedi.")
                    
            finally:
                if os.path.exists(zip_path): os.remove(zip_path)

# -----------------------------------------------------------------------------
# MODULE 3: DEADLINE CALCULATOR
# -----------------------------------------------------------------------------
elif menu.startswith("🧮"):
    st.markdown('<div class="main-header">🧮 İcra Hukuk Beyni: Süre Hesaplayıcı</div>', unsafe_allow_html=True)
    st.markdown('<div class="title-sub">Görsel Seizure Deadline Engine (İİK 106/110)</div>', unsafe_allow_html=True)
    
    with st.container(border=True):
        c1, c2 = st.columns(2)
        h_date = c1.date_input("Haciz Tarihi", value=date(2021, 10, 15))
        m_turu = c2.selectbox("Mal Türü", ["TASINIR (Araç vb.)", "TASINMAZ (Ev, Arsa)", "BANKA/MAAŞ (Süre İşlemez)"])
        
        c3, c4 = st.columns(2)
        avans = c3.toggle("Satış Avansı / Masrafı Yatırıldı mı?", value=False)
        a_date = None
        if avans:
            a_date = c4.date_input("Avans Yatırma Tarihi", value=date.today())
    
    if st.button("Hukuki Analiz Yap", use_container_width=True):
        # Map input
        mal = MalTuru.TASINIR
        if "TASINMAZ" in m_turu: mal = MalTuru.TASINMAZ
        elif "BANKA" in m_turu: mal = MalTuru.BANKA_HESABI
        
        h_dt = datetime.combine(h_date, datetime.min.time())
        a_dt = datetime.combine(a_date, datetime.min.time()) if a_date else None
        
        res = IcraUtils.haciz_sure_hesapla(h_dt, mal, avans, a_dt)
        
        # Color Logic
        risk_class = "risk-GUVENLI"
        if res.risk_seviyesi == RiskSeviyesi.DUSMUS: risk_class = "risk-DUSMUS"
        elif res.risk_seviyesi in [RiskSeviyesi.KRITIK, RiskSeviyesi.YUKSEK]: risk_class = "risk-KRITIK"
        
        st.markdown(f"""
        <div class="risk-box {risk_class}">
            <h2 style="margin:0">{res.durum} ({res.risk_seviyesi.value})</h2>
            <hr style="margin:10px 0">
            <p><strong>Son İşlem Günü:</strong> {res.son_gun.strftime('%d.%m.%Y')}</p>
            <p><strong>Kalan Süre:</strong> {res.kalan_gun} Gün</p>
            <p><strong>Strateji:</strong> {res.onerilen_aksiyon}</p>
            <small>Legal Basis: {res.yasal_dayanak}</small>
        </div>
        """, unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# MODULE 4: OTHER TOOLS (Placeholder)
# -----------------------------------------------------------------------------
else:
    st.markdown('<div class="main-header">📜 Masraf & Faiz Araçları</div>', unsafe_allow_html=True)
    st.info("Bu modül 'İcra Analiz v11.1' güncellemesi ile aktif edilecektir. Şu anki odak: 'Haciz Düşmesi' ve '89 İhbarnameleri'.")
    st.image("https://img.icons8.com/wired/128/null/calculator.png", width=100)
    st.write("Planlanan Özellikler:")
    st.write("- Kademeli Yasal Faiz Hesaplayıcı")
    ord_list = ["EYBM Faiz Oranları", "Reeskont / Avans Faizleri", "Harç ve Masraf Tarifesi (2026)"]
    for item in ord_list:
        st.write(f"🔹 {item}")
