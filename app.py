import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# Sayfa Ayarları
st.set_page_config(page_title="İMO Van 2026", layout="wide", page_icon="🏗️")

# --- 1. BAĞLANTIYI KUR ---
@st.cache_resource
def get_connection():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    return client

# --- 2. VERİYİ ÇEK VE TEMİZLE ---
def get_data():
    client = get_connection()
    try:
        sheet = client.open("Van_IMO_Secim_2026")
        ws = sheet.worksheet("secmenler")
        data = ws.get_all_records()
        df = pd.DataFrame(data)
        
        # Sütun İsimlerindeki Boşlukları Temizle (HAYAT KURTARAN HAMLE)
        # "Cizikler " şeklindeki hatalı başlıkları "Cizikler" yapar.
        df.columns = df.columns.str.strip()
        
        # Tüm verileri yazıya çevir ki hata vermesin
        df = df.astype(str)
        return df, ws
    except Exception as e:
        return None, None

# --- 3. GİRİŞ EKRANI ---
if 'user' not in st.session_state:
    st.session_state.user = None

if st.session_state.user is None:
    st.title("🏗️ İMO VAN 2026 - GÜVENLİ GİRİŞ")
    with st.form("giris_formu"):
        kadi = st.text_input("Kullanıcı Adı")
        sifre = st.text_input("Şifre", type="password")
        # Submit butonu formun içinde olmalı!
        btn = st.form_submit_button("Giriş Yap")
        
        if btn:
            try:
                client = get_connection()
                sheet = client.open("Van_IMO_Secim_2026")
                ws_users = sheet.worksheet("kullanicilar")
                users = ws_users.get_all_records()
                df_users = pd.DataFrame(users)
                
                # Kullanıcı Doğrulama
                login_user = df_users[df_users['Kullanici_Adi'] == kadi]
                if not login_user.empty and str(login_user.iloc[0]['Sifre']) == sifre:
                    st.session_state.user = login_user.iloc[0].to_dict()
                    st.rerun()
                else:
                    st.error("❌ Hatalı Kullanıcı Adı veya Şifre")
            except Exception as e:
                st.error(f"Bağlantı Hatası: {e}")
    st.stop()

# --- 4. ANA PROGRAM ---
user = st.session_state.user
st.sidebar.success(f"Aktif Kullanıcı: {user['Kullanici_Adi']}")

if st.sidebar.button("Çıkış Yap"):
    st.session_state.user = None
    st.rerun()

# Veriyi getir
df, ws = get_data()

if df is None:
    st.error("⚠️ Excel dosyasına bağlanılamadı. Lütfen 'Van_IMO_Secim_2026' dosyasının adını ve 'secmenler' sayfasını kontrol et.")
    st.stop()

# --- MENÜ ---
menu = st.sidebar.radio("Menü", ["📝 Seçmen Listesi & Güncelleme", "📊 Analiz Raporu"])

