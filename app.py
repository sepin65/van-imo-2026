import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from oauth2client.service_account import ServiceAccountCredentials

st.set_page_config(page_title="İMO Van 2026", layout="wide", page_icon="🏗️")

# --- BAĞLANTI AYARLARI ---
@st.cache_resource
def get_connection():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    return client

def get_data():
    client = get_connection()
    try:
        sheet = client.open("Van_IMO_Secim_2026")
        ws = sheet.worksheet("secmenler")
        data = ws.get_all_records()
        df = pd.DataFrame(data)
        # Tüm sütunları metin (string) formatına çevir ki hata vermesin
        df = df.astype(str) 
        return df, ws
    except Exception as e:
        st.error(f"Excel Bağlantı Hatası: {e}")
        return pd.DataFrame(), None

# --- GİRİŞ EKRANI ---
if 'user' not in st.session_state:
    st.session_state.user = None

if st.session_state.user is None:
    st.title("🏗️ İMO VAN 2026 - SEÇİM SİSTEMİ")
    with st.form("giris"):
        kadi = st.text_input("Kullanıcı Adı")
        sifre = st.text_input("Şifre", type="password")
        btn = st.form_submit_button("Giriş Yap")
        if btn:
            try:
                client = get_connection()
                sheet = client.open("Van_IMO_Secim_2026")
                ws_users = sheet.worksheet("kullanicilar")
                users = ws_users.get_all_records()
                df_users = pd.DataFrame(users)
                
                login_user = df_users[df_users['Kullanici_Adi'] == kadi]
                if not login_user.empty and str(login_user.iloc[0]['Sifre']) == sifre:
                    st.session_state.user = login_user.iloc[0].to_dict()
                    st.rerun()
                else:
                    st.error("Hatalı Kullanıcı Adı veya Şifre!")
            except Exception as e:
                st.error(f"Giriş Hatası: {e}")
    st.stop()

# --- ANA PROGRAM ---
user = st.session_state.user
st.sidebar.info(f"👤 {user['Kullanici_Adi']} | Görev: {user['Rol']}")

if st.sidebar.button("Çıkış"):
    st.session_state.user = None
    st.rerun()

df, ws = get_data()
if df.empty:
    st.warning("Veri bulunamadı.")
    st.stop()

# NOT: Temsilcilik sütunu henüz boş olduğu için kısıtlamayı şimdilik kapattık.
# Herkes listeyi görebilir. İleride açabiliriz.
# if user['Rol'] == 'SAHA' and user['Bolge_Yetkisi'] != 'Tümü':
#     df = df[df['Temsilcilik'] == user['Bolge_Yetkisi']]

menu = st.sidebar.radio("Menü", ["📊 Genel Durum (Analiz)", "📝 Seçmen Listesi & Giriş"])

