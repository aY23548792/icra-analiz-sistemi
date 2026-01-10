#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
İCRA ANALİZ PRO v12.2 (Final Robust)
====================================
Tam hata korumalı, stateless ve modüler yapı.
"""

import streamlit as st
import tempfile
import os
import shutil
import io
from datetime import datetime

# === MODULE IMPORTS (SAFE) ===
# Modüller yüklenemezse False olur, sınıflar None atanır
BANKA_OK = False
HacizIhbarAnalyzer = None
CevapDurumu = None

try:
    from haciz_ihbar_analyzer import HacizIhbarAnalyzer, CevapDurumu
    BANKA_OK = True
except ImportError as e:
    print(f"Banka Modülü Hatası: {e}")

PDF_OK = False
NeatPDFUretici = None
REPORTLAB_OK = False

try:
    from neat_pdf_uretici import NeatPDFUretici, REPORTLAB_OK
    PDF_OK = REPORTLAB_OK
except ImportError as e:
    print(f"PDF Modülü Hatası: {e}")

UYAP_OK = False
UYAPDosyaAnalyzer = None

try:
    from uyap_dosya_analyzer import UYAPDosyaAnalyzer
    UYAP_OK = True
except ImportError as e:
    print(f"UYAP Modülü Hatası: {e}")

PANDAS_OK = False
try:
    import pandas as pd
    PANDAS_OK = True
except ImportError:
    pass

# === PAGE CONFIG ===
st.set_page_config(page_title="İcra Analiz Pro", page_icon="⚖️", layout="wide")

# === SESSION STATE INIT ===
if 'master_files' not in st.session_state:
    st.session_state.master_files = []
if 'banka_sonuc' not in st.session_state:
    st.session_state.banka_sonuc = None
if 'pdf_rapor' not in st.session_state:
    st.session_state.pdf_rapor = None
if 'uyap_sonuc' not in st.session_state:
    st.session_state.uyap_sonuc = None

def clear_all():
    """Her şeyi sıfırla"""
    st.session_state.master_files = []
    st.session_state.banka_sonuc = None
    st.session_state.pdf_rapor = None
    st.session_state.uyap_sonuc = None
    st.rerun()

# === SIDEBAR ===
with st.sidebar:
    st.title("⚖️ İcra Analiz Pro")
    st.subheader("1. Dosya Yükle")

    uploaded = st.file_uploader(
        "ZIP, UDF veya PDF yükleyin",
        type=['zip', 'pdf', 'udf'],
        accept_multiple_files=True,
        key="main_uploader"
    )
    
    if uploaded:
        new_files = [(f.name, f.getvalue()) for f in uploaded]
        old_names = set(n for n, _ in st.session_state.master_files)
        new_names = set(n for n, _ in new_files)

        if old_names != new_names:
            st.session_state.master_files = new_files
            st.session_state.banka_sonuc = None
            st.session_state.pdf_rapor = None
            st.session_state.uyap_sonuc = None
    
    if st.session_state.master_files:
        st.success(f"📂 Hafızada {len(st.session_state.master_files)} dosya var")
        if st.button("🗑️ Temizle", use_container_width=True):
            clear_all()
    else:
        st.warning("Henüz dosya yok.")

    st.divider()
    st.subheader("2. İşlem Seç")
    modul = st.radio(
        "Modül:",
        ["🏦 Banka Analizi", "📄 Neat PDF", "📁 Dosya Analizi"],
        index=0
    )

# === TEMP FILE HELPER ===
def save_temp_files():
    if not st.session_state.master_files:
        return [], None
    temp_dir = tempfile.mkdtemp()
    paths = []
    for name, data in st.session_state.master_files:
        path = os.path.join(temp_dir, name)
        with open(path, "wb") as f:
            f.write(data)
        paths.append(path)
    return paths, temp_dir

# ============================================================================
# MODÜL 1: BANKA HACİZ İHBAR ANALİZİ
# ============================================================================
if modul == "🏦 Banka Analizi":
    st.header("🏦 Banka Haciz İhbar Analizi")
    
    if not st.session_state.master_files:
        st.info("👈 Lütfen önce sol menüden dosya yükleyin.")
        st.stop()

    if not BANKA_OK:
        st.error("Modül eksik! (haciz_ihbar_analyzer.py)")
        st.stop()

    if st.button("🔍 Analiz Et", type="primary"):
        with st.spinner("İşleniyor..."):
            paths, tdir = save_temp_files()
            try:
                analyzer = HacizIhbarAnalyzer()
                res = analyzer.batch_analiz(paths)
                st.session_state.banka_sonuc = res
            finally:
                if tdir: shutil.rmtree(tdir)
        st.rerun()

    if st.session_state.banka_sonuc:
        res = st.session_state.banka_sonuc
        c1, c2, c3 = st.columns(3)
        c1.metric("Toplam", res.toplam_dosya)
        c2.metric("Bloke", f"{res.toplam_bloke:,.2f} ₺")
        c3.metric("Banka", getattr(res, 'banka_sayisi', 0)) # Güvenli erişim

        st.divider()
        t1, t2 = st.tabs(["Detaylar", "İndir"])
        
        with t1:
            for c in res.cevaplar:
                # Enum değerine güvenli erişim
                durum_val = c.durum.value if hasattr(c.durum, 'value') else str(c.durum)
                is_bloke = durum_val == "💰 BLOKE VAR"
                icon = "✅" if is_bloke else "ℹ️"

                with st.expander(f"{icon} {c.muhatap} - {durum_val}"):
                    st.write(f"Tutar: {c.tutar:,.2f} TL")
                    st.write(f"Öneri: {c.sonraki_adim}")
                    st.caption(c.ham_metin[:200] + "...")

        with t2:
            try:
                # Ozet rapor string ise direkt ver, değilse oluştur
                rapor_txt = res.ozet_rapor if isinstance(res.ozet_rapor, str) else "Rapor oluşturulamadı."
                st.download_button("Rapor İndir", rapor_txt, "banka_rapor.txt")
            except:
                st.error("Rapor indirilemedi.")

# ============================================================================
# MODÜL 2: NEAT PDF
# ============================================================================
elif modul == "📄 Neat PDF":
    st.header("📄 Neat PDF Üretici")

    if not st.session_state.master_files:
        st.info("👈 Lütfen önce sol menüden dosya yükleyin.")
        st.stop()

    if not PDF_OK:
        st.error("ReportLab eksik! (requirements.txt kontrol edin)")
        st.stop()

    baslik = st.text_input("PDF Başlığı", "İcra Dosyası")

    if st.button("🔄 Dönüştür", type="primary"):
        with st.spinner("PDF hazırlanıyor..."):
            paths, tdir = save_temp_files()
            try:
                target = paths[0] if len(paths) == 1 else tdir
                uretici = NeatPDFUretici()
                out_path = os.path.join(tdir, "output.pdf")
                rapor = uretici.uret(target, out_path, baslik)

                if rapor and os.path.exists(out_path):
                    with open(out_path, "rb") as f:
                        st.session_state.pdf_rapor = {
                            "data": f.read(),
                            "info": rapor
                        }
            finally:
                if tdir: shutil.rmtree(tdir)
        st.rerun()

    if st.session_state.pdf_rapor:
        r = st.session_state.pdf_rapor["info"]
        st.success(f"PDF Hazır! ({r.toplam_sayfa} sayfa)")
        st.download_button(
            "📥 İNDİR",
            st.session_state.pdf_rapor["data"],
            "dosya.pdf",
            "application/pdf",
            type="primary"
        )

# ============================================================================
# MODÜL 3: UYAP DOSYA ANALİZİ
# ============================================================================
elif modul == "📁 Dosya Analizi":
    st.header("📁 UYAP Dosya Analizi")

    if not st.session_state.master_files:
        st.info("👈 Lütfen önce sol menüden dosya yükleyin.")
        st.stop()

    if not UYAP_OK:
        st.error("Modül eksik! (uyap_dosya_analyzer.py)")
        st.stop()

    if st.button("🚀 Başlat", type="primary"):
        with st.spinner("Analiz ediliyor..."):
            paths, tdir = save_temp_files()
            try:
                analyzer = UYAPDosyaAnalyzer()
                # Genelde ZIP beklenir
                target = paths[0] if len(paths) == 1 and paths[0].endswith('.zip') else paths[0]
                res = analyzer.analiz_et(target)
                st.session_state.uyap_sonuc = res
            finally:
                if tdir: shutil.rmtree(tdir)
        st.rerun()

    if st.session_state.uyap_sonuc:
        res = st.session_state.uyap_sonuc
        c1, c2 = st.columns(2)
        c1.metric("Evrak", res.toplam_evrak)
        c2.metric("Aksiyon", len(res.aksiyonlar))
        
        if res.aksiyonlar:
            st.subheader("Öneriler")
            for a in res.aksiyonlar:
                st.warning(f"{a.baslik}: {a.aciklama}")

        if hasattr(res, 'ozet_rapor') and res.ozet_rapor:
            st.download_button("Rapor İndir", res.ozet_rapor, "uyap_analiz.txt")
