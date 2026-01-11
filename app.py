#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
İCRA ANALİZ PRO v12.5 (Stateless + Fixed Attributes)
====================================================
Düzeltilmiş attribute isimleri ve robust file handling.

Author: Arda & Claude
"""

import streamlit as st
import tempfile
import os
import shutil
from datetime import datetime

# === MODULE IMPORTS ===
try:
    from haciz_ihbar_analyzer import HacizIhbarAnalyzer, CevapDurumu, MuhatapTuru
    BANKA_OK = True
except ImportError as e:
    BANKA_OK = False
    print(f"Haciz modülü yüklenemedi: {e}")

try:
    from neat_pdf_uretici import NeatPDFUretici, REPORTLAB_OK
    PDF_OK = REPORTLAB_OK
except ImportError:
    PDF_OK = False

try:
    from uyap_dosya_analyzer import UYAPDosyaAnalyzer, IslemDurumu, RiskSeviyesi
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
    page_title="İcra Analiz Pro v12.5",
    page_icon="⚖️",
    layout="wide"
)

# === CUSTOM CSS ===
st.markdown("""
<style>
    .bloke-box {
        background: linear-gradient(135deg, #48BB78, #38A169);
        color: white;
        padding: 1.5rem;
        border-radius: 10px;
        text-align: center;
        margin: 1rem 0;
    }
    .bloke-box h2 { margin: 0; font-size: 2rem; }
    .kritik-box {
        background: linear-gradient(135deg, #FC8181, #E53E3E);
        color: white;
        padding: 1rem;
        border-radius: 8px;
        margin: 0.5rem 0;
    }
</style>
""", unsafe_allow_html=True)

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

# === SIDEBAR ===
with st.sidebar:
    st.title("⚖️ İcra Analiz Pro")
    st.caption("v12.5 | Context-Aware Edition")
    
    st.divider()
    
    # Dosya Yükleme
    st.subheader("📂 Dosya Yükle")
    
    uploaded = st.file_uploader(
        "ZIP, UDF veya PDF",
        type=['zip', 'pdf', 'udf'],
        accept_multiple_files=True,
        key="main_uploader"
    )
    
    # İsim bazlı değişiklik kontrolü
    if uploaded:
        new_files = [(f.name, f.getvalue()) for f in uploaded]
        old_names = set(n for n, _ in st.session_state.master_files)
        new_names = set(n for n, _ in new_files)
        
        if old_names != new_names:
            st.session_state.master_files = new_files
            st.session_state.banka_sonuc = None
            st.session_state.pdf_rapor = None
            st.session_state.uyap_sonuc = None
    
    # Durum göster
    if st.session_state.master_files:
        st.success(f"✅ {len(st.session_state.master_files)} dosya hazır")
        for name, _ in st.session_state.master_files[:5]:
            st.caption(f"  📄 {name}")
        if len(st.session_state.master_files) > 5:
            st.caption(f"  ... ve {len(st.session_state.master_files) - 5} dosya daha")
        
        if st.button("🗑️ Temizle", use_container_width=True):
            clear_all()
            st.rerun()
    else:
        st.info("Dosya yüklenmedi")
    
    st.divider()
    
    # Modül Seçimi
    st.subheader("🔧 Modül Seç")
    modul = st.radio(
        "Modül:",
        ["🏦 Banka Analizi", "📄 PDF Üretici", "📁 UYAP Analizi"],
        index=0,
        label_visibility="collapsed"
    )
    
    st.divider()
    
    # Modül durumu
    st.caption("Modül Durumu")
    st.write(f"{'✅' if BANKA_OK else '❌'} Haciz İhbar")
    st.write(f"{'✅' if PDF_OK else '❌'} PDF Üretici")
    st.write(f"{'✅' if UYAP_OK else '❌'} UYAP Analiz")

# === HELPER: Geçici dosya oluştur ===
def save_temp_files():
    """State'deki dosyaları temp klasöre yazar"""
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
    st.header("🏦 89/1-2-3 Haciz İhbar Analizi")
    st.caption("Context-Aware Bloke Tespiti | 40-Karakter Proximity")
    
    if not st.session_state.master_files:
        st.info("👈 Lütfen sol menüden dosya yükleyin.")
        st.stop()
    
    if not BANKA_OK:
        st.error("Haciz İhbar Analyzer modülü yüklenemedi!")
        st.stop()
    
    col1, col2 = st.columns([3, 1])
    with col1:
        st.caption(f"📁 {len(st.session_state.master_files)} dosya analiz edilecek")
    with col2:
        analyze_btn = st.button("🔍 Analiz Et", type="primary", use_container_width=True)
    
    if analyze_btn:
        with st.spinner("Context-aware analiz yapılıyor..."):
            paths, tdir = save_temp_files()
            try:
                analyzer = HacizIhbarAnalyzer()
                res = analyzer.batch_analiz(paths)
                st.session_state.banka_sonuc = res
            except Exception as e:
                st.error(f"Analiz hatası: {e}")
            finally:
                if tdir:
                    shutil.rmtree(tdir, ignore_errors=True)
        st.rerun()
    
    if st.session_state.banka_sonuc:
        res = st.session_state.banka_sonuc
        
        # Metrikler (DOĞRU ATTRIBUTE İSİMLERİ)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Toplam Muhatap", res.toplam_muhatap)
        c2.metric("🏦 Banka", res.banka_sayisi)
        c3.metric("🏢 Şirket", res.tuzel_kisi_sayisi)
        c4.metric("👤 Kişi", res.gercek_kisi_sayisi)
        
        # Büyük bloke göstergesi
        if res.toplam_bloke > 0:
            st.markdown(f"""
            <div class="bloke-box">
                <h2>💰 {res.toplam_bloke:,.2f} TL</h2>
                <p>Toplam Bloke Edilen Tutar</p>
            </div>
            """, unsafe_allow_html=True)
        
        st.divider()
        
        # Tabs
        tab1, tab2, tab3 = st.tabs(["📊 Detaylar", "📋 Tablo", "📥 İndir"])
        
        with tab1:
            for c in res.cevaplar:
                # DOĞRU ATTRIBUTE İSİMLERİ
                if c.cevap_durumu == CevapDurumu.BLOKE_VAR:
                    icon = "✅"
                elif c.cevap_durumu == CevapDurumu.HESAP_YOK:
                    icon = "❌"
                else:
                    icon = "ℹ️"
                
                with st.expander(f"{icon} {c.muhatap_adi} - {c.cevap_durumu.value}"):
                    st.write(f"**Tür:** {c.muhatap_turu.value}")
                    st.write(f"**Bloke:** {c.bloke_tutari:,.2f} TL")
                    st.write(f"**Öneri:** {c.sonraki_adim}")
                    if c.aciklama:
                        st.caption(c.aciklama[:300])
        
        with tab2:
            if PANDAS_OK:
                df = pd.DataFrame([{
                    'Muhatap': c.muhatap_adi,
                    'Tür': c.muhatap_turu.value,
                    'Durum': c.cevap_durumu.value,
                    'Bloke (TL)': f"{c.bloke_tutari:,.2f}",
                    'Aksiyon': c.sonraki_adim
                } for c in res.cevaplar])
                st.dataframe(df, use_container_width=True, hide_index=True)
            else:
                st.warning("pandas yüklü değil")
        
        with tab3:
            col1, col2 = st.columns(2)
            with col1:
                st.download_button(
                    "📄 Rapor İndir (TXT)",
                    res.ozet_rapor,
                    f"Haciz_Rapor_{datetime.now().strftime('%Y%m%d_%H%M')}.txt",
                    "text/plain",
                    use_container_width=True
                )
            
            with col2:
                if PANDAS_OK:
                    import io
                    excel_buffer = io.BytesIO()
                    df = pd.DataFrame([{
                        'Muhatap': c.muhatap_adi,
                        'Tür': c.muhatap_turu.value,
                        'Durum': c.cevap_durumu.value,
                        'Bloke': c.bloke_tutari,
                        'Alacak': c.alacak_tutari,
                        'Aksiyon': c.sonraki_adim
                    } for c in res.cevaplar])
                    with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                        df.to_excel(writer, index=False, sheet_name='Analiz')
                    
                    st.download_button(
                        "📊 Excel İndir",
                        excel_buffer.getvalue(),
                        f"Haciz_Rapor_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True
                    )

# ============================================================================
# MODÜL 2: PDF ÜRETİCİ
# ============================================================================
elif modul == "📄 PDF Üretici":
    st.header("📄 Profesyonel PDF Üretici")
    
    if not st.session_state.master_files:
        st.info("👈 Lütfen sol menüden dosya yükleyin.")
        st.stop()
    
    if not PDF_OK:
        st.error("ReportLab/PyPDF2 kütüphanesi eksik!")
        st.code("pip install reportlab PyPDF2")
        st.stop()
    
    baslik = st.text_input("PDF Başlığı", "İcra Dosyası")
    
    if st.button("🔄 PDF Üret", type="primary", use_container_width=True):
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
                else:
                    st.error("PDF oluşturulamadı!")
            except Exception as e:
                st.error(f"Hata: {e}")
            finally:
                if tdir:
                    shutil.rmtree(tdir, ignore_errors=True)
        st.rerun()
    
    if st.session_state.pdf_rapor:
        r = st.session_state.pdf_rapor["info"]
        
        st.success("✅ PDF başarıyla oluşturuldu!")
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Sayfa", r.toplam_sayfa)
        col2.metric("İşlenen Dosya", r.islenen_dosya)
        col3.metric("Süre", f"{getattr(r, 'sure_saniye', 0):.1f}s")
        
        st.download_button(
            "📥 PDF İNDİR",
            st.session_state.pdf_rapor["data"],
            f"{baslik.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.pdf",
            "application/pdf",
            type="primary",
            use_container_width=True
        )

# ============================================================================
# MODÜL 3: UYAP DOSYA ANALİZİ
# ============================================================================
elif modul == "📁 UYAP Analizi":
    st.header("📁 UYAP Dosya Analizi")
    st.caption("İİK 106/110 Süre Hesaplaması | Evrak Sınıflandırma")
    
    if not st.session_state.master_files:
        st.info("👈 Lütfen sol menüden dosya yükleyin.")
        st.stop()
    
    if not UYAP_OK:
        st.error("UYAP Analyzer modülü yüklenemedi!")
        st.stop()
    
    if st.button("🔍 Taramayı Başlat", type="primary", use_container_width=True):
        with st.spinner("Dosyalar taranıyor..."):
            paths, tdir = save_temp_files()
            try:
                zip_files = [p for p in paths if p.endswith('.zip')]
                target = zip_files[0] if zip_files else paths[0]
                
                analyzer = UYAPDosyaAnalyzer()
                res = analyzer.analiz_et(target)
                st.session_state.uyap_sonuc = res
            except Exception as e:
                st.error(f"Analiz hatası: {e}")
            finally:
                if tdir:
                    shutil.rmtree(tdir, ignore_errors=True)
        st.rerun()
    
    if st.session_state.uyap_sonuc:
        res = st.session_state.uyap_sonuc
        
        # Metrikler
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Toplam Evrak", res.toplam_evrak)
        col2.metric("Tebligat", len(res.tebligatlar))
        col3.metric("Haciz", len(res.hacizler))
        col4.metric("Aksiyon", len(res.aksiyonlar))
        
        st.divider()
        
        # Tabs
        tab1, tab2, tab3, tab4 = st.tabs(["⚡ Aksiyonlar", "🔒 Haciz Süreleri", "📊 Dağılım", "📄 Rapor"])
        
        with tab1:
            if res.aksiyonlar:
                for a in res.aksiyonlar:
                    if a.oncelik == IslemDurumu.KRITIK:
                        st.markdown(f"""
                        <div class="kritik-box">
                            <strong>🔴 {a.baslik}</strong><br/>
                            {a.aciklama}
                        </div>
                        """, unsafe_allow_html=True)
                    elif a.oncelik == IslemDurumu.UYARI:
                        st.warning(f"⚠️ **{a.baslik}**: {a.aciklama}")
                    else:
                        st.info(f"ℹ️ **{a.baslik}**: {a.aciklama}")
            else:
                st.success("✅ Acil aksiyon gerektiren durum yok.")
        
        with tab2:
            if res.hacizler:
                for h in res.hacizler:
                    risk_color = {
                        RiskSeviyesi.DUSMUS: "🔴",
                        RiskSeviyesi.KRITIK: "🔴",
                        RiskSeviyesi.YUKSEK: "🟠",
                        RiskSeviyesi.ORTA: "🟡",
                        RiskSeviyesi.DUSUK: "🟢",
                        RiskSeviyesi.GUVENLI: "✅",
                    }.get(h.risk, "❓")
                    
                    kalan = f"{h.kalan_gun} gün" if h.kalan_gun and h.kalan_gun < 9999 else "Süresiz"
                    st.write(f"{risk_color} **{h.tur.value}**: {kalan} - {h.risk.value if h.risk else 'Belirsiz'}")
            else:
                st.info("Haciz kaydı bulunamadı.")
        
        with tab3:
            if res.evrak_dagilimi:
                if PANDAS_OK:
                    df = pd.DataFrame([
                        {'Evrak Türü': k, 'Adet': v}
                        for k, v in sorted(res.evrak_dagilimi.items(), key=lambda x: -x[1])
                    ])
                    st.bar_chart(df.set_index('Evrak Türü'))
                else:
                    for k, v in sorted(res.evrak_dagilimi.items(), key=lambda x: -x[1]):
                        st.write(f"**{k}**: {v}")
            else:
                st.info("Evrak dağılımı hesaplanamadı.")
        
        with tab4:
            st.text(res.ozet_rapor)
            st.download_button(
                "📥 Rapor İndir",
                res.ozet_rapor,
                f"UYAP_Analiz_{datetime.now().strftime('%Y%m%d_%H%M')}.txt",
                "text/plain",
                use_container_width=True
            )

# === FOOTER ===
st.divider()
st.caption("⚖️ İcra Analiz Pro v12.5 | Context-Aware Edition | Arda & Claude | 2026")