# --- 1. ANALİZ EKRANI (Adminler İçin Özet) ---
if menu == "📊 Genel Durum (Analiz)":
    st.title("📊 Seçim Komuta Merkezi")
    
    # Rakamlar
    toplam = len(df)
    # Eğilim sütunu boş olmayanlar (Veri girilmiş kişiler)
    ulasilan = len(df[df['Egilim'].str.len() > 1])
    
    # Bizimkiler (Tüm Listemizi Yazar + Büyük Kısmı Yazar)
    bizimkiler = len(df[df['Egilim'].isin(["Tüm Listemizi Yazar", "Büyük Kısmı Yazar"])])

    c1, c2, c3 = st.columns(3)
    c1.metric("Toplam Seçmen", toplam)
    c2.metric("Veri Girilen", ulasilan, f"%{int(ulasilan/toplam*100) if toplam else 0}")
    c3.metric("🎯 Potansiyel Oyumuz", bizimkiler)
    
    st.divider()

    if ulasilan > 0:
        tab1, tab2, tab3 = st.tabs(["Genel Dağılım", "Kurum Analizi", "Lojistik/Ulaşım"])
        
        with tab1:
            st.subheader("Üyelerin Eğilimi")
            fig_pie = px.pie(df[df['Egilim'].str.len() > 1], names='Egilim', title='Oy Tercih Dağılımı', hole=0.4)
            st.plotly_chart(fig_pie, use_container_width=True)
            
            st.subheader("2024 vs 2026 Geçiş Analizi")
            # Sadece 2024 ve Egilim dolu olanları al
            df_gecis = df[(df['Gecmis_2024'].str.len() > 1) & (df['Egilim'].str.len() > 1)]
            if not df_gecis.empty:
                fig_bar = px.bar(df_gecis, x="Gecmis_2024", color="Egilim", title="2024 Tercihine Göre Şimdiki Durum")
                st.plotly_chart(fig_bar, use_container_width=True)
        
        with tab2:
            st.subheader("Kurumlara Göre Bizim Durum")
            # Sadece bizimkilere bakalım
            df_bizim = df[df['Egilim'].isin(["Tüm Listemizi Yazar", "Büyük Kısmı Yazar"])]
            if not df_bizim.empty:
                fig_kurum = px.bar(df_bizim, x='Kurum', title="Bize Oy Vereceklerin Kurum Dağılımı")
                st.plotly_chart(fig_kurum, use_container_width=True)
            else:
                st.info("Henüz yeterli veri oluşmadı.")

        with tab3:
            st.subheader("Seçim Günü Ulaşım İhtiyacı")
            ulasim_counts = df['Ulasim'].value_counts().reset_index()
            ulasim_counts.columns = ['Durum', 'Kişi Sayısı']
            # Boşları filtrele
            ulasim_counts = ulasim_counts[ulasim_counts['Durum'].str.len() > 1]
            fig_ulasim = px.bar(ulasim_counts, x='Durum', y='Kişi Sayısı', color='Durum')
            st.plotly_chart(fig_ulasim, use_container_width=True)

    else:
        st.info("Henüz saha ekibi veri girişine başlamadı.")

