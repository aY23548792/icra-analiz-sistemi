#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
İCRA ANALİZ PRO v12.4 (Fast & Robust)
=====================================
"""

import streamlit as st
import tempfile
import os
import shutil
from datetime import datetime

# === IMPORTS ===
try:
    from haciz_ihbar_analyzer import HacizIhbarAnalyzer, CevapDurumu
    BANKA_OK = True
except ImportError:
    BANKA_OK = False

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

st.set_page_config(page_title="İcra Analiz Pro", layout="wide")

if 'master_files' not in st.session_state: st.session_state.master_files = []
if 'results' not in st.session_state: st.session_state.results = {}

with st.sidebar:
    st.title("⚖️ İcra Analiz")
    uploaded = st.file_uploader("Dosya Yükle", type=['zip', 'pdf', 'udf'], accept_multiple_files=True)
    
    if uploaded:
        new_files = [(f.name, f.getvalue()) for f in uploaded]
        # Simple name check
        if set(n for n, _ in new_files) != set(n for n, _ in st.session_state.master_files):
            st.session_state.master_files = new_files
            st.session_state.results = {}
    
    if st.session_state.master_files:
        st.success(f"{len(st.session_state.master_files)} dosya hazır")
        if st.button("Temizle"):
            st.session_state.master_files = []
            st.session_state.results = {}
            st.rerun()

    modul = st.radio("Modül:", ["🏦 Banka", "📄 PDF", "📁 Dosya"])

def get_paths(temp_dir):
    paths = []
    for name, data in st.session_state.master_files:
        p = os.path.join(temp_dir, name)
        with open(p, "wb") as f: f.write(data)
        paths.append(p)
    return paths

if modul == "🏦 Banka":
    st.header("Banka Analizi")
    if not BANKA_OK: st.error("Modül eksik.")
    elif st.button("Analiz Et"):
        with st.spinner("Hızlı Analiz..."):
            tdir = tempfile.mkdtemp()
            try:
                paths = get_paths(tdir)
                analyzer = HacizIhbarAnalyzer()
                res = analyzer.batch_analiz(paths)
                st.session_state.results['banka'] = res
            finally:
                shutil.rmtree(tdir)

    if 'banka' in st.session_state.results:
        res = st.session_state.results['banka']
        st.metric("Bloke", f"{res.toplam_bloke:,.2f} TL")
        for c in res.cevaplar:
            st.write(f"{c.muhatap}: {c.durum.value} - {c.tutar} TL")

elif modul == "📄 PDF":
    st.header("PDF Üretici")
    if not PDF_OK: st.error("Modül eksik.")
    elif st.button("PDF Üret"):
        with st.spinner("Üretiliyor..."):
            tdir = tempfile.mkdtemp()
            try:
                paths = get_paths(tdir)
                target = paths[0] if len(paths) == 1 else tdir
                uretici = NeatPDFUretici()
                out = os.path.join(tdir, "out.pdf")
                rapor = uretici.uret(target, out)
                if rapor:
                    with open(out, "rb") as f:
                        st.download_button("İndir", f.read(), "rapor.pdf")
            finally:
                shutil.rmtree(tdir)

elif modul == "📁 Dosya":
    st.header("UYAP Analiz")
    if not UYAP_OK: st.error("Modül eksik.")
    elif st.button("Analiz"):
        with st.spinner("Taranıyor..."):
            tdir = tempfile.mkdtemp()
            try:
                paths = get_paths(tdir)
                analyzer = UYAPDosyaAnalyzer()
                res = analyzer.analiz_et(paths[0])
                st.session_state.results['uyap'] = res
            finally:
                shutil.rmtree(tdir)

    if 'uyap' in st.session_state.results:
        res = st.session_state.results['uyap']
        st.metric("Evrak", res.toplam_evrak)
        st.write(res.ozet_rapor)