# ==========================================
# EKRAN 1: SEÇMEN LİSTESİ (LİSTE DİREKT AÇILIR)
# ==========================================
if menu == "📝 Seçmen Listesi & Güncelleme":
    st.header("📋 Seçmen Yönetim Paneli")
    
    # Arama Kutusu (İsteğe bağlı)
    search_term = st.text_input("🔎 İsimle Hızlı Ara (Boş bırakırsan hepsi görünür)", placeholder="Örn: Ahmet")

    # Gösterilecek Sütunlar (Varsa gösterir, yoksa hata vermez)
    # Excel'deki başlıkların tam olarak bunlar olduğundan emin olmaya çalışıyoruz
    desired_columns = ['Sicil_No', 'Ad_Soyad', 'Kurum', 'Egilim', 'Son_Guncelleyen']
    available_columns = [col for col in desired_columns if col in df.columns]

    # Filtreleme
    if search_term:
        df_display = df[df['Ad_Soyad'].str.contains(search_term, case=False, na=False)]
    else:
        df_display = df

    # TABLOYU ÇİZ
    st.write(f"Toplam **{len(df_display)}** kişi listeleniyor.")
    
    event = st.dataframe(
        df_display[available_columns],
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row"
    )

    # --- KİŞİ SEÇİLDİĞİNDE FORM AÇILSIN ---
    if len(event.selection.rows) > 0:
        selected_row_idx = event.selection.rows[0]
        # Seçilen kişinin Sicil Numarasını al (Kaydırmayı önler)
        sicil_no = df_display.iloc[selected_row_idx]['Sicil_No']
        
        # Ana listeden (df) o kişiyi bul
        gercek_index = df[df['Sicil_No'] == sicil_no].index[0]
        row_num = gercek_index + 2 # Excel satır numarası
        kisi = df.iloc[gercek_index]

        st.divider()
        st.markdown(f"### 👤 Düzenleniyor: **{kisi['Ad_Soyad']}**")
        
        # --- GÜNCELLEME FORMU ---
        with st.form("guncelleme_formu"):
            c1, c2 = st.columns(2)
            
            # Not: .get() fonksiyonu, eğer Excel'de o sütun yoksa hata vermek yerine boş getirir.
            # Bu sayede "KeyError" hatası ALMAZSIN.
            
            with c1:
                st.markdown("**🏢 Kurumsal Bilgiler**")
                
                # Kurum
                opt_kurum = ["", "Özel Sektör", "Dsi", "Karayolları", "Büyükşehir", "Vaski", "Projeci", "Yapı Denetimci", "İlçe Belediyeleri", "Müteahhit", "Yapsat", "Diğer"]
                curr_kurum = kisi.get('Kurum', "") # Hata önleyici .get()
                idx_kurum = opt_kurum.index(curr_kurum) if curr_kurum in opt_kurum else 0
                yeni_kurum = st.selectbox("Kurum", opt_kurum, index=idx_kurum)
                
                # Geçmiş 2024
                opt_24 = ["", "Sarı Liste", "Mavi Liste"]
                curr_24 = kisi.get('Gecmis_2024', "")
                idx_24 = opt_24.index(curr_24) if curr_24 in opt_24 else 0
                yeni_24 = st.selectbox("2024 Seçimi", opt_24, index=idx_24)

                # Geçmiş 2022
                opt_22 = ["", "Sarı Liste", "Mavi Liste", "Beyaz Liste"]
                curr_22 = kisi.get('Gecmis_2022', "")
                idx_22 = opt_22.index(curr_22) if curr_22 in opt_22 else 0
                yeni_22 = st.selectbox("2022 Seçimi", opt_22, index=idx_22)

                # Referans
                yeni_referans = st.text_input("Referans / İlgilenen", value=kisi.get('Referans', ""))

            with c2:
                st.markdown("**🗳️ 2026 Durumu & Lojistik**")
                
                # Eğilim
                opt_egilim = ["", "Tüm Listemizi Yazar", "Büyük Kısmı Yazar", "Kısmen Yazar", "Karşı Tarafı Destekler", "Kararsızım"]
                curr_egilim = kisi.get('Egilim', "")
                idx_egilim = opt_egilim.index(curr_egilim) if curr_egilim in opt_egilim else 0
                yeni_egilim = st.selectbox("2026 Eğilimi", opt_egilim, index=idx_egilim)

                # Temas Durumu
                opt_temas = ["", "Kendim Görüştüm", "Arkadaşım/Akraba Aracılığı", "Tanımıyorum"]
                curr_temas = kisi.get('Temas_Durumu', "")
                idx_temas = opt_temas.index(curr_temas) if curr_temas in opt_temas else 0
                yeni_temas = st.selectbox("Temas Durumu", opt_temas, index=idx_temas)

                # Ulaşım
                opt_ulasim = ["", "Kendisi Gelir", "Araç Gerekir", "İlçeden Gelecek", "Temsilcilikten Gelecek"]
                curr_ulasim = kisi.get('Ulasim', "")
                idx_ulasim = opt_ulasim.index(curr_ulasim) if curr_ulasim in opt_ulasim else 0
                yeni_ulasim = st.selectbox("Ulaşım İhtiyacı", opt_ulasim, index=idx_ulasim)
                
                # Çizikler / Notlar
                yeni_cizik = st.text_input("Çizikler / Notlar", value=kisi.get('Cizikler', ""))
                yeni_rakip = st.text_input("Rakip Ekleme", value=kisi.get('Rakip_Ekleme', ""))

            # KAYDET BUTONU FORMUN İÇİNDE!
            submitted = st.form_submit_button("✅ BİLGİLERİ KAYDET")
            
            if submitted:
                try:
                    headers = df.columns.tolist()
                    
                    # Güncellemeler
                    updates = [
                        ("Kurum", yeni_kurum),
                        ("Gecmis_2024", yeni_24),
                        ("Gecmis_2022", yeni_22),
                        ("Referans", yeni_referans),
                        ("Egilim", yeni_egilim),
                        ("Temas_Durumu", yeni_temas),
                        ("Ulasim", yeni_ulasim),
                        ("Cizikler", yeni_cizik),
                        ("Rakip_Ekleme", yeni_rakip),
                        ("Son_Guncelleyen", user['Kullanici_Adi'])
                    ]
                    
                    for col_name, val in updates:
                        if col_name in headers:
                            col_idx = headers.index(col_name) + 1
                            ws.update_cell(row_num, col_idx, val)
                    
                    st.success(f"✅ {kisi['Ad_Soyad']} başarıyla güncellendi!")
                
                except Exception as e:
                    st.error(f"Hata oluştu: {e}")

# ==========================================
# EKRAN 2: ANALİZ RAPORU
# ==========================================
elif menu == "📊 Analiz Raporu":
    st.title("📊 Seçim Komuta Merkezi")
    
    toplam = len(df)
    ulasilan = len(df[df['Egilim'].str.len() > 1]) if 'Egilim' in df.columns else 0
    
    c1, c2 = st.columns(2)
    c1.metric("Toplam Üye", toplam)
    c2.metric("Veri Girilen", ulasilan, f"%{int(ulasilan/toplam*100) if toplam else 0}")
    
    st.divider()
    
    if ulasilan > 0:
        import plotly.express as px
        # Grafik 1: Pasta Dilimi
        fig = px.pie(df[df['Egilim'].str.len() > 1], names='Egilim', title='Genel Oy Dağılımı')
        st.plotly_chart(fig, use_container_width=True)
        
        # Grafik 2: Kurum Bazlı
        if 'Kurum' in df.columns:
            bizimkiler = df[df['Egilim'].isin(["Tüm Listemizi Yazar", "Büyük Kısmı Yazar"])]
            if not bizimkiler.empty:
                fig2 = px.bar(bizimkiler, x='Kurum', title="Bizi Destekleyenlerin Kurum Dağılımı")
                st.plotly_chart(fig2, use_container_width=True)
    else:
        st.info("Henüz yeterli veri girişi yapılmadı.")
