#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
İCRA ANALİZ SİSTEMİ - MERKEZİ YÖNETİM ARAYÜZÜ (v5.0 Ultimate)
=============================================================
Özellikler:
1. Merkezi Dosya Yükleme (Global State)
2. Neat PDF (Deep Clean / Matruşka ZIP Desteği)
3. Banka Haciz Analizi (Context-Aware)
4. Genel UYAP Dosya Analizi
"""

import streamlit as st
import pandas as pd
import os
import sys
import tempfile
import shutil
from datetime import datetime

# -----------------------------------------------------------------------------
# 1. MODÜL İMPORTLARI VE KONTROLLERİ
# -----------------------------------------------------------------------------
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Banka Analiz Modülü
try:
    from haciz_ihbar_analyzer import HacizIhbarAnalyzer, CevapDurumu
    BANKA_AVAILABLE = True
except ImportError:
    BANKA_AVAILABLE = False

# Neat PDF Modülü (Yeni Deep Clean Versiyon)
try:
    from neat_pdf_uretici import NeatPDFUretici, REPORTLAB_OK
    PDF_AVAILABLE = REPORTLAB_OK
except ImportError:
    PDF_AVAILABLE = False

# UYAP Dosya Analiz Modülü
try:
    from uyap_dosya_analyzer import UYAPDosyaAnalyzer, IslemDurumu
    UYAP_AVAILABLE = True
except ImportError:
    UYAP_AVAILABLE = False

# -----------------------------------------------------------------------------
# 2. SAYFA AYARLARI VE STİL
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="İcra Hukuk Otomasyonu",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    .main-header { font-size: 2rem; font-weight: 700; color: #1E3A5F; text-align: center; margin-bottom: 20px; border-bottom: 2px solid #eee; padding-bottom: 10px; }
    .success-box { background-color: #e8f5e9; border-left: 5px solid #4caf50; padding: 15px; border-radius: 5px; }
    .warning-box { background-color: #fff3e0; border-left: 5px solid #ff9800; padding: 15px; border-radius: 5px; }
    .error-box { background-color: #ffebee; border-left: 5px solid #f44336; padding: 15px; border-radius: 5px; }
    .metric-card { background-color: #f8f9fa; padding: 10px; border-radius: 10px; text-align: center; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
    div[data-testid="stFileUploader"] { margin-bottom: 10px; }
</style>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 3. SESSION STATE (HAFIZA) YÖNETİMİ
# -----------------------------------------------------------------------------
if 'master_file_bytes' not in st.session_state:
    st.session_state.master_file_bytes = None
if 'master_filename' not in st.session_state:
    st.session_state.master_filename = None
# Analiz sonuçlarını saklamak için (sayfa yenilense de gitmesin)
if 'results' not in st.session_state:
    st.session_state.results = {
        'pdf_path': None,      # Oluşturulan PDF'in yolu (temp)
        'pdf_bytes': None,     # İndirme için byte verisi
        'pdf_rapor': None,     # Rapor objesi
        'banka_sonuc': None,   # Banka analiz sonucu
        'dosya_sonuc': None    # Genel analiz sonucu
    }

# -----------------------------------------------------------------------------
# 4. YARDIMCI FONKSİYONLAR
# -----------------------------------------------------------------------------
def get_temp_file_path(filename, file_bytes):
    """Uploaded file bytes'ı geçici bir dosyaya yazar ve yolunu döner."""
    temp_dir = tempfile.mkdtemp()
    file_path = os.path.join(temp_dir, filename)
    with open(file_path, "wb") as f:
        f.write(file_bytes)
    return file_path, temp_dir

# -----------------------------------------------------------------------------
# 5. SIDEBAR (DOSYA YÜKLEME VE MENÜ)
# -----------------------------------------------------------------------------
with st.sidebar:
    st.title("⚖️ İcra Otomasyon")
    
    st.markdown("### 1. Dosya Yükle")
    uploaded_file = st.file_uploader(
        "ZIP, UDF veya PDF Yükle", 
        type=['zip', 'udf', 'pdf', 'xml', 'tiff', 'tif'],
        help="İç içe klasörler veya ZIP'ler olabilir. Sistem otomatik çözer."
    )

    # Dosya yüklendiğinde State'i güncelle
    if uploaded_file is not None:
        # Eğer yeni bir dosya geldiyse hafızayı güncelle
        if st.session_state.master_filename != uploaded_file.name:
            st.session_state.master_file_bytes = uploaded_file.getvalue()
            st.session_state.master_filename = uploaded_file.name
            # Yeni dosya geldiği için eski sonuçları temizle
            st.session_state.results = {k: None for k in st.session_state.results}
            st.toast("Yeni dosya sisteme alındı!", icon="✅")

    # Yüklü dosya bilgisi
    if st.session_state.master_file_bytes:
        st.info(f"📂 Aktif Dosya:\n**{st.session_state.master_filename}**")
        if st.button("🗑️ Temizle", use_container_width=True):
            st.session_state.master_file_bytes = None
            st.session_state.master_filename = None
            st.session_state.results = {k: None for k in st.session_state.results}
            st.rerun()
    else:
        st.warning("⚠️ İşlem yapmak için önce dosya yükleyin.")

    st.markdown("---")
    st.markdown("### 2. Modül Seç")
    selected_module = st.radio(
        "İşlem:",
        ["📄 Neat PDF (Birleştir)", "🏦 Banka Haciz Analizi", "📁 UYAP Dosya Analizi"]
    )

