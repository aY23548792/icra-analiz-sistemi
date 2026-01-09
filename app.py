#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
İCRA ANALİZ PRO v11.0 (Stateless & Robust)
==========================================
"""

import streamlit as st
import tempfile
import os
import shutil
from haciz_ihbar_analyzer import HacizIhbarAnalyzer, CevapDurumu
from neat_pdf_uretici import NeatPDFUretici, REPORTLAB_OK
from uyap_dosya_analyzer import UYAPDosyaAnalyzer

st.set_page_config(page_title="İcra Analiz Pro", layout="wide")

# STATE INIT
if 'file_path' not in st.session_state: st.session_state.file_path = None
if 'analysis_results' not in st.session_state: st.session_state.analysis_results = {}

# SIDEBAR
with st.sidebar:
    st.title("⚖️ İcra Analiz")
    uploaded_file = st.file_uploader("Dosya Yükle (ZIP/UDF/PDF)", type=['zip','udf','pdf'])
    
    if uploaded_file:
        # Stateless dosya kaydı (Temp'e yazıyoruz)
        if st.session_state.file_path is None:
            tfile = tempfile.NamedTemporaryFile(delete=False, suffix=f"_{uploaded_file.name}")
            tfile.write(uploaded_file.getvalue())
            tfile.close()
            st.session_state.file_path = tfile.name
            st.success(f"Dosya yüklendi: {uploaded_file.name}")
    
    modul = st.radio("Modül Seç:", ["🏦 Banka Analizi", "📄 Neat PDF", "📁 Genel Analiz"])

# MAIN AREA
if not st.session_state.file_path:
    st.info("Lütfen sol menüden dosya yükleyin.")
    st.stop()

path = st.session_state.file_path

if modul == "🏦 Banka Analizi":
    st.header("Banka Haciz İhbar Analizi")
    if st.button("Analiz Et"):
        analyzer = HacizIhbarAnalyzer()
        # Batch analiz tek dosya yolunu liste olarak alır
        res = analyzer.batch_analiz([path])
        st.session_state.analysis_results['banka'] = res
    
    if 'banka' in st.session_state.analysis_results:
        res = st.session_state.analysis_results['banka']
        c1, c2 = st.columns(2)
        c1.metric("Toplam Dosya", res.toplam_dosya)
        c2.metric("Toplam Bloke", f"{res.toplam_bloke:,.2f} TL")
        
        st.subheader("Detaylar")
        for c in res.cevaplar:
            color = "green" if c.durum == CevapDurumu.BLOKE_VAR else "red"
            st.markdown(f":{color}[**{c.muhatap}**]: {c.durum.value} - {c.tutar:,.2f} TL -> *{c.sonraki_adim}*")

elif modul == "📄 Neat PDF":
    st.header("Neat PDF Üretici")
    if not REPORTLAB_OK:
        st.error("ReportLab kütüphanesi eksik!")
    elif st.button("PDF Üret"):
        with st.spinner("Dönüştürülüyor..."):
            uretici = NeatPDFUretici()
            out_path = path + "_neat.pdf"
            rapor = uretici.uret(path, out_path)
            
            if rapor:
                st.success(f"PDF Hazır! ({rapor.toplam_sayfa} sayfa)")
                with open(out_path, "rb") as f:
                    st.download_button("İndir", f.read(), "analiz.pdf", "application/pdf")
            else:
                st.error("PDF oluşturulamadı.")

elif modul == "📁 Genel Analiz":
    st.header("UYAP Dosya Analizi")
    if st.button("Taramayı Başlat"):
        analyzer = UYAPDosyaAnalyzer()
        res = analyzer.analiz_et(path)
        
        st.info(f"Toplam {res.toplam_evrak} evrak tarandı.")
        if res.aksiyonlar:
            st.warning("Aksiyonlar:")
            for a in res.aksiyonlar:
                st.write(f"- {a.baslik}: {a.aciklama}")
