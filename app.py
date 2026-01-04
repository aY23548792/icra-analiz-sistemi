#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
İCRA ANALİZ SİSTEMİ v2.0
========================
UYAP Evrakları → Profesyonel PDF

Modüller:
1. Neat PDF Üret - UDF/PDF/TIFF → Tek Birleşik PDF
"""

import streamlit as st
import os
import tempfile
from datetime import datetime

# Pandas
try:
    import pandas as pd
    PANDAS_OK = True
except ImportError:
    PANDAS_OK = False

# Neat PDF modülü
NEAT_PDF_AVAILABLE = False
try:
    from neat_pdf_uretici import NeatPDFUretici, NeatPDFRapor, REPORTLAB_OK
    if REPORTLAB_OK:
        NEAT_PDF_AVAILABLE = True
except ImportError:
    pass

# Sayfa ayarları
st.set_page_config(
    page_title="İcra Analiz Sistemi",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS Stilleri
st.markdown("""
<style>
    /* Ana başlık */
    .main-header {
        font-size: 2rem;
        font-weight: bold;
        color: #1E3A5F;
        text-align: center;
        padding: 1rem;
        margin-bottom: 1rem;
    }
    
    /* Başarı kutusu */
    .basari-box {
        background: linear-gradient(135deg, #d4edda 0%, #c3e6cb 100%);
        border-left: 4px solid #28a745;
        padding: 1rem 1.5rem;
        border-radius: 8px;
        margin: 1rem 0;
    }
    
    /* Bilgi kutusu */
    .bilgi-box {
        background: linear-gradient(135deg, #e7f3ff 0%, #cce5ff 100%);
        border-left: 4px solid #0066cc;
        padding: 1rem 1.5rem;
        border-radius: 8px;
        margin: 1rem 0;
    }
    
    /* Metrik kartları */
    .stMetric {
        background: #f8f9fa;
        padding: 1rem;
        border-radius: 8px;
        border: 1px solid #e9ecef;
    }
    
    /* Sidebar */
    .css-1d391kg {
        background: #f8f9fa;
    }
    
    /* Butonlar */
    .stButton > button {
        width: 100%;
    }
    
    /* Download butonu */
    .stDownloadButton > button {
        background-color: #28a745;
        color: white;
    }
</style>
""", unsafe_allow_html=True)


def main():
    """Ana uygulama"""
    
    # Başlık
    st.markdown('<div class="main-header">⚖️ İcra Analiz Sistemi</div>', unsafe_allow_html=True)
    st.markdown('<p style="text-align: center; color: #666; margin-bottom: 2rem;">UYAP Evrakları → Profesyonel Birleşik PDF</p>', unsafe_allow_html=True)
    
    # Modül kontrolü
    if not NEAT_PDF_AVAILABLE:
        st.error("⚠️ Neat PDF modülü kullanılamıyor.")
        st.warning("""
        **Olası nedenler:**
        - `reportlab` kütüphanesi yüklenmemiş
        
        **Çözüm:**
        `requirements.txt` dosyasında şunlar olmalı:
        ```
        streamlit>=1.28.0
        reportlab>=4.0.0
        PyPDF2>=3.0.0
        Pillow>=10.0.0
        pandas>=2.0.0
        ```
        """)
        return
    
    # Session state
    if 'rapor' not in st.session_state:
        st.session_state.rapor = None
    if 'pdf_bytes' not in st.session_state:
        st.session_state.pdf_bytes = None
    
    # Sidebar
    with st.sidebar:
        st.header("📁 UYAP Dosyası Yükle")
        
        uploaded_file = st.file_uploader(
            "ZIP dosyası seçin",
            type=['zip'],
            help="UYAP'tan indirilen evrak arşivi (UDF, PDF, TIFF içerebilir)"
        )
        
        if uploaded_file:
            st.success(f"✅ {uploaded_file.name}")
            st.caption(f"Boyut: {uploaded_file.size / 1024:.1f} KB")
            
            st.divider()
            
            # Ayarlar
            st.subheader("⚙️ Ayarlar")
            baslik = st.text_input(
                "PDF Başlığı",
                value="İCRA DOSYASI",
                help="Kapak sayfasında görünecek başlık"
            )
            icindekiler = st.checkbox(
                "İçindekiler Ekle",
                value=True,
                help="PDF'e içindekiler sayfası ekle"
            )
            
            st.divider()
            
            # Üret butonu
            if st.button("📄 NEAT PDF ÜRET", type="primary", use_container_width=True):
                with st.spinner("PDF oluşturuluyor..."):
                    try:
                        # Dosyayı temp'e kaydet
                        temp_zip = os.path.join(tempfile.gettempdir(), uploaded_file.name)
                        with open(temp_zip, 'wb') as f:
                            f.write(uploaded_file.getvalue())
                        
                        # Çıktı yolu
                        cikti_pdf = os.path.join(
                            tempfile.gettempdir(),
                            f"BIRLESIK_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
                        )
                        
                        # Üret
                        uretici = NeatPDFUretici()
                        rapor = uretici.uret(
                            temp_zip,
                            cikti_pdf,
                            baslik=baslik,
                            icindekiler=icindekiler
                        )
                        
                        st.session_state.rapor = rapor
                        
                        # PDF'i oku
                        if rapor.cikti_dosya and os.path.exists(rapor.cikti_dosya):
                            with open(rapor.cikti_dosya, 'rb') as f:
                                st.session_state.pdf_bytes = f.read()
                        
                        # Temizlik
                        if os.path.exists(temp_zip):
                            os.remove(temp_zip)
                        
                    except Exception as e:
                        st.error(f"Hata: {str(e)}")
                
                st.rerun()
        
        st.divider()
        
        # Bilgi
        st.info("""
        **Desteklenen Formatlar:**
        - 📄 UDF (UYAP belgeleri)
        - 📑 PDF
        - 🖼️ TIFF, PNG, JPG
        
        **Çıktı:**
        - Profesyonel format
        - Kapak sayfası
        - İçindekiler
        - Sayfa numaraları
        """)
    
    # Ana içerik
    if st.session_state.rapor:
        rapor = st.session_state.rapor
        
        # Üst metrikler
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("📁 Toplam Dosya", rapor.toplam_dosya)
        with col2:
            st.metric("✅ İşlenen", rapor.islenen_dosya)
        with col3:
            st.metric("📄 Sayfa", rapor.toplam_sayfa)
        with col4:
            st.metric("⏱️ Süre", f"{rapor.sure_saniye:.1f} sn")
        
        st.divider()
        
        # Başarı mesajı
        if rapor.cikti_dosya and st.session_state.pdf_bytes:
            st.markdown(f"""
            <div class="basari-box">
                <h3 style="margin: 0; color: #155724;">✅ PDF Başarıyla Oluşturuldu!</h3>
                <p style="margin: 0.5rem 0 0 0; color: #155724;">{rapor.islenen_dosya} dosya → {rapor.toplam_sayfa} sayfa</p>
            </div>
            """, unsafe_allow_html=True)
            
            # İndirme butonu
            col1, col2, col3 = st.columns([1, 1, 2])
            with col1:
                st.download_button(
                    label="📥 PDF İNDİR",
                    data=st.session_state.pdf_bytes,
                    file_name=f"BIRLESIK_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
                    mime="application/pdf",
                    type="primary",
                    use_container_width=True
                )
            with col2:
                if st.button("🔄 Yeni Dosya", use_container_width=True):
                    st.session_state.rapor = None
                    st.session_state.pdf_bytes = None
                    st.rerun()
        
        st.divider()
        
        # Sekmeler
        tab1, tab2, tab3 = st.tabs(["📊 Özet", "📋 Dosya Listesi", "⚠️ Hatalar"])
        
        with tab1:
            st.subheader("📊 İşlem Özeti")
            
            # Dosya türü dağılımı
            if rapor.dosyalar:
                tur_sayilari = {}
                for d in rapor.dosyalar:
                    tur = d.dosya_turu
                    tur_sayilari[tur] = tur_sayilari.get(tur, 0) + 1
                
                col1, col2 = st.columns(2)
                
                with col1:
                    st.markdown("### Dosya Türleri")
                    for tur, sayi in sorted(tur_sayilari.items()):
                        emoji = {
                            'UDF': '📄',
                            'PDF': '📑',
                            'TIFF': '🖼️',
                            'IMG': '🖼️'
                        }.get(tur, '📄')
                        st.write(f"{emoji} **{tur}:** {sayi} dosya")
                
                with col2:
                    st.markdown("### İşlem Durumu")
                    st.write(f"✅ İşlenen: {rapor.islenen_dosya}")
                    st.write(f"❌ Hatalı: {rapor.hatali_dosya}")
                    st.write(f"⏭️ Atlanan: {rapor.atlanan_dosya}")
                    st.write(f"⏱️ Süre: {rapor.sure_saniye:.2f} saniye")
        
        with tab2:
            st.subheader("📋 İşlenen Dosyalar")
            
            if rapor.dosyalar and PANDAS_OK:
                dosya_data = []
                for d in rapor.dosyalar:
                    durum = "✅" if d.islendi else "❌" if d.hata else "⏭️"
                    dosya_data.append({
                        'Durum': durum,
                        'Dosya': d.orijinal_ad[:40] + "..." if len(d.orijinal_ad) > 40 else d.orijinal_ad,
                        'Tür': d.dosya_turu,
                        'Boyut (KB)': f"{d.boyut_kb:.1f}",
                        'Başlık': (d.baslik[:30] + "..." if d.baslik and len(d.baslik) > 30 else d.baslik) or "-",
                        'Hata': d.hata or "-"
                    })
                
                df = pd.DataFrame(dosya_data)
                st.dataframe(df, use_container_width=True, height=400)
            else:
                st.info("Dosya listesi için pandas gerekli")
        
        with tab3:
            st.subheader("⚠️ Hatalar ve Uyarılar")
            
            if rapor.hatalar:
                for hata in rapor.hatalar:
                    st.error(hata)
            else:
                st.success("✅ Hiç hata yok!")
    
    else:
        # Başlangıç ekranı
        st.markdown("""
        <div class="bilgi-box">
            <h3 style="margin: 0; color: #004085;">📦 UYAP ZIP Dosyası Yükleyin</h3>
            <p style="margin: 0.5rem 0 0 0; color: #004085;">Sol menüden ZIP yükleyerek profesyonel PDF oluşturun.</p>
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown("---")
        
        # Nasıl çalışır
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.markdown("""
            ### 📥 1. Yükle
            - UYAP'tan evrak indir
            - ZIP olarak kaydet
            - Sol menüden yükle
            """)
        
        with col2:
            st.markdown("""
            ### ⚙️ 2. İşle
            - UDF metin çıkarma
            - PDF birleştirme
            - TIFF dönüştürme
            """)
        
        with col3:
            st.markdown("""
            ### 📤 3. İndir
            - Profesyonel format
            - T.C. başlıklı
            - Kapak + İçindekiler
            """)
        
        st.markdown("---")
        
        # Özellikler
        st.markdown("### ✨ Özellikler")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("""
            **Desteklenen Formatlar:**
            - ✅ UDF (UYAP dokümanları)
            - ✅ PDF (direkt birleştirme)
            - ✅ TIFF/TIF (görüntü)
            - ✅ PNG/JPG (görüntü)
            """)
        
        with col2:
            st.markdown("""
            **PDF Özellikleri:**
            - ✅ T.C. başlıklı resmi format
            - ✅ Kapak sayfası
            - ✅ İçindekiler
            - ✅ Sayfa numaraları
            - ✅ Tarih damgası
            """)


if __name__ == "__main__":
    main()