# -----------------------------------------------------------------------------
# 6. MODÜL 1: NEAT PDF OLUŞTURUCU
# -----------------------------------------------------------------------------
def render_neat_pdf():
    st.markdown('<div class="main-header">📄 Neat PDF Oluşturucu (Deep Clean)</div>', unsafe_allow_html=True)
    
    if not st.session_state.master_file_bytes:
        st.info("👈 Lütfen sol menüden dosya yükleyerek başlayın.")
        return

    if not PDF_AVAILABLE:
        st.error("❌ Neat PDF modülü (ReportLab) eksik. Lütfen `requirements.txt` dosyasını kontrol edin.")
        return

    col1, col2 = st.columns([3, 1])
    with col1:
        st.markdown("""
        **Ne Yapar?**
        - İç içe geçmiş ZIP'leri ve klasörleri tarar.
        - UDF, TIFF ve PDF dosyalarını bulur.
        - Tek bir profesyonel, dizinli PDF haline getirir.
        """)
        pdf_baslik = st.text_input("PDF Başlığı", value="İCRA DOSYASI İNCELEMESİ")
    
    with col2:
        st.write("") # Spacer
        st.write("") 
        btn_convert = st.button("🚀 Dönüştür", type="primary", use_container_width=True)

    # İşlem Butonu
    if btn_convert:
        with st.spinner("Matruşka ZIP'ler çözülüyor, UDF'ler işleniyor..."):
            path, tmp_dir = get_temp_file_path(st.session_state.master_filename, st.session_state.master_file_bytes)
            
            try:
                uretici = NeatPDFUretici()
                cikti_yolu = os.path.join(tmp_dir, "BIRLESIK_DOSYA.pdf")
                
                # BÜYÜK İŞLEM BURADA
                rapor = uretici.uret(path, cikti_yolu, baslik=pdf_baslik)
                
                # Sonucu State'e kaydet
                st.session_state.results['pdf_rapor'] = rapor
                if os.path.exists(cikti_yolu):
                    with open(cikti_yolu, "rb") as f:
                        st.session_state.results['pdf_bytes'] = f.read()
                
            except Exception as e:
                st.error(f"Dönüştürme Hatası: {e}")
            finally:
                # Temizlik
                if os.path.exists(tmp_dir):
                    shutil.rmtree(tmp_dir)
        
        st.rerun()

    # Sonuç Gösterimi
    if st.session_state.results['pdf_bytes']:
        rapor = st.session_state.results['pdf_rapor']
        
        st.success(f"✅ PDF Hazır! ({rapor.sure_saniye:.1f} saniye)")
        
        m1, m2, m3 = st.columns(3)
        m1.metric("Toplam Sayfa", rapor.toplam_sayfa)
        m2.metric("İşlenen Evrak", rapor.islenen_dosya)
        m3.metric("Bulunan Dosya", rapor.toplam_dosya)
        
        # İndirme Butonu
        st.download_button(
            label="📥 PROFESYONEL PDF İNDİR",
            data=st.session_state.results['pdf_bytes'],
            file_name=f"Neat_{st.session_state.master_filename}.pdf",
            mime="application/pdf",
            type="primary",
            use_container_width=True
        )

        # Hata/Uyarı Logları
        if rapor.hatalar:
            with st.expander("⚠️ İşlem Uyarıları"):
                for err in rapor.hatalar:
                    st.warning(err)