# --- 2. VERİ GİRİŞ EKRANI (Mazlum ve Ekip İçin) ---
elif menu == "📝 Seçmen Listesi & Giriş":
    st.header("📝 Seçmen Bilgi Kartı")
    st.info("👇 Listeden isme tıklayın, bilgileri doldurup 'Kaydet'e basın.")

    # Arama Kutusu
    filter_text = st.text_input("🔍 İsim Ara (Filtrele)")
    
    # Tabloda gösterilecek sütunlar
    cols_show = ['Sicil_No', 'Ad_Soyad', 'Kurum', 'Egilim', 'Son_Guncelleyen']
    
    # Filtreleme mantığı
    if filter_text:
        df_show = df[df['Ad_Soyad'].str.contains(filter_text, case=False, na=False)]
    else:
        df_show = df

    # Tıklanabilir Tablo
    event = st.dataframe(
        df_show[cols_show], 
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row"
    )

    if len(event.selection.rows) > 0:
        selected_row_idx = event.selection.rows[0]
        # Filtrelenmiş listeden seçilen kişiyi bul
        sicil_no = df_show.iloc[selected_row_idx]['Sicil_No']
        
        # Ana DataFrame'den o kişiyi çek
        gercek_index = df[df['Sicil_No'] == sicil_no].index[0]
        row_num = gercek_index + 2 # Excel satır no
        kisi = df.iloc[gercek_index]

        st.divider()
        st.markdown(f"### 👷‍♂️ **{kisi['Ad_Soyad']}**")
        st.caption(f"Sicil: {kisi['Sicil_No']} | Kayıtlı Bölge: {kisi['Dogum_Yeri']}")

        with st.form("veri_giris_formu", border=True):
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("##### 🏢 Kurum ve Geçmiş")
                # KURUM LİSTESİ (Resimden)
                opt_kurum = ["", "Özel Sektör", "Dsi", "Karayolları", "Büyükşehir", "Vaski", "Projeci", "Yapı Denetimci", "İlçe Belediyeleri", "Müteahhit", "Yapsat", "Diğer"]
                curr_kurum = kisi['Kurum']
                idx_kurum = opt_kurum.index(curr_kurum) if curr_kurum in opt_kurum else 0
                yeni_kurum = st.selectbox("Kurum", opt_kurum, index=idx_kurum)
                
                # GEÇMİŞ 2024
                opt_24 = ["", "Sarı Liste", "Mavi Liste"]
                curr_24 = kisi['Gecmis_2024']
                idx_24 = opt_24.index(curr_24) if curr_24 in opt_24 else 0
                yeni_24 = st.selectbox("2024 Tercihi", opt_24, index=idx_24)

                # GEÇMİŞ 2022
                opt_22 = ["", "Sarı Liste", "Mavi Liste", "Beyaz Liste"]
                curr_22 = kisi['Gecmis_2022']
                idx_22 = opt_22.index(curr_22) if curr_22 in opt_22 else 0
                yeni_22 = st.selectbox("2022 Tercihi", opt_22, index=idx_22)

            with col2:
                st.markdown("##### 🗳️ 2026 Durumu ve Ulaşım")
                # EĞİLİM (Puanlama)
                opt_egilim = ["", "Tüm Listemizi Yazar", "Büyük Kısmı Yazar", "Kısmen Yazar", "Karşı Tarafı Destekler", "Kararsızım"]
                curr_egilim = kisi['Egilim']
                idx_egilim = opt_egilim.index(curr_egilim) if curr_egilim in opt_egilim else 0
                yeni_egilim = st.selectbox("2026 Eğilimi", opt_egilim, index=idx_egilim)

                # TEMAS DURUMU
                opt_temas = ["", "Kendim Görüştüm", "Arkadaşım/Akraba Aracılığı", "Tanımıyorum"]
                curr_temas = kisi['Temas_Durumu']
                idx_temas = opt_temas.index(curr_temas) if curr_temas in opt_temas else 0
                yeni_temas = st.selectbox("Temas Durumu", opt_temas, index=idx_temas)

                # ULAŞIM
                opt_ulasim = ["", "Kendisi Gelir", "Araç Gerekir", "İlçeden Gelecek", "Temsilcilikten Gelecek"]
                curr_ulasim = kisi['Ulasim']
                idx_ulasim = opt_ulasim.index(curr_ulasim) if curr_ulasim in opt_ulasim else 0
                yeni_ulasim = st.selectbox("Ulaşım İhtiyacı", opt_ulasim, index=idx_ulasim)

            # Notlar Kısmı (Geniş)
            st.markdown("##### 📝 Notlar")
            c_not1, c_not2 = st.columns(2)
            yeni_referans = c_not1.text_input("Referans (Kim ilgileniyor?)", value=kisi['Referans'])
            yeni_cizik = c_not2.text_input("Çizikler / Rakip Ekleme", value=kisi['Cizikler']) # Cizikler sütununu kullanıyoruz notlar için

            kaydet_btn = st.form_submit_button("✅ BİLGİLERİ KAYDET")

            if kaydet_btn:
                try:
                    # Sütun İsimlerine Göre Güncelleme (Hata Riskini Sıfırlar)
                    headers = df.columns.tolist()
                    
                    updates = [
                        ("Kurum", yeni_kurum),
                        ("Gecmis_2024", yeni_24),
                        ("Gecmis_2022", yeni_22),
                        ("Egilim", yeni_egilim),
                        ("Temas_Durumu", yeni_temas),
                        ("Ulasim", yeni_ulasim),
                        ("Referans", yeni_referans),
                        ("Cizikler", yeni_cizik),
                        ("Son_Guncelleyen", user['Kullanici_Adi']) # Veriyi giren kişi
                    ]
                    
                    for col_name, value in updates:
                        if col_name in headers:
                            col_idx = headers.index(col_name) + 1
                            ws.update_cell(row_num, col_idx, value)
                    
                    st.success(f"{kisi['Ad_Soyad']} başarıyla güncellendi!")
                    # Anında ekranı yenilemek için boşluk bırakma, direkt rerun yap
                    
                except Exception as e:
                    st.error(f"Hata oluştu: {e}")
