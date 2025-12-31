#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
İCRA DOSYA ANALİZ SİSTEMİ - Web Arayüzü v3.0
============================================
1. İcra Dosya Analizi (UYAP ZIP)
2. Banka Cevapları Analizi (89/1-2-3)
"""

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import io
import os
import sys
import tempfile

# Modülleri import et
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from icra_analiz_v2 import (
        IcraDosyaAnaliz, DosyaAnalizSonucu, TakipTuru, TebligatDurumu,
        HacizTuru, MulkiyetTipi, EvrakKategorisi, TasinmazAsama
    )
    ICRA_ANALIZ_AVAILABLE = True
except ImportError:
    ICRA_ANALIZ_AVAILABLE = False

try:
    from banka_cevap_analyzer import (
        BankaCevapAnalyzer, BankaAnalizSonucu, CevapDurumu, IhbarTuru
    )
    BANKA_ANALYZER_AVAILABLE = True
except ImportError:
    BANKA_ANALYZER_AVAILABLE = False

# Sayfa ayarları
st.set_page_config(
    page_title="İcra Dosya Analiz Sistemi",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.2rem;
        font-weight: bold;
        color: #1E3A5F;
        text-align: center;
        padding: 1rem;
    }
    .kritik-box {
        background-color: #ffebee;
        border-left: 5px solid #f44336;
        padding: 1rem;
        margin: 0.5rem 0;
        border-radius: 0 5px 5px 0;
    }
    .uyari-box {
        background-color: #fff3e0;
        border-left: 5px solid #ff9800;
        padding: 1rem;
        margin: 0.5rem 0;
        border-radius: 0 5px 5px 0;
    }
    .basari-box {
        background-color: #e8f5e9;
        border-left: 5px solid #4caf50;
        padding: 1rem;
        margin: 0.5rem 0;
        border-radius: 0 5px 5px 0;
    }
    .bilgi-box {
        background-color: #e3f2fd;
        border-left: 5px solid #2196f3;
        padding: 1rem;
        margin: 0.5rem 0;
        border-radius: 0 5px 5px 0;
    }
    .bloke-box {
        background-color: #e8f5e9;
        border-left: 5px solid #4caf50;
        padding: 1rem;
        margin: 0.5rem 0;
        border-radius: 0 5px 5px 0;
        font-size: 1.1rem;
    }
</style>
""", unsafe_allow_html=True)


# ============================================================================
# BANKA CEVAPLARI SAYFASI
# ============================================================================

