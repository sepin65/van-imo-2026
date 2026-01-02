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
        return pd.DataFrame(data), ws
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
                # Kullanıcılar sekmesinden yetki kontrolü
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
st.sidebar.info(f"👤 {user['Kullanici_Adi']} | Yetki: {user['Rol']}")

if st.sidebar.button("Çıkış"):
    st.session_state.user = None
    st.rerun()

df, ws = get_data()
if df.empty:
    st.warning("Veri yok veya bağlantı hatası.")
    st.stop()

# Yetki Bazlı Filtreleme (Saha Elemanı Sadece Kendi Bölgesini Görür)
# Eğer Mazlum 'Tümü' görsün istiyorsan Excel'den Mazlum'un bölgesini 'Tümü' yapabilirsin.
if user['Rol'] == 'SAHA' and user['Bolge_Yetkisi'] != 'Tümü':
    df = df[df['Temsilcilik'] == user['Bolge_Yetkisi']]

menu = st.sidebar.radio("Menü", ["📊 Analiz Paneli", "📝 Veri Girişi"])

# --- 1. ANALİZ PANELİ ---
if menu == "📊 Analiz Paneli":
    st.title("📊 Seçim Durum Analizi")
    
    col1, col2, col3 = st.columns(3)
    toplam = len(df)
    ulasilan = len(df[df['Egilim'].astype(str) != ""])
    
    col1.metric("Toplam Seçmen", toplam)
    col2.metric("Ulaşılan", ulasilan, f"%{int(ulasilan/toplam*100) if toplam else 0}")
    
    if ulasilan > 0:
        fig = px.pie(df, names='Egilim', title='Oy Dağılımı', hole=0.4)
        st.plotly_chart(fig)
        
        if 'Temsilcilik' in df.columns:
            st.subheader("Bölge Bazlı Durum")
            bolge_chart = px.bar(df, x='Temsilcilik', color='Egilim')
            st.plotly_chart(bolge_chart)
    else:
        st.info("Henüz veri girişi yapılmamış.")

# --- 2. VERİ GİRİŞİ (YENİ SİSTEM: LİSTEDEN SEÇMELİ) ---
elif menu == "📝 Veri Girişi":
    st.header("📝 Listeden Kişi Seçin")
    
    if user['Rol'] == 'GOZLEM':
        st.warning("Gözlemciler veri girişi yapamaz.")
    else:
        st.info("👇 Aşağıdaki listeden işlem yapmak istediğiniz kişinin üzerine tıklayın.")

        # --- TIKLANABİLİR TABLO AYARLARI ---
        # Tabloyu oluşturuyoruz ve seçilebilir yapıyoruz
        event = st.dataframe(
            df[['Sicil_No', 'Ad_Soyad', 'Temsilcilik', 'Egilim']], # Sadece önemli sütunları göster
            use_container_width=True,
            hide_index=True,
            on_select="rerun",  # Tıklayınca sayfayı yenile
            selection_mode="single-row" # Sadece tek kişi seçilebilsin
        )

        # Eğer listeden biri seçildiyse:
        if len(event.selection.rows) > 0:
            # Seçilen satırın numarasını al
            selected_index = event.selection.rows[0]
            
            # O satırdaki kişinin tüm verilerini çek
            kisi = df.iloc[selected_index]
            
            # Excel'deki gerçek satır numarasını bul (Sicil No üzerinden eşleştirme yaparak)
            # Bu işlem sıralama değişse bile doğru kişiyi bulmamızı sağlar
            gercek_index = df[df['Sicil_No'] == kisi['Sicil_No']].index[0]
            row_num = gercek_index + 2 # Excel başlık payı

            st.divider()
            st.markdown(f"### 👤 Seçilen: **{kisi['Ad_Soyad']}**")
            st.caption(f"Sicil: {kisi['Sicil_No']} | Bölge: {kisi['Temsilcilik']}")

            with st.form("guncelle", border=True):
                c1, c2 = st.columns(2)
                with c1:
                    opt_egilim = ["", "🟡 SARI BLOK", "🟠 KARMA", "🔴 RAKİP", "⚪ KARARSIZ"]
                    curr_egilim = kisi['Egilim']
                    def_idx = opt_egilim.index(curr_egilim) if curr_egilim in opt_egilim else 0
                    
                    yeni_egilim = st.selectbox("Oy Eğilimi", opt_egilim, index=def_idx)
                    
                    # Ulaşım kontrolü (Hata vermemesi için)
                    mevcut_ulasim = kisi['Ulasim'] if 'Ulasim' in kisi else ""
                    ulasim_secenekleri = ["Kendi İmkanı", "Otobüs Lazım"]
                    ulasim_index = 1 if "Otobüs" in str(mevcut_ulasim) else 0
                    yeni_ulasim = st.selectbox("Ulaşım", ulasim_secenekleri, index=ulasim_index)

                with c2:
                    yeni_rakip = st.text_input("Rakip Ekleme", value=str(kisi['Rakip_Ekleme']))
                    yeni_cizik = st.text_input("Çizikler (Kimi Çizecek?)", value=str(kisi['Cizikler']))
                
                kaydet = st.form_submit_button("✅ BİLGİLERİ KAYDET")
                
                if kaydet:
                    try:
                        # Sütun yerlerini bul
                        col_egilim = df.columns.get_loc("Egilim") + 1
                        col_ulasim = df.columns.get_loc("Ulasim") + 1
                        col_rakip = df.columns.get_loc("Rakip_Ekleme") + 1
                        col_cizik = df.columns.get_loc("Cizikler") + 1
                        col_son = df.columns.get_loc("Son_Guncelleyen") + 1
                        
                        # Excel'i güncelle
                        ws.update_cell(row_num, col_egilim, yeni_egilim)
                        ws.update_cell(row_num, col_ulasim, yeni_ulasim)
                        ws.update_cell(row_num, col_rakip, yeni_rakip)
                        ws.update_cell(row_num, col_cizik, yeni_cizik)
                        ws.update_cell(row_num, col_son, user['Kullanici_Adi'])
                        
                        st.success(f"{kisi['Ad_Soyad']} güncellendi! Listeden sıradaki kişiye geçebilirsiniz.")
                        
                        # 2 saniye bekleme koymuyoruz ki seri olsun, ama istersen koyabiliriz.
                    except Exception as e:
                        st.error(f"Hata oluştu: {e}")
