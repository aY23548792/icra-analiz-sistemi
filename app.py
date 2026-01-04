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
    from haciz_ihbar_analyzer import (
        HacizIhbarAnalyzer, HacizIhbarAnalizSonucu, HacizIhbarCevabi,
        CevapDurumu, IhbarTuru, MuhatapTuru,
        # Geriye uyumluluk
        BankaCevapAnalyzer, BankaAnalizSonucu
    )
    BANKA_ANALYZER_AVAILABLE = True
except ImportError as e:
    BANKA_ANALYZER_AVAILABLE = False
    print(f"Haciz İhbar import hatası: {e}")

try:
    from neat_pdf_uretici import NeatPDFUretici, NeatPDFRapor, REPORTLAB_OK
    NEAT_PDF_AVAILABLE = REPORTLAB_OK  # reportlab yoksa modül çalışmaz
except ImportError as e:
    NEAT_PDF_AVAILABLE = False
    print(f"Neat PDF import hatası: {e}")

try:
    from uyap_dosya_analyzer import UYAPDosyaAnalyzer, DosyaAnalizSonucu as UYAPAnalizSonucu, IslemDurumu
    UYAP_ANALYZER_AVAILABLE = True
except ImportError as e:
    UYAP_ANALYZER_AVAILABLE = False
    print(f"UYAP Analyzer import hatası: {e}")

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
    """89/1-2-3 Haciz İhbar Analiz Sayfası (Banka + 3. Şahıs)"""
    
    st.markdown('<div class="main-header">🏦 89/1-2-3 Haciz İhbar Analizi</div>', unsafe_allow_html=True)
    st.markdown('<p style="text-align: center; color: #666;">Banka + 3. Şahıs (Tüzel/Gerçek Kişi) Cevapları</p>', unsafe_allow_html=True)
    
    if not BANKA_ANALYZER_AVAILABLE:
        st.error("⚠️ Haciz İhbar Analyzer modülü yüklenemedi.")
        return
    
    # Session state
    if 'ihbar_sonuc' not in st.session_state:
        st.session_state.ihbar_sonuc = None
    
    # Sidebar
    with st.sidebar:
        st.header("📁 Dosya Yükle")
        st.info("💡 **Batch Yükleme:** Birden fazla dosya seçebilirsiniz!")
        
        # BATCH UPLOAD
        uploaded_files = st.file_uploader(
            "ZIP dosyaları yükleyin",
            type=['zip', 'pdf'],
            accept_multiple_files=True,  # BATCH!
            help="Birden fazla ZIP veya PDF dosyası seçebilirsiniz",
            key="ihbar_uploader"
        )
        
        if uploaded_files:
            st.success(f"✅ {len(uploaded_files)} dosya seçildi")
            for f in uploaded_files:
                st.write(f"  • {f.name}")
            
            if st.button("🔍 Analiz Et", type="primary", key="ihbar_analyze"):
                with st.spinner("Dosyalar analiz ediliyor..."):
                    try:
                        # Tüm dosyaları temp'e kaydet
                        temp_paths = []
                        for f in uploaded_files:
                            temp_path = os.path.join(tempfile.gettempdir(), f.name)
                            with open(temp_path, 'wb') as out:
                                out.write(f.getvalue())
                            temp_paths.append(temp_path)
                        
                        # Batch analiz
                        analyzer = HacizIhbarAnalyzer()
                        sonuc = analyzer.batch_analiz(temp_paths)
                        st.session_state.ihbar_sonuc = sonuc
                        
                        # Temizlik
                        for p in temp_paths:
                            if os.path.exists(p):
                                os.remove(p)
                    except Exception as e:
                        st.error(f"Hata: {str(e)}")
                
                st.rerun()
        
        st.divider()
        
        st.info("""
        **Desteklenen Muhataplar:**
        - 🏦 Bankalar (tüm Türkiye bankaları)
        - 🏢 Tüzel Kişiler (şirketler)
        - 👤 Gerçek Kişiler (3. şahıs)
        - 🏛️ Kamu Kurumları
        
        **89/1-2-3 Kuralları:**
        - Cevap olumsuz → 89/2 gönder
        - 89/2 olumsuz → 89/3 gönder
        """)
    
    # Ana içerik
    if st.session_state.ihbar_sonuc:
        sonuc = st.session_state.ihbar_sonuc
        
        # Üst kartlar
        col1, col2, col3, col4, col5 = st.columns(5)
        
        with col1:
            st.metric("📋 Toplam Muhatap", sonuc.toplam_muhatap)
        with col2:
            st.metric("🏦 Banka", sonuc.banka_sayisi)
        with col3:
            st.metric("🏢 Tüzel Kişi", sonuc.tuzel_kisi_sayisi)
        with col4:
            st.metric("👤 Gerçek Kişi", sonuc.gercek_kisi_sayisi)
        with col5:
            st.metric("💰 Toplam Bloke", f"{sonuc.toplam_bloke:,.0f} ₺")
        
        # İkinci satır metrikler
        if sonuc.toplam_alacak > 0 or sonuc.toplam_odenen > 0:
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("💵 3. Şahıs Alacak", f"{sonuc.toplam_alacak:,.0f} ₺")
            with col2:
                st.metric("✅ Ödenen", f"{sonuc.toplam_odenen:,.0f} ₺")
            with col3:
                st.metric("📤 Eksik İhbar", len(sonuc.eksik_ihbarlar))
        
        st.divider()
        
        # Yüklenen dosyalar
        if sonuc.yuklenen_dosyalar:
            with st.expander(f"📂 Yüklenen Dosyalar ({len(sonuc.yuklenen_dosyalar)})"):
                for d in sonuc.yuklenen_dosyalar:
                    st.write(f"• {d}")
        
        # Sekmeler
        tab1, tab2, tab3, tab4, tab5 = st.tabs([
            "💰 Bloke/Alacak",
            "📤 Gönderilecek İhbarlar",
            "🏦 Bankalar",
            "🏢 3. Şahıslar",
            "📥 İndir"
        ])
        
        # TAB 1: BLOKE/ALACAK ÖZETİ
        with tab1:
            st.subheader("💰 Bloke ve Alacak Özeti")
            
            toplam = sonuc.toplam_bloke + sonuc.toplam_alacak
            if toplam > 0:
                st.markdown(f"""
                <div class="bloke-box">
                    <h2 style="color: #2e7d32; margin: 0;">
                        💰 TOPLAM TAHSİL EDİLEBİLİR: {toplam:,.2f} TL
                    </h2>
                    <p>Banka Bloke: {sonuc.toplam_bloke:,.2f} TL | 3. Şahıs Alacak: {sonuc.toplam_alacak:,.2f} TL</p>
                </div>
                """, unsafe_allow_html=True)
            
            # Bloke olanlar
            bloke_olanlar = [c for c in sonuc.cevaplar if c.cevap_durumu == CevapDurumu.BLOKE_VAR]
            alacak_olanlar = [c for c in sonuc.cevaplar if c.cevap_durumu == CevapDurumu.ALACAK_VAR]
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("### 🏦 Banka Blokeleri")
                if bloke_olanlar:
                    for c in bloke_olanlar:
                        st.markdown(f"""
                        <div class="basari-box">
                            <strong>{c.muhatap_turu.value} {c.muhatap_adi}</strong><br>
                            💰 <strong>{c.bloke_tutari:,.2f} TL</strong>
                        </div>
                        """, unsafe_allow_html=True)
                else:
                    st.info("Bloke yok")
            
            with col2:
                st.markdown("### 🏢 3. Şahıs Alacakları")
                if alacak_olanlar:
                    for c in alacak_olanlar:
                        tutar_str = f"{c.alacak_tutari:,.2f} TL" if c.alacak_tutari else "Tutar belirtilmemiş"
                        st.markdown(f"""
                        <div class="basari-box">
                            <strong>{c.muhatap_turu.value} {c.muhatap_adi}</strong><br>
                            💵 <strong>{tutar_str}</strong>
                        </div>
                        """, unsafe_allow_html=True)
                else:
                    st.info("3. şahıs alacağı yok")
        
        # TAB 2: GÖNDERİLECEK İHBARLAR
        with tab2:
            st.subheader("📤 Gönderilmesi Gereken İhbarlar")
            
            if sonuc.eksik_ihbarlar:
                st.error(f"⚠️ {len(sonuc.eksik_ihbarlar)} muhataba ek ihbar gönderilmeli!")
                
                for e in sonuc.eksik_ihbarlar:
                    st.markdown(f"""
                    <div class="kritik-box">
                        <strong>{e.get('tur', '')} {e['muhatap']}</strong><br>
                        📤 <strong>{e['gonderilecek']} GÖNDER!</strong><br>
                        <small>Neden: {e['neden']}</small>
                    </div>
                    """, unsafe_allow_html=True)
                
                # Tablo
                df_eksik = pd.DataFrame(sonuc.eksik_ihbarlar)
                st.dataframe(df_eksik, use_container_width=True)
            else:
                st.markdown('<div class="basari-box">✅ Tüm ihbarlar tamamlanmış!</div>', unsafe_allow_html=True)
        
        # TAB 3: BANKALAR
        with tab3:
            st.subheader("🏦 Banka Cevapları")
            
            banka_cevaplari = [c for c in sonuc.cevaplar if c.muhatap_turu == MuhatapTuru.BANKA]
            
            if banka_cevaplari:
                for c in banka_cevaplari:
                    durum_renk = "basari" if c.cevap_durumu == CevapDurumu.BLOKE_VAR else "uyari" if c.cevap_durumu == CevapDurumu.HESAP_VAR_BAKIYE_YOK else "bilgi"
                    
                    with st.expander(f"🏦 {c.muhatap_adi} - {c.ihbar_turu.value.split('-')[0]}"):
                        col1, col2 = st.columns(2)
                        with col1:
                            st.write(f"**Banka:** {c.muhatap_adi}")
                            st.write(f"**İhbar:** {c.ihbar_turu.value}")
                            st.write(f"**Durum:** {c.cevap_durumu.value}")
                        with col2:
                            if c.bloke_tutari:
                                st.success(f"💰 **Bloke:** {c.bloke_tutari:,.2f} TL")
                            if c.iban_listesi:
                                st.write(f"**IBAN:** {c.iban_listesi[0] if c.iban_listesi else '-'}")
                        st.write(f"**Sonraki Adım:** {c.sonraki_adim}")
            else:
                st.info("Banka cevabı bulunamadı")
        
        # TAB 4: 3. ŞAHISLAR
        with tab4:
            st.subheader("🏢👤 3. Şahıs Cevapları")
            
            ucuncu_sahis = [c for c in sonuc.cevaplar if c.muhatap_turu in [MuhatapTuru.TUZEL_KISI, MuhatapTuru.GERCEK_KISI, MuhatapTuru.KAMU_KURUMU]]
            
            if ucuncu_sahis:
                for c in ucuncu_sahis:
                    emoji = "🏢" if c.muhatap_turu == MuhatapTuru.TUZEL_KISI else "👤" if c.muhatap_turu == MuhatapTuru.GERCEK_KISI else "🏛️"
                    
                    with st.expander(f"{emoji} {c.muhatap_adi}"):
                        col1, col2 = st.columns(2)
                        with col1:
                            st.write(f"**Muhatap:** {c.muhatap_adi}")
                            st.write(f"**Tür:** {c.muhatap_turu.value}")
                            st.write(f"**Durum:** {c.cevap_durumu.value}")
                            if c.vkn:
                                st.write(f"**VKN:** {c.vkn}")
                            if c.tckn:
                                st.write(f"**TCKN:** {c.tckn}")
                        with col2:
                            if c.alacak_tutari:
                                st.success(f"💵 **Alacak:** {c.alacak_tutari:,.2f} TL")
                            if c.odenen_tutar:
                                st.success(f"✅ **Ödenen:** {c.odenen_tutar:,.2f} TL")
                        st.write(f"**Sonraki Adım:** {c.sonraki_adim}")
            else:
                st.info("3. şahıs cevabı bulunamadı")
        
        # TAB 5: İNDİR
        with tab5:
            st.subheader("📥 Rapor İndir")
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.download_button(
                    label="📄 Özet Rapor (TXT)",
                    data=sonuc.ozet_rapor,
                    file_name=f"haciz_ihbar_raporu_{datetime.now().strftime('%Y%m%d_%H%M')}.txt",
                    mime="text/plain"
                )
            
            with col2:
                if st.button("📊 Excel Oluştur"):
                    cevap_data = [{
                        'Muhatap': c.muhatap_adi,
                        'Tür': c.muhatap_turu.value,
                        'İhbar': c.ihbar_turu.value,
                        'Durum': c.cevap_durumu.value,
                        'Bloke': c.bloke_tutari or 0,
                        'Alacak': c.alacak_tutari or 0,
                        'Ödenen': c.odenen_tutar or 0,
                        'Sonraki Adım': c.sonraki_adim,
                        'Kaynak': c.kaynak_zip
                    } for c in sonuc.cevaplar]
                    
                    buffer = io.BytesIO()
                    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                        pd.DataFrame(cevap_data).to_excel(writer, sheet_name='Tüm Cevaplar', index=False)
                        if sonuc.eksik_ihbarlar:
                            pd.DataFrame(sonuc.eksik_ihbarlar).to_excel(writer, sheet_name='Gönderilecek İhbarlar', index=False)
                    
                    st.download_button(
                        label="⬇️ Excel İndir",
                        data=buffer.getvalue(),
                        file_name=f"haciz_ihbar_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
            
            st.markdown("### 📋 Tam Rapor")
            st.code(sonuc.ozet_rapor, language=None)
    
    else:
        # Başlangıç ekranı
        st.markdown("""
        <div style="text-align: center; padding: 3rem;">
            <h2>📦 Dosyaları Yükleyin (Batch Destekli!)</h2>
            <p>Sol menüden birden fazla ZIP veya PDF dosyası seçebilirsiniz.</p>
        </div>
        """, unsafe_allow_html=True)
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.markdown("""
            **🏦 Banka Cevapları**
            - Tüm Türkiye bankaları
            - Bloke tutarı tespiti
            - IBAN çıkarma
            """)
        
        with col2:
            st.markdown("""
            **🏢 3. Şahıs Tüzel**
            - Şirket cevapları
            - Alacak tespiti
            - VKN çıkarma
            """)
        
        with col3:
            st.markdown("""
            **👤 3. Şahıs Gerçek**
            - Kişi cevapları
            - Borç/alacak tespiti
            - TCKN çıkarma
            """)


# ============================================================================
# İCRA DOSYA ANALİZ SAYFASI
# ============================================================================

def icra_dosya_sayfasi():
    """UYAP ZIP'ten Otomatik Dosya Analizi - YENİ VİZYON"""
    
    st.markdown('<div class="main-header">📁 UYAP Dosya Analizi</div>', unsafe_allow_html=True)
    st.markdown('<p style="text-align: center; color: #666;">UYAP ZIP yükleyin → Sistem otomatik analiz etsin → Excel + Rapor alsın</p>', unsafe_allow_html=True)
    
    if not UYAP_ANALYZER_AVAILABLE:
        st.error("⚠️ UYAP Dosya Analyzer modülü yüklenemedi.")
        return
    
    # Session state
    if 'uyap_sonuc' not in st.session_state:
        st.session_state.uyap_sonuc = None
    
    # Sidebar
    with st.sidebar:
        st.header("📁 UYAP Dosyası Yükle")
        st.info("💡 UYAP'tan indirdiğiniz ZIP'i doğrudan yükleyin!")
        
        uploaded_file = st.file_uploader(
            "ZIP dosyası yükleyin",
            type=['zip'],
            help="UYAP'tan indirilen evrak arşivi",
            key="uyap_uploader"
        )
        
        if uploaded_file:
            st.success(f"✅ {uploaded_file.name}")
            
            if st.button("🔍 Analiz Et", type="primary", key="uyap_analyze"):
                with st.spinner("Dosya analiz ediliyor..."):
                    try:
                        temp_path = os.path.join(tempfile.gettempdir(), uploaded_file.name)
                        with open(temp_path, 'wb') as f:
                            f.write(uploaded_file.getvalue())
                        
                        analyzer = UYAPDosyaAnalyzer()
                        sonuc = analyzer.analiz_et(temp_path)
                        st.session_state.uyap_sonuc = sonuc
                        
                        if os.path.exists(temp_path):
                            os.remove(temp_path)
                        
                    except Exception as e:
                        st.error(f"Hata: {str(e)}")
                
                st.rerun()
        
        st.divider()
        
        st.markdown("""
        **📥 GİRDİ:** Sadece UYAP ZIP
        
        **📤 ÇIKTI:**
        - 📊 Özet Excel
        - 📋 Analiz Raporu
        - ✅ Aksiyon Listesi
        
        **🔍 Analiz Edilen:**
        - Tebligat mazbataları
        - Haciz evrakları  
        - 89/1-2-3 ihbarları
        - Kıymet takdirleri
        - Satış ilanları
        """)
    
    # Ana içerik
    if st.session_state.uyap_sonuc:
        sonuc = st.session_state.uyap_sonuc
        
        # Üst kartlar
        col1, col2, col3, col4, col5 = st.columns(5)
        
        with col1:
            st.metric("📁 Toplam Evrak", sonuc.toplam_evrak)
        with col2:
            st.metric("📬 Tebligat", len(sonuc.tebligatlar))
        with col3:
            st.metric("🔒 Haciz", len(sonuc.hacizler))
        with col4:
            st.metric("💰 Bloke", f"{sonuc.toplam_bloke:,.0f} ₺")
        with col5:
            kritik = len([a for a in sonuc.aksiyonlar if a.oncelik == IslemDurumu.KRITIK])
            st.metric("🔴 Kritik", kritik)
        
        st.divider()
        
        # Tebligat durumu banner
        tebligat_emoji = "✅" if "Tebliğ Edildi" in sonuc.tebligat_durumu.value else "⚠️"
        box_class = "basari" if tebligat_emoji == "✅" else "uyari"
        st.markdown(f"""
        <div class="{box_class}-box">
            <strong>📬 Tebligat Durumu:</strong> {sonuc.tebligat_durumu.value}
        </div>
        """, unsafe_allow_html=True)
        
        # Sekmeler
        tab1, tab2, tab3, tab4, tab5 = st.tabs([
            "✅ Aksiyonlar",
            "📁 Evraklar", 
            "📬 Tebligatlar",
            "🔒 Hacizler",
            "📥 İndir"
        ])
        
        # TAB 1: AKSİYONLAR
        with tab1:
            st.subheader("✅ Yapılması Gerekenler")
            
            if sonuc.aksiyonlar:
                for a in sonuc.aksiyonlar:
                    if a.oncelik == IslemDurumu.KRITIK:
                        box_class = "kritik-box"
                    elif a.oncelik == IslemDurumu.UYARI:
                        box_class = "uyari-box"
                    elif a.oncelik == IslemDurumu.TAMAMLANDI:
                        box_class = "basari-box"
                    else:
                        box_class = "bilgi-box"
                    
                    tarih_str = f'<br><small>Son Tarih: {a.son_tarih.strftime("%d.%m.%Y")}</small>' if a.son_tarih else ''
                    st.markdown(f"""
                    <div class="{box_class}">
                        <strong>{a.oncelik.value} {a.baslik}</strong><br>
                        {a.aciklama}{tarih_str}
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.success("✅ Bekleyen aksiyon yok!")
        
        # TAB 2: EVRAKLAR
        with tab2:
            st.subheader("📁 Evrak Listesi")
            
            # Evrak dağılımı
            if sonuc.evrak_dagilimi:
                st.markdown("### 📊 Evrak Dağılımı")
                cols = st.columns(4)
                for i, (tur, sayi) in enumerate(sorted(sonuc.evrak_dagilimi.items(), key=lambda x: -x[1])[:8]):
                    with cols[i % 4]:
                        st.metric(tur[:20], sayi)
            
            # Evrak tablosu
            if sonuc.evraklar:
                evrak_data = [{
                    'Dosya': e.dosya_adi[:40] + "..." if len(e.dosya_adi) > 40 else e.dosya_adi,
                    'Tür': e.evrak_turu.value,
                    'Tarih': e.tarih.strftime('%d.%m.%Y') if e.tarih else '-'
                } for e in sonuc.evraklar]
                
                df = pd.DataFrame(evrak_data)
                st.dataframe(df, use_container_width=True, height=400)
        
        # TAB 3: TEBLİGATLAR
        with tab3:
            st.subheader("📬 Tebligat Durumu")
            
            if sonuc.tebligatlar:
                for t in sonuc.tebligatlar:
                    if "Tebliğ Edildi" in t.durum.value:
                        durum_class = "basari"
                    elif "Bila" in t.durum.value:
                        durum_class = "kritik"
                    else:
                        durum_class = "uyari"
                    
                    tarih_str = f'📅 {t.tarih.strftime("%d.%m.%Y")}' if t.tarih else ''
                    st.markdown(f"""
                    <div class="{durum_class}-box">
                        <strong>{t.durum.value}</strong><br>
                        📄 {t.evrak_adi}<br>
                        {tarih_str}
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.info("Tebligat evrakı bulunamadı")
        
        # TAB 4: HACİZLER
        with tab4:
            st.subheader("🔒 Haciz Durumu")
            
            if sonuc.toplam_bloke > 0:
                st.markdown(f"""
                <div class="bloke-box">
                    <h2 style="margin: 0;">💰 TOPLAM BLOKE: {sonuc.toplam_bloke:,.2f} TL</h2>
                </div>
                """, unsafe_allow_html=True)
            
            if sonuc.hacizler:
                haciz_data = [{
                    'Tür': h.tur,
                    'Tarih': h.tarih.strftime('%d.%m.%Y') if h.tarih else '-',
                    'Tutar': f"{h.tutar:,.2f} TL" if h.tutar else '-',
                    'Kalan Süre': f"{h.sure_106_110} gün" if h.sure_106_110 else '-'
                } for h in sonuc.hacizler]
                
                df = pd.DataFrame(haciz_data)
                st.dataframe(df, use_container_width=True)
                
                # Kritik süre uyarıları
                kritik_hacizler = [h for h in sonuc.hacizler if h.sure_106_110 and h.sure_106_110 <= 30]
                if kritik_hacizler:
                    st.error(f"⚠️ {len(kritik_hacizler)} hacizde satış talep süresi 30 günden az!")
            else:
                st.info("Haciz evrakı bulunamadı")
        
        # TAB 5: İNDİR
        with tab5:
            st.subheader("📥 Rapor ve Excel İndir")
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.download_button(
                    label="📄 Analiz Raporu (TXT)",
                    data=sonuc.ozet_rapor,
                    file_name=f"dosya_analiz_{datetime.now().strftime('%Y%m%d_%H%M')}.txt",
                    mime="text/plain"
                )
            
            with col2:
                if st.button("📊 Excel Oluştur"):
                    try:
                        excel_path = os.path.join(tempfile.gettempdir(), f"dosya_analiz_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx")
                        analyzer = UYAPDosyaAnalyzer()
                        analyzer.excel_olustur(sonuc, excel_path)
                        
                        with open(excel_path, 'rb') as f:
                            excel_data = f.read()
                        
                        st.download_button(
                            label="⬇️ Excel İndir",
                            data=excel_data,
                            file_name=os.path.basename(excel_path),
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        )
                    except Exception as e:
                        st.error(f"Excel oluşturma hatası: {e}")
            
            st.markdown("### 📋 Tam Rapor")
            st.code(sonuc.ozet_rapor, language=None)
    
    else:
        # Başlangıç ekranı - YENİ VİZYON
        st.markdown("""
        <div style="text-align: center; padding: 2rem;">
            <h2>📦 UYAP ZIP Yükleyin - Gerisini Biz Yapalım!</h2>
            <p style="color: #666; font-size: 1.1rem;">
                Excel doldurmak yok! Sadece UYAP'tan indirin, yükleyin, analizi alın.
            </p>
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown("""
        <div style="text-align: center; padding: 1rem; background: #f5f5f5; border-radius: 10px; margin: 2rem 0;">
            <h3>🔄 Nasıl Çalışır?</h3>
            <p style="font-size: 1.5rem;">
                📥 UYAP ZIP → ⚙️ Otomatik Analiz → 📊 Excel + 📄 Rapor
            </p>
        </div>
        """, unsafe_allow_html=True)
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.markdown("""
            ### 📥 GİRDİ
            **Sadece UYAP ZIP**
            - UYAP'tan evrak indir
            - ZIP olarak kaydet
            - Buraya yükle
            
            *Excel doldurmak YOK!*
            """)
        
        with col2:
            st.markdown("""
            ### ⚙️ OTOMATİK ANALİZ
            **Sistem algılar:**
            - Evrak türleri
            - Tebligat durumu
            - Haciz bilgileri
            - Kritik tarihler
            - Eksik işlemler
            """)
        
        with col3:
            st.markdown("""
            ### 📤 ÇIKTI
            **Size sunulan:**
            - ✅ Aksiyon listesi
            - 📊 Özet Excel
            - 📋 Analiz raporu
            - ⏰ Kritik tarihler
            """)


# ============================================================================
# NEAT PDF SAYFASI
# ============================================================================

def neat_pdf_sayfasi():
    """UYAP Dosyalarını Neat PDF'e Dönüştür"""
    
    st.markdown('<div class="main-header">📄 Neat PDF Üretici</div>', unsafe_allow_html=True)
    st.markdown('<p style="text-align: center; color: #666;">UYAP dosyalarını düzgün, profesyonel tek PDF\'e dönüştürün</p>', unsafe_allow_html=True)
    
    if not NEAT_PDF_AVAILABLE:
        st.error("⚠️ Neat PDF modülü kullanılamıyor.")
        st.warning("""
        **Olası nedenler:**
        - `reportlab` kütüphanesi yüklenmemiş
        - `requirements.txt` dosyasında `reportlab>=4.0.0` satırı eksik
        
        **Çözüm:**
        1. GitHub repo'nuzdaki `requirements.txt` dosyasını kontrol edin
        2. Şu satırların olduğundan emin olun:
        ```
        reportlab>=4.0.0
        PyPDF2>=3.0.0
        Pillow>=10.0.0
        ```
        3. Streamlit Cloud'da uygulamayı yeniden başlatın (Reboot app)
        """)
        return
    
    # Session state
    if 'neat_rapor' not in st.session_state:
        st.session_state.neat_rapor = None
    if 'neat_pdf_bytes' not in st.session_state:
        st.session_state.neat_pdf_bytes = None
    
    # Sidebar
    with st.sidebar:
        st.header("📁 UYAP Dosyası Yükle")
        
        uploaded_file = st.file_uploader(
            "ZIP dosyası yükleyin",
            type=['zip'],
            help="UYAP'tan indirilen evrak arşivi",
            key="neat_uploader"
        )
        
        if uploaded_file:
            st.success(f"✅ {uploaded_file.name}")
            
            # Ayarlar
            st.markdown("### ⚙️ Ayarlar")
            baslik = st.text_input("PDF Başlığı", value="İCRA DOSYASI", key="neat_baslik")
            icindekiler = st.checkbox("İçindekiler Ekle", value=True, key="neat_icindekiler")
            
            if st.button("📄 Neat PDF Üret", type="primary", key="neat_uret"):
                with st.spinner("PDF oluşturuluyor..."):
                    try:
                        # Dosyayı temp'e kaydet
                        temp_zip = os.path.join(tempfile.gettempdir(), uploaded_file.name)
                        with open(temp_zip, 'wb') as f:
                            f.write(uploaded_file.getvalue())
                        
                        # Çıktı yolu
                        cikti_pdf = os.path.join(tempfile.gettempdir(), f"BIRLESIK_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf")
                        
                        # Üret
                        uretici = NeatPDFUretici()
                        rapor = uretici.uret(temp_zip, cikti_pdf, baslik=baslik, icindekiler=icindekiler)
                        
                        st.session_state.neat_rapor = rapor
                        
                        # PDF'i oku
                        if rapor.cikti_dosya and os.path.exists(rapor.cikti_dosya):
                            with open(rapor.cikti_dosya, 'rb') as f:
                                st.session_state.neat_pdf_bytes = f.read()
                        
                        # Temizlik
                        if os.path.exists(temp_zip):
                            os.remove(temp_zip)
                        
                    except Exception as e:
                        st.error(f"Hata: {str(e)}")
                
                st.rerun()
        
        st.divider()
        
        st.info("""
        **Desteklenen Formatlar:**
        - 📄 UDF (UYAP belgeleri)
        - 📑 PDF
        - 🖼️ TIFF, PNG, JPG
        - 📝 TXT, XML, HTML
        
        **Çıktı:**
        - Tek düzgün PDF
        - Sayfa numaraları
        - İçindekiler
        - Tarih damgası
        """)
    
    # Ana içerik
    if st.session_state.neat_rapor:
        rapor = st.session_state.neat_rapor
        
        # Üst kartlar
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("📁 Toplam Dosya", rapor.toplam_dosya)
        with col2:
            st.metric("✅ İşlenen", rapor.islenen_dosya)
        with col3:
            st.metric("📄 Sayfa Sayısı", rapor.toplam_sayfa)
        with col4:
            st.metric("⏱️ Süre", f"{rapor.sure_saniye:.1f} sn")
        
        st.divider()
        
        # Başarı mesajı ve indirme
        if rapor.cikti_dosya and st.session_state.neat_pdf_bytes:
            st.markdown(f"""
            <div class="basari-box">
                <h3 style="margin: 0;">✅ PDF Başarıyla Oluşturuldu!</h3>
                <p>{rapor.islenen_dosya} dosya → {rapor.toplam_sayfa} sayfa</p>
            </div>
            """, unsafe_allow_html=True)
            
            # İndirme butonu
            col1, col2 = st.columns([1, 3])
            with col1:
                st.download_button(
                    label="📥 PDF İNDİR",
                    data=st.session_state.neat_pdf_bytes,
                    file_name=f"BIRLESIK_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
                    mime="application/pdf",
                    type="primary"
                )
        
        # Sekmeler
        tab1, tab2, tab3 = st.tabs(["📊 Özet", "📋 Dosya Listesi", "⚠️ Hatalar"])
        
        with tab1:
            st.subheader("📊 İşlem Özeti")
            
            # Dosya türü dağılımı
            tur_sayilari = {}
            for d in rapor.dosyalar:
                tur = d.dosya_turu
                tur_sayilari[tur] = tur_sayilari.get(tur, 0) + 1
            
            if tur_sayilari:
                st.markdown("### Dosya Türleri")
                for tur, sayi in sorted(tur_sayilari.items()):
                    emoji = "📄" if tur == "UDF" else "📑" if tur == "PDF" else "🖼️" if tur == "IMG" else "📝"
                    st.write(f"{emoji} **{tur}:** {sayi} dosya")
            
            # İstatistikler
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("### İşlem Durumu")
                st.write(f"✅ İşlenen: {rapor.islenen_dosya}")
                st.write(f"⏭️ Atlanan: {rapor.atlanan_dosya}")
                st.write(f"❌ Hatalı: {rapor.hatali_dosya}")
            
            with col2:
                st.markdown("### Performans")
                st.write(f"⏱️ Toplam Süre: {rapor.sure_saniye:.2f} saniye")
                if rapor.islenen_dosya > 0:
                    st.write(f"📊 Dosya/saniye: {rapor.islenen_dosya/rapor.sure_saniye:.1f}")
        
        with tab2:
            st.subheader("📋 İşlenen Dosyalar")
            
            if rapor.dosyalar:
                dosya_data = []
                for d in rapor.dosyalar:
                    durum = "✅" if d.islendi else "❌" if d.hata else "⏭️"
                    dosya_data.append({
                        'Durum': durum,
                        'Dosya': d.orijinal_ad[:40] + "..." if len(d.orijinal_ad) > 40 else d.orijinal_ad,
                        'Tür': d.dosya_turu,
                        'Boyut (KB)': f"{d.boyut_kb:.1f}",
                        'Hata': d.hata or "-"
                    })
                
                df = pd.DataFrame(dosya_data)
                st.dataframe(df, use_container_width=True, height=400)
        
        with tab3:
            st.subheader("⚠️ Hatalar ve Uyarılar")
            
            if rapor.hatalar:
                for hata in rapor.hatalar:
                    st.error(hata)
            else:
                st.success("✅ Hiç hata yok!")
            
            # Atlanan dosyalar
            atlanan = [d for d in rapor.dosyalar if not d.islendi and d.hata]
            if atlanan:
                st.markdown("### Atlanan Dosyalar")
                for d in atlanan:
                    st.warning(f"**{d.orijinal_ad}:** {d.hata}")
    
    else:
        # Başlangıç ekranı
        st.markdown("""
        <div style="text-align: center; padding: 3rem;">
            <h2>📦 UYAP ZIP Dosyası Yükleyin</h2>
            <p>Sol menüden dosya yükleyerek düzgün PDF oluşturun.</p>
        </div>
        """, unsafe_allow_html=True)
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.markdown("""
            **📥 Girdi**
            - UYAP ZIP arşivi
            - UDF belgeleri
            - PDF, TIFF, görüntüler
            """)
        
        with col2:
            st.markdown("""
            **⚙️ İşlem**
            - Otomatik format algılama
            - Metin çıkarma
            - Görüntü dönüştürme
            """)
        
        with col3:
            st.markdown("""
            **📄 Çıktı**
            - Tek profesyonel PDF
            - Sayfa numaraları
            - İçindekiler sayfası
            """)


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
        ["🏦 89/1-2-3 Haciz İhbar", "📄 Neat PDF Üret", "📁 İcra Dosya Analizi"],
        index=0
    )
    
    st.sidebar.markdown("---")
    
    if modul == "🏦 89/1-2-3 Haciz İhbar":
        banka_cevaplari_sayfasi()
    elif modul == "📄 Neat PDF Üret":
        neat_pdf_sayfasi()
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