def banka_cevaplari_sayfasi():
    """Banka Cevapları Analiz Sayfası"""
    
    st.markdown('<div class="main-header">🏦 Banka Cevapları Analizi</div>', unsafe_allow_html=True)
    st.markdown('<p style="text-align: center; color: #666;">89/1, 89/2, 89/3 Haciz İhbarnamelerine Gelen Cevaplar</p>', unsafe_allow_html=True)
    
    if not BANKA_ANALYZER_AVAILABLE:
        st.error("⚠️ Banka Cevap Analyzer modülü yüklenemedi.")
        return
    
    # Session state
    if 'banka_sonuc' not in st.session_state:
        st.session_state.banka_sonuc = None
    
    # Sidebar
    with st.sidebar:
        st.header("📁 Banka Cevapları Yükle")
        
        uploaded_file = st.file_uploader(
            "ZIP dosyası yükleyin",
            type=['zip'],
            help="Banka cevap dosyalarını içeren ZIP",
            key="banka_uploader"
        )
        
        if uploaded_file:
            st.success(f"✅ {uploaded_file.name}")
            
            if st.button("🔍 Analiz Et", type="primary", key="banka_analyze"):
                with st.spinner("Banka cevapları analiz ediliyor..."):
                    try:
                        temp_path = os.path.join(tempfile.gettempdir(), uploaded_file.name)
                        with open(temp_path, 'wb') as f:
                            f.write(uploaded_file.getvalue())
                        
                        analyzer = BankaCevapAnalyzer()
                        sonuc = analyzer.arsiv_analiz(temp_path)
                        st.session_state.banka_sonuc = sonuc
                        
                        os.remove(temp_path)
                    except Exception as e:
                        st.error(f"Hata: {str(e)}")
                
                st.rerun()
        
        st.divider()
        
        st.info("""
        **89/1-2-3 Kuralları:**
        - 89/1 cevap yok → 89/2 gönder
        - 89/2 cevap yok → 89/3 gönder
        - Banka hacizlerinde 106/110 YOK
        
        **Cevap Türleri:**
        - 💰 Bloke var
        - 📋 Hesap var, bakiye yok
        - ❌ Hesap yok
        """)
    
    # Ana içerik
    if st.session_state.banka_sonuc:
        sonuc = st.session_state.banka_sonuc
        
        # Üst kartlar
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("🏦 Toplam Banka", sonuc.toplam_banka)
        with col2:
            st.metric("📬 Cevap Gelen", sonuc.cevap_gelen)
        with col3:
            bloke_sayisi = len([c for c in sonuc.cevaplar if c.cevap_durumu == CevapDurumu.BLOKE_VAR])
            st.metric("💰 Bloke Var", bloke_sayisi)
        with col4:
            st.metric("💵 Toplam Bloke", f"{sonuc.toplam_bloke:,.2f} TL")
        
        st.divider()
        
        # Sekmeler
        tab1, tab2, tab3, tab4 = st.tabs([
            "💰 Bloke Özeti",
            "📤 Gönderilecek İhbarlar",
            "📋 Banka Detayları",
            "📥 Rapor İndir"
        ])
        
        # TAB 1: BLOKE ÖZETİ
        with tab1:
            st.subheader("💰 Bloke Edilen Tutarlar")
            
            # Toplam bloke - büyük göster
            if sonuc.toplam_bloke > 0:
                st.markdown(f"""
                <div class="bloke-box">
                    <h2 style="color: #2e7d32; margin: 0;">💰 TOPLAM BLOKE: {sonuc.toplam_bloke:,.2f} TL</h2>
                </div>
                """, unsafe_allow_html=True)
            
            # Bloke olan bankalar
            bloke_olanlar = [c for c in sonuc.cevaplar if c.cevap_durumu == CevapDurumu.BLOKE_VAR]
            
            if bloke_olanlar:
                st.markdown("### ✅ Bloke Olan Bankalar")
                
                for c in bloke_olanlar:
                    st.markdown(f"""
                    <div class="basari-box">
                        <strong>🏦 {c.banka_adi}</strong><br>
                        💰 Bloke: <strong>{c.bloke_tutari:,.2f} TL</strong><br>
                        <small>{c.ihbar_turu.value} | {c.cevap_tarihi.strftime('%d.%m.%Y') if c.cevap_tarihi else ''}</small>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.warning("Henüz bloke edilen tutar yok")
            
            # Hesap yok
            st.markdown("### ❌ Hesap Bulunamayan Bankalar")
            hesap_yok = [c for c in sonuc.cevaplar if c.cevap_durumu == CevapDurumu.HESAP_YOK]
            
            if hesap_yok:
                for c in hesap_yok:
                    st.markdown(f"• {c.banka_adi}: Hesap kaydı yok")
            else:
                st.info("Tüm bankalarda hesap mevcut veya cevap bekleniyor")
        
        # TAB 2: GÖNDERİLECEK İHBARLAR
        with tab2:
            st.subheader("📤 Gönderilmesi Gereken İhbarlar")
            
            if sonuc.eksik_ihbarlar:
                st.error(f"⚠️ {len(sonuc.eksik_ihbarlar)} bankaya ek ihbar gönderilmeli!")
                
                for e in sonuc.eksik_ihbarlar:
                    st.markdown(f"""
                    <div class="kritik-box">
                        <strong>🏦 {e['banka']}</strong><br>
                        📤 <strong>{e['gonderilecek']} GÖNDER!</strong><br>
                        <small>Neden: {e['neden']}</small>
                    </div>
                    """, unsafe_allow_html=True)
                
                # Özet tablo
                st.markdown("### 📋 Özet Tablo")
                df_eksik = pd.DataFrame(sonuc.eksik_ihbarlar)
                st.dataframe(df_eksik, use_container_width=True)
            else:
                st.markdown('<div class="basari-box">✅ Tüm ihbarlar tamamlanmış - Ek ihbar gerekmiyor</div>', unsafe_allow_html=True)
        
        # TAB 3: BANKA DETAYLARI
        with tab3:
            st.subheader("📋 Banka Banka Detay")
            
            # Cevap tablosu
            cevap_data = []
            for c in sonuc.cevaplar:
                cevap_data.append({
                    'Banka': c.banka_adi,
                    'İhbar': c.ihbar_turu.value.split('-')[0].strip(),
                    'Durum': c.cevap_durumu.value,
                    'Bloke': f"{c.bloke_tutari:,.2f} TL" if c.bloke_tutari else "-",
                    'Tarih': c.cevap_tarihi.strftime('%d.%m.%Y') if c.cevap_tarihi else '-',
                    'Sonraki Adım': c.sonraki_adim[:50] + "..." if len(c.sonraki_adim) > 50 else c.sonraki_adim
                })
            
            if cevap_data:
                df = pd.DataFrame(cevap_data)
                st.dataframe(df, use_container_width=True, height=400)
            
            # Her banka için expander
            st.markdown("### 🔍 Detaylı İnceleme")
            
            for c in sonuc.cevaplar:
                durum_emoji = "💰" if c.cevap_durumu == CevapDurumu.BLOKE_VAR else "❌" if c.cevap_durumu == CevapDurumu.HESAP_YOK else "📋"
                
                with st.expander(f"{durum_emoji} {c.banka_adi} - {c.ihbar_turu.value.split('-')[0]}"):
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.write(f"**Banka:** {c.banka_adi}")
                        st.write(f"**İhbar Türü:** {c.ihbar_turu.value}")
                        st.write(f"**Durum:** {c.cevap_durumu.value}")
                        if c.cevap_tarihi:
                            st.write(f"**Tarih:** {c.cevap_tarihi.strftime('%d.%m.%Y')}")
                    
                    with col2:
                        if c.bloke_tutari:
                            st.success(f"💰 **Bloke:** {c.bloke_tutari:,.2f} TL")
                        st.write(f"**Hesap Sayısı:** {c.hesap_sayisi}")
                        if c.iban_listesi:
                            st.write(f"**IBAN:** {', '.join(c.iban_listesi[:3])}")
                    
                    st.write(f"**Sonraki Adım:** {c.sonraki_adim}")
                    st.write(f"**Dosya:** {c.dosya_adi}")
        
        # TAB 4: RAPOR İNDİR
        with tab4:
            st.subheader("📥 Rapor İndir")
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.download_button(
                    label="📄 Özet Rapor (TXT)",
                    data=sonuc.ozet_rapor,
                    file_name=f"banka_cevap_raporu_{datetime.now().strftime('%Y%m%d_%H%M')}.txt",
                    mime="text/plain"
                )
            
            with col2:
                # Excel
                if st.button("📊 Excel Oluştur"):
                    cevap_data = [{
                        'Banka': c.banka_adi,
                        'İhbar Türü': c.ihbar_turu.value,
                        'Durum': c.cevap_durumu.value,
                        'Bloke Tutarı': c.bloke_tutari or 0,
                        'Cevap Tarihi': c.cevap_tarihi.strftime('%d.%m.%Y') if c.cevap_tarihi else '',
                        'Hesap Sayısı': c.hesap_sayisi,
                        'Sonraki Adım': c.sonraki_adim,
                        'Dosya': c.dosya_adi
                    } for c in sonuc.cevaplar]
                    
                    buffer = io.BytesIO()
                    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                        pd.DataFrame(cevap_data).to_excel(writer, sheet_name='Banka Cevapları', index=False)
                        
                        if sonuc.eksik_ihbarlar:
                            pd.DataFrame(sonuc.eksik_ihbarlar).to_excel(writer, sheet_name='Gönderilecek İhbarlar', index=False)
                    
                    st.download_button(
                        label="⬇️ Excel İndir",
                        data=buffer.getvalue(),
                        file_name=f"banka_cevaplari_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
            
            # Tam rapor göster
            st.markdown("### 📋 Tam Rapor")
            st.code(sonuc.ozet_rapor, language=None)
    
    else:
        # Başlangıç ekranı
        st.markdown("""
        <div style="text-align: center; padding: 3rem;">
            <h2>📦 Banka Cevapları ZIP Yükleyin</h2>
            <p>Sol menüden banka cevap dosyalarını içeren ZIP yükleyin.</p>
            <br>
            <h4>🔍 Ne Analiz Edilir?</h4>
        </div>
        """, unsafe_allow_html=True)
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.markdown("""
            **💰 Bloke Tespiti**
            - Her bankadan bloke tutarı
            - Toplam bloke hesaplama
            - IBAN numaraları
            """)
        
        with col2:
            st.markdown("""
            **📤 89/2-3 Önerisi**
            - Cevap yoksa → 89/2 gönder
            - 89/2 olumsuz → 89/3 gönder
            - Otomatik aksiyon önerisi
            """)
        
        with col3:
            st.markdown("""
            **📊 Detaylı Rapor**
            - Banka banka özet
            - Excel export
            - Yazdırılabilir rapor
            """)


# ============================================================================
# İCRA DOSYA ANALİZ SAYFASI
# ============================================================================

def icra_dosya_sayfasi():
    """İcra Dosya Analiz Sayfası"""
    
    st.markdown('<div class="main-header">⚖️ İcra Dosya Analizi</div>', unsafe_allow_html=True)
    st.markdown('<p style="text-align: center; color: #666;">UYAP ZIP Dosyasından Kapsamlı Hukuki Analiz</p>', unsafe_allow_html=True)
    
    if not ICRA_ANALIZ_AVAILABLE:
        st.error("⚠️ İcra Analiz modülü yüklenemedi.")
        return
    
    if 'analiz_sonucu' not in st.session_state:
        st.session_state.analiz_sonucu = None
    
    with st.sidebar:
        st.header("📁 UYAP Dosyası Yükle")
        
        uploaded_file = st.file_uploader(
            "ZIP dosyası yükleyin",
            type=['zip'],
            help="UYAP'tan indirilen evrak arşivi",
            key="icra_uploader"
        )
        
        if uploaded_file:
            st.success(f"✅ {uploaded_file.name}")
            
            if st.button("🔍 Analiz Et", type="primary", key="icra_analyze"):
                with st.spinner("Dosya analiz ediliyor..."):
                    try:
                        temp_path = os.path.join(tempfile.gettempdir(), uploaded_file.name)
                        with open(temp_path, 'wb') as f:
                            f.write(uploaded_file.getvalue())
                        
                        analizci = IcraDosyaAnaliz()
                        sonuc = analizci.dosya_analiz_et(temp_path)
                        st.session_state.analiz_sonucu = sonuc
                        st.session_state.icra_rapor = analizci.rapor_olustur(sonuc)
                        
                        os.remove(temp_path)
                    except Exception as e:
                        st.error(f"Hata: {str(e)}")
                
                st.rerun()
        
        st.divider()
        
        st.info("""
        **Analiz Kapsamı:**
        - 📬 Tebligat (Bila/21/35)
        - ⚖️ İtiraz süresi
        - 💼 Tüm hacizler
        - 🏠 Taşınmaz detayları
        - 📊 106/110 süre takibi
        
        **Not:** 89/1'de 106/110 YOK
        """)
    
    if st.session_state.analiz_sonucu:
        sonuc = st.session_state.analiz_sonucu
        
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("📁 Dosya No", sonuc.dosya_no or "?")
        col2.metric("📋 Takip", sonuc.takip_turu.value.split('(')[0])
        col3.metric("Kesinleşme", "✅ Evet" if sonuc.kesinlesti_mi else "⏳ Hayır")
        col4.metric("📄 Evrak", len(sonuc.evraklar))
        
        st.divider()
        
        tab1, tab2, tab3, tab4 = st.tabs(["🚨 Uyarılar", "💼 Hacizler", "📊 Rapor", "📥 İndir"])
        
        with tab1:
            st.subheader("🚨 Kritik Uyarılar")
            if sonuc.kritik_uyarilar:
                for u in sonuc.kritik_uyarilar:
                    if "❌" in u or "DÜŞMÜŞ" in u:
                        st.markdown(f'<div class="kritik-box">{u}</div>', unsafe_allow_html=True)
                    elif "🔴" in u or "⚠️" in u:
                        st.markdown(f'<div class="uyari-box">{u}</div>', unsafe_allow_html=True)
                    else:
                        st.markdown(f'<div class="bilgi-box">{u}</div>', unsafe_allow_html=True)
            else:
                st.markdown('<div class="basari-box">✅ Kritik uyarı yok</div>', unsafe_allow_html=True)
            
            if sonuc.oneriler:
                st.subheader("💡 Öneriler")
                for o in sonuc.oneriler:
                    st.markdown(f'<div class="bilgi-box">{o}</div>', unsafe_allow_html=True)
        
        with tab2:
            st.subheader("💼 Haciz Özeti")
            
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("🏦 Banka", len(sonuc.banka_hacizleri))
            col2.metric("🚗 Araç", len(sonuc.arac_hacizleri))
            col3.metric("🏠 Taşınmaz", len(sonuc.tasinmaz_hacizleri))
            col4.metric("📦 Menkul", len(sonuc.menkul_hacizleri))
            
            if sonuc.banka_hacizleri:
                st.markdown("### 🏦 Banka Hacizleri")
                st.info("ℹ️ Banka hacizlerinde 106/110 süre takibi YOKTUR")
                for h in sonuc.banka_hacizleri:
                    st.write(f"• {h.hedef}: {h.haciz_turu.value}")
            
            if sonuc.arac_hacizleri:
                st.markdown("### 🚗 Araç Hacizleri (106/110)")
                for h in sonuc.arac_hacizleri:
                    durum = f"🔴 {h.kalan_gun} gün" if h.kalan_gun and h.kalan_gun <= 30 else f"🟢 {h.kalan_gun} gün" if h.kalan_gun else "-"
                    st.write(f"• {h.hedef}: {durum}")
        
        with tab3:
            st.subheader("📊 Detaylı Rapor")
            if 'icra_rapor' in st.session_state:
                st.code(st.session_state.icra_rapor, language=None)
        
        with tab4:
            st.subheader("📥 Rapor İndir")
            if 'icra_rapor' in st.session_state:
                st.download_button(
                    label="📄 Rapor İndir (TXT)",
                    data=st.session_state.icra_rapor,
                    file_name=f"icra_analiz_{datetime.now().strftime('%Y%m%d_%H%M')}.txt",
                    mime="text/plain"
                )
    
    else:
        st.markdown("""
        <div style="text-align: center; padding: 3rem;">
            <h2>📦 UYAP ZIP Dosyası Yükleyin</h2>
            <p>Sol menüden dosya yükleyerek analiz başlatın.</p>
        </div>
        """, unsafe_allow_html=True)


# ============================================================================
# ANA UYGULAMA
# ============================================================================

def main():
    """Ana uygulama"""
    
    st.sidebar.title("⚖️ İcra Analiz Sistemi")
    st.sidebar.markdown("---")
    
    # Modül seçimi
    modul = st.sidebar.radio(
        "📌 Modül Seçin",
        ["🏦 Banka Cevapları", "📁 İcra Dosya Analizi"],
        index=0
    )
    
    st.sidebar.markdown("---")
    
    if modul == "🏦 Banka Cevapları":
        banka_cevaplari_sayfasi()
    else:
        icra_dosya_sayfasi()
    
    # Footer
    st.markdown("""
    <div style="text-align: center; color: #666; padding: 2rem; margin-top: 3rem;">
        <hr>
        <p>⚖️ <strong>İcra Dosya Analiz Sistemi</strong> v3.0 | 
        İİK 89, 106/110 | © 2024-2025</p>
    </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    main()
