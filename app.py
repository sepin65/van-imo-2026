import streamlit as st
import pandas as pd
import gspread
import plotly.express as px
import plotly.graph_objects as go
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import time
import math

# --- SAYFA AYARLARI (EN BAŞTA OLMALI) ---
st.set_page_config(
    page_title="İMO Van 2026 - Karargah", 
    layout="wide", 
    page_icon="🏗️",
    initial_sidebar_state="collapsed"
)

# --- 1. BAĞLANTIYI KUR ---
@st.cache_resource
def get_connection():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    return client

# --- 2. VERİLERİ ÇEK VE İŞLE ---
def get_data():
    client = get_connection()
    try:
        sheet = client.open("Van_IMO_Secim_2026")
        ws = sheet.worksheet("secmenler")
        all_data = ws.get_all_values()
        
        if len(all_data) > 1:
            headers = [h.strip() for h in all_data[0]]
            rows = all_data[1:]
            # Boş sütun başlıklarını onar
            cleaned_headers = [h if h != "" else f"Bos_Sutun_{i}" for i, h in enumerate(headers)]
            df = pd.DataFrame(rows, columns=cleaned_headers)
        else:
            return pd.DataFrame(), None, pd.DataFrame(), None

        # Sütun İsimlerini Eşleştir (Türkçe -> Kod)
        rename_map = {
            'Üniversite': 'Universite',
            'Doğum_Tarihi': 'Dogum_Yili',
            'Eğilim': 'Egilim',
            'Ulaşım': 'Ulasim',
            'Temsilcilik': 'Temsilcilik'
        }
        df.rename(columns=rename_map, inplace=True)

        required_cols = ['Referans', 'Sandik_No', 'Egilim', 'Kurum', 'Ad_Soyad', 'Sicil_No', 'Temas_Durumu', 'Ulasim', 'Cizikler', 'Rakip_Ekleme', 'Gecmis_2024', 'Gecmis_2022', 'Telefon', 'Universite', 'Dogum_Yili', 'Temsilcilik']
        for col in required_cols:
            if col not in df.columns: df[col] = ""

        # --- VERİ TEMİZLİĞİ ---
        
        # 1. Temsilcilik Düzeltme
        def fix_location(x):
            x = str(x).strip().upper()
            if x in ["-", "", "NONE", "NAN"] or len(x) < 3: return "VAN MERKEZ"
            return x
        df['Temsilcilik'] = df['Temsilcilik'].apply(fix_location)

        # 2. Üniversite Düzeltme
        df['Universite'] = df['Universite'].str.upper().str.strip()

        # 3. Yaş Hesaplama
        current_year = datetime.now().year
        def get_age(val):
            val = str(val).strip()
            try:
                year = 0
                if "/" in val: year = int(val.split("/")[-1])
                elif "." in val: year = int(val.split(".")[-1])
                elif len(val) == 4 and val.isdigit(): year = int(val)
                
                if 1930 < year < current_year: return current_year - year
                return 0
            except: return 0
        df['Yas'] = df['Dogum_Yili'].apply(get_age)

        def group_age(age):
            if age == 0: return "Belirsiz"
            if age < 30: return "20-29 (Genç)"
            if age < 40: return "30-39 (Dinamik)"
            if age < 50: return "40-49 (Olgun)"
            if age < 60: return "50-59 (Kıdemli)"
            return "60+ (Duayen)"
        df['Yas_Grubu'] = df['Yas'].apply(group_age)

        # 4. Sicil
        def clean_sicil(x):
            try: return int(str(x).replace(".", "").replace(" ", ""))
            except: return 999999 
        df['Sicil_Int'] = df['Sicil_No'].apply(clean_sicil)
        df = df.sort_values(by='Sicil_Int')
        
        # 5. Sandık