# -----------------------------------------------------------------------------
# 7. MODÜL 2: BANKA HACİZ ANALİZİ
# -----------------------------------------------------------------------------
def render_banka_analiz():
    st.markdown('<div class="main-header">🏦 Banka Haciz İhbar Analizi</div>', unsafe_allow_html=True)

    if not st.session_state.master_file_bytes:
        st.info("👈 Lütfen sol menüden Banka Cevaplarını içeren ZIP yükleyin.")
        return

    if not BANKA_AVAILABLE:
        st.error("❌ Haciz İhbar Analyzer modülü bulunamadı.")
        return

    if st.button("🔍 Analizi Başlat", type="primary"):
        with st.spinner("Banka cevapları taranıyor, blokeler hesaplanıyor..."):
            path, tmp_dir = get_temp_file_path(st.session_state.master_filename, st.session_state.master_file_bytes)
            try:
                # Analyzer genelde liste bekler, tek dosya olsa bile listeye alıyoruz
                analyzer = HacizIhbarAnalyzer()
                # Batch analiz, ZIP'i kendisi açıp traverse eder (veya neat_pdf mantığı eklenebilir)
                sonuc = analyzer.batch_analiz([path])
                st.session_state.results['banka_sonuc'] = sonuc
            except Exception as e:
                st.error(f"Analiz Hatası: {e}")
            finally:
                if os.path.exists(tmp_dir):
                    shutil.rmtree(tmp_dir)
        st.rerun()

    # Sonuçlar
    if st.session_state.results['banka_sonuc']:
        sonuc = st.session_state.results['banka_sonuc']
        
        # Metrikler
        c1, c2, c3 = st.columns(3)
        c1.metric("Toplam Cevap", sonuc.toplam_dosya)
        c2.metric("Bloke Miktarı", f"{sonuc.toplam_bloke:,.2f} ₺")
        c3.metric("Aksiyon Gereken", len([c for c in sonuc.cevaplar if "GÖNDER" in c.sonraki_adim]))
        
        st.divider()
        
        t1, t2, t3 = st.tabs(["🚨 Aksiyonlar", "💰 Bloke Detay", "📋 Tüm Liste"])
        
        with t1:
            aksiyonlar = [c for c in sonuc.cevaplar if "GÖNDER" in c.sonraki_adim or "İtiraz" in c.cevap_durumu.value]
            if aksiyonlar:
                for a in aksiyonlar:
                    st.warning(f"**{a.muhatap}**: {a.sonraki_adim} ({a.cevap_durumu.value})")
            else:
                st.success("Acil aksiyon gerektiren bir durum yok.")
        
        with t2:
            blokeler = [c for c in sonuc.cevaplar if c.cevap_durumu == CevapDurumu.BLOKE_VAR]
            if blokeler:
                for b in blokeler:
                    st.success(f"**{b.muhatap}**: {b.bloke_tutari:,.2f} TL Bloke")
            else:
                st.info("Bloke tespit edilemedi.")
                
        with t3:
            df = pd.DataFrame([{
                "Kurum": c.muhatap,
                "Durum": c.cevap_durumu.value,
                "Tutar": c.bloke_tutari,
                "Öneri": c.sonraki_adim
            } for c in sonuc.cevaplar])
            st.dataframe(df, use_container_width=True)

# -----------------------------------------------------------------------------
# 8. MODÜL 3: GENEL DOSYA ANALİZİ
# -----------------------------------------------------------------------------
def render_genel_analiz():
    st.markdown('<div class="main-header">📁 UYAP Dosya Analizi</div>', unsafe_allow_html=True)
    
    if not st.session_state.master_file_bytes:
        st.info("👈 Lütfen UYAP Tüm Dosya ZIP'ini yükleyin.")
        return

    if not UYAP_AVAILABLE:
        st.error("❌ UYAP Dosya Analyzer modülü eksik.")
        return

    if st.button("🕵️ Dosyayı İncele", type="primary"):
        with st.spinner("Tebligatlar, süreler ve evraklar analiz ediliyor..."):
            path, tmp_dir = get_temp_file_path(st.session_state.master_filename, st.session_state.master_file_bytes)
            try:
                analyzer = UYAPDosyaAnalyzer()
                sonuc = analyzer.analiz_et(path)
                st.session_state.results['dosya_sonuc'] = sonuc
            except Exception as e:
                st.error(f"Analiz Hatası: {e}")
            finally:
                if os.path.exists(tmp_dir):
                    shutil.rmtree(tmp_dir)
        st.rerun()

    if st.session_state.results['dosya_sonuc']:
        sonuc = st.session_state.results['dosya_sonuc']
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Toplam Evrak", sonuc.toplam_evrak)
        c2.metric("Tebligat Sayısı", len(sonuc.tebligatlar))
        c3.metric("Kritik Uyarı", len(sonuc.aksiyonlar))
        
        if sonuc.aksiyonlar:
            st.subheader("🚨 Kritik Uyarılar")
            for ax in sonuc.aksiyonlar:
                if ax.oncelik == IslemDurumu.KRITIK:
                    st.error(f"**{ax.baslik}**: {ax.aciklama}")
                elif ax.oncelik == IslemDurumu.UYARI:
                    st.warning(f"**{ax.baslik}**: {ax.aciklama}")
                else:
                    st.info(f"**{ax.baslik}**: {ax.aciklama}")
        else:
            st.success("Kritik bir eksiklik tespit edilmedi.")
            
        with st.expander("📄 Evrak Dağılımı"):
            st.json(sonuc.evrak_dagilimi)
            
        st.download_button(
            "Raporu İndir (TXT)", 
            sonuc.ozet_rapor, 
            file_name="Analiz_Raporu.txt"
        )

# -----------------------------------------------------------------------------
# 9. ANA YÖNLENDİRME
# -----------------------------------------------------------------------------
if selected_module.startswith("📄"):
    render_neat_pdf()
elif selected_module.startswith("🏦"):
    render_banka_analiz()
elif selected_module.startswith("📁"):
    render_genel_analiz()

# Footer
st.markdown("---")
st.markdown("<div style='text-align: center; color: grey; font-size: 0.8em;'>İcra Analiz Sistemi v5.0 | Ultimate Edition</div>", unsafe_allow_html=True)