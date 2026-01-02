import streamlit as st
import pandas as pd
import gspread
import plotly.express as px
import plotly.graph_objects as go
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import pytz

# Sayfa Ayarları
st.set_page_config(page_title="İMO Van 2026 - Komuta Merkezi", layout="wide", page_icon="🏗️")

# --- 1. BAĞLANTIYI KUR ---
@st.cache_resource
def get_connection():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    return client

# --- 2. VERİLERİ ÇEK ---
def get_data():
    client = get_connection()
    try:
        sheet = client.open("Van_IMO_Secim_2026")
        
        # Ana Liste
        ws = sheet.worksheet("secmenler")
        data = ws.get_all_records()
        df = pd.DataFrame(data)
        df.columns = df.columns.str.strip()
        df = df.astype(str)
        
        # Log Kayıtları
        try:
            ws_log = sheet.worksheet("log_kayitlari")
            data_log = ws_log.get_all_records()
            df_log = pd.DataFrame(data_log)
        except:
            df_log = pd.DataFrame()
            ws_log = None
            
        return df, ws, df_log, ws_log
    except Exception as e:
        return None, None, None, None

# --- 3. GİRİŞ EKRANI ---
if 'user' not in st.session_state:
    st.session_state.user = None

if st.session_state.user is None:
    st.title("🏗️ İMO SEÇİM KOMUTA MERKEZİ")
    with st.form("giris_formu"):
        kadi = st.text_input("Kullanıcı Adı")
        sifre = st.text_input("Şifre", type="password")
        # BUTON FORMUN İÇİNDE
        if st.form_submit_button("Giriş Yap"):
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
                    st.error("❌ Hatalı Giriş")
            except Exception as e:
                st.error(f"Hata: {e}")
    st.stop()

# --- 4. ANA PROGRAM ---
user = st.session_state.user
st.sidebar.success(f"👮‍♂️ {user['Kullanici_Adi']} ({user['Rol']})")
if st.sidebar.button("Çıkış"):
    st.session_state.user = None
    st.rerun()

df, ws, df_log, ws_log = get_data()

if df is None:
    st.error("Veri alınamadı. Sayfayı yenileyin.")
    st.stop()

menu = st.sidebar.radio("Menü", ["📊 360° DERİN ANALİZ", "📝 Seçmen Kartı & Giriş"])

# =========================================================
# EKRAN 1: 360 DERECE DERİN ANALİZ (İSTATİSTİK CANAVARI)
# =========================================================
if menu == "📊 360° DERİN ANALİZ":
    st.title("📊 STRATEJİK İSTİHBARAT RAPORU")
    
    # --- VERİ HAZIRLIĞI ---
    toplam_uye = len(df)
    temas_df = df[df['Egilim'].str.len() > 1]
    temas_sayisi = len(temas_df)
    temas_orani = int(temas_sayisi / toplam_uye * 100) if toplam_uye else 0
    
    # Bizimkiler
    bizimkiler = temas_df[temas_df['Egilim'].isin(["Tüm Listemizi Yazar", "Büyük Kısmı Yazar"])]
    bizim_sayi = len(bizimkiler)
    
    # Sicil Analizi için Sayısal Dönüşüm
    def clean_sicil(x):
        try:
            return int(str(x).replace(".", ""))
        except:
            return 0
    
    temas_df = temas_df.copy()
    temas_df['Sicil_Int'] = temas_df['Sicil_No'].apply(clean_sicil)

    # --- ÜST METRİKLER ---
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Toplam Üye", toplam_uye)
    c2.metric("Sahada Dokunulan", temas_sayisi, f"%{temas_orani}")
    c3.metric("🟡 KEMİK OYUMUZ", bizim_sayi, f"Temasın %{int(bizim_sayi/temas_sayisi*100) if temas_sayisi else 0}'i")
    c4.metric("Kalan Hedef", toplam_
