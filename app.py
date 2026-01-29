import streamlit as st
import pandas as pd
import gspread
import plotly.express as px
import plotly.graph_objects as go
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import time
import math

# --- SAYFA AYARLARI ---
st.set_page_config(
    page_title="İMO Van 2026", 
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
            cleaned_headers = [h if h != "" else f"Bos_Sutun_{i}" for i, h in enumerate(headers)]
            df = pd.DataFrame(rows, columns=cleaned_headers)
        else:
            return pd.DataFrame(), None, pd.DataFrame(), None

        # Sütun İsimlerini Eşleştir (Türkçe -> Kod)
        rename_map = {
            'Üniversite': 'Universite',
            'Doğum_Tarihi': 'Dogum_Yili',
            'Doğum_Yeri': 'Dogum_Yeri', # Yeni Eklendi
            'Eğilim': 'Egilim',
            'Ulaşım': 'Ulasim'
        }
        df.rename(columns=rename_map, inplace=True)

        required_cols = ['Referans', 'Sandik_No', 'Egilim', 'Kurum', 'Ad_Soyad', 'Sicil_No', 'Temas_Durumu', 'Ulasim', 'Cizikler', 'Rakip_Ekleme', 'Gecmis_2024', 'Gecmis_2022', 'Telefon', 'Universite', 'Dogum_Yili', 'Dogum_Yeri', 'Temsilcilik']
        for col in required_cols:
            if col not in df.columns: df[col] = ""

        # --- VERİ TEMİZLİĞİ ---
        
        # 1. Temsilcilik
        def fix_location(x):
            x = str(x).strip()
            if x in ["-", "", "None", "nan"] or len(x) < 3: return "VAN MERKEZ"
            return x.upper()
        df['Temsilcilik'] = df['Temsilcilik'].apply(fix_location)

        # 2. Üniversite
        df['Universite'] = df['Universite'].str.upper().str.strip()
        
        # 3. Doğum Yeri (Şehir Bazlı)
        df['Dogum_Yeri'] = df['Dogum_Yeri'].str.upper().str.strip()

        # 4. Yaş Hesaplama
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

        # 5. YAŞ GRUPLAMA (5 YILLIK DETAYLI)
        def group_age_5(age):
            if age == 0: return "Belirsiz"
            if age < 25: return "20-24"
            if age < 30: return "25-29"
            if age < 35: return "30-34"
            if age < 40: return "35-39"
            if age < 45: return "40-44"
            if age < 50: return "45-49"
            if age < 55: return "50-54"
            if age < 60: return "55-59"
            if age < 65: return "60-64"
            return "65+"
            
        df['Yas_Grubu_5'] = df['Yas'].apply(group_age_5)

        # 6. Sicil ve Sandık
        def clean_sicil(x):
            try: return int(str(x).replace(".", "").replace(" ", ""))
            except: return 999999 
        df['Sicil_Int'] = df['Sicil_No'].apply(clean_sicil)
        df = df.sort_values(by='Sicil_Int')
        
        try:
            df['Sandik_No'] = pd.qcut(df['Sicil_Int'].rank(method='first'), q=6, labels=[
                "1. Sandık (En Kıdemliler)", "2. Sandık", "3. Sandık", 
                "4. Sandık", "5. Sandık", "6. Sandık (En Gençler)"
            ])
        except: df['Sandik_No'] = "Belirsiz"

        # --- LOGLAR ---
        try:
            ws_log = sheet.worksheet("log_kayitlari")
        except:
            ws_log = sheet.add_worksheet(title="log_kayitlari", rows="1000", cols="20")
        
        log_raw = ws_log.get_all_values()
        log_headers = ['Zaman', 'Sicil_No', 'Ad_Soyad', 'Kullanici', 'Kurum', 'Egilim', 'Gecmis_2024', 'Gecmis_2022', 'Temas_Durumu', 'Rakip_Ekleme', 'Ulasim', 'Cizikler']
        
        if not log_raw or (len(log_raw) > 0 and log_raw[0] != log_headers):
            if len(log_raw) < 5:
                ws_log.clear()
                ws_log.append_row(log_headers)
                df_log = pd.DataFrame(columns=log_headers)
            else:
                 h = log_raw[0]
                 clean_h = [x if x.strip() != "" else f"Bos_{i}" for i, x in enumerate(h)]
                 df_log = pd.DataFrame(log_raw[1:], columns=clean_h)
        else:
            df_log = pd.DataFrame(log_raw[1:], columns=log_raw[0])

        if not df_log.empty and 'Sicil_No' in df_log.columns:
            df_log['Sicil_No'] = df_log['Sicil_No'].astype(str)

        return df, ws, df_log, ws_log
    except Exception as e:
        return pd.DataFrame(), None, pd.DataFrame(), None

# --- GİRİŞ ---
if 'user' not in st.session_state: st.session_state.user = None
if st.session_state.user is None:
    st.title("🏗️ İMO SEÇİM SİSTEMİ")
    with st.form("giris"):
        kadi = st.text_input("Kullanıcı Adı")
        sifre = st.text_input("Şifre", type="password")
        if st.form_submit_button("Giriş Yap"):
            try:
                client = get_connection()
                sheet = client.open("Van_IMO_Secim_2026")
                users = sheet.worksheet("kullanicilar").get_all_records()
                df_users = pd.DataFrame(users)
                login = df_users[df_users['Kullanici_Adi'] == kadi]
                if not login.empty and str(login.iloc[0]['Sifre']) == sifre:
                    st.session_state.user = login.iloc[0].to_dict()
                    st.rerun()
                else: st.error("Hatalı Giriş")
            except: st.error("Bağlantı Hatası")
    st.stop()

# --- POP-UP FORM ---
@st.dialog("✏️ SEÇMEN KARTI")
def entry_form_dialog(kisi, row_n, sicil, user, df_cols, ws, ws_log, df_log):
    st.markdown(f"### 👤 {kisi['Ad_Soyad']}")
    
    yas = kisi.get('Yas', 0)
    uni = kisi.get('Universite', '')
    temsil = kisi.get('Temsilcilik', 'VAN MERKEZ')
    dyeri = kisi.get('Dogum_Yeri', '')
    
    c1, c2, c3 = st.columns(3)
    c1.info(f"📍 **{temsil}**")
    c2.info(f"🎓 **{uni if len(uni)>2 else '-'}**")
    c3.info(f"🎂 **{int(yas) if yas > 0 else '?'} Yaş** ({dyeri})")
    
    is_admin = (user['Rol'] == 'ADMIN')
    def get(f): return kisi.get(f, "") if is_admin else ""

    st.markdown("##### 🕒 Geçmiş Hareketler")
    if df_log is not None and not df_log.empty and 'Sicil_No' in df_log.columns:
        logs = df_log[df_log['Sicil_No'].astype(str).str.strip() == str(sicil).strip()]
        if not logs.empty:
            st.dataframe(logs[['Zaman','Kullanici','Egilim','Cizikler']].sort_values('Zaman', ascending=False), hide_index=True, use_container_width=True)
        else: st.caption("Kayıt yok.")
    
    with st.form("form"):
        c1, c2 = st.columns(2)
        with c1:
            k_opt = ["", "Özel Sektör", "Dsi", "Karayolları", "Büyükşehir", "Vaski", "Projeci", "Yapı Denetimci", "İlçe Belediyeleri", "Müteahhit", "Yapsat", "Çevre Şehircilik", "Emekli", "Diğer"]
            nk = st.selectbox("Kurum", k_opt, index=k_opt.index(kisi.get('Kurum',"")) if kisi.get('Kurum',"") in k_opt else 0)
            n24 = st.selectbox("2024", ["", "Sarı Liste", "Mavi Liste"], index=["", "Sarı Liste", "Mavi Liste"].index(get('Gecmis_2024')) if get('Gecmis_2024') in ["", "Sarı Liste", "Mavi Liste"] else 0)
            n22 = st.selectbox("2022", ["", "Sarı Liste", "Mavi Liste", "Beyaz Liste"], index=["", "Sarı Liste", "Mavi Liste", "Beyaz Liste"].index(get('Gecmis_2022')) if get('Gecmis_2022') in ["", "Sarı Liste", "Mavi Liste", "Beyaz Liste"] else 0)
        with c2:
            e_opt = ["", "Tüm Listemizi Yazar", "Büyük Kısmı Yazar", "Kısmen Yazar", "Karşı Tarafı Destekler", "Kararsızım"]
            ne = st.selectbox("2026 EĞİLİMİ", e_opt, index=e_opt.index(get('Egilim')) if get('Egilim') in e_opt else 0)
            nt = st.selectbox("Temas", ["", "Kendim Görüştüm", "Arkadaşım/Akraba Aracılığı", "Tanımıyorum"], index=["", "Kendim Görüştüm", "Arkadaşım/Akraba Aracılığı", "Tanımıyorum"].index(get('Temas_Durumu')) if get('Temas_Durumu') in ["", "Kendim Görüştüm", "Arkadaşım/Akraba Aracılığı", "Tanımıyorum"] else 0)
            nu = st.selectbox("Ulaşım", ["", "Kendisi Gelir", "Araç Gerekir", "İlçeden Gelecek"], index=["", "Kendisi Gelir", "Araç Gerekir", "İlçeden Gelecek"].index(get('Ulasim')) if get('Ulasim') in ["", "Kendisi Gelir", "Araç Gerekir", "İlçeden Gelecek"] else 0)

        nn = st.text_area("Notlar", value=get('Cizikler'))
        nr = st.text_input("Rakip Ekleme", value=get('Rakip_Ekleme'))
        nref = st.text_input("Referans", value=get('Referans'))
        
        c_ex1, c_ex2 = st.columns(2)
        n_uni = c_ex1.text_input("Üniversite Düzelt", value=kisi.get('Universite', ''))
        n_temsil = c_ex2.text_input("Temsilcilik Düzelt", value=kisi.get('Temsilcilik', ''))

        if st.form_submit_button("✅ KAYDET"):
            updates = [
                ("Kurum", nk), ("Gecmis_2024", n24), ("Gecmis_2022", n22),
                ("Egilim", ne), ("Temas_Durumu", nt), ("Ulasim", nu),
                ("Cizikler", nn), ("Rakip_Ekleme", nr), ("Referans", nref),
                ("Universite", n_uni), ("Temsilcilik", n_temsil),
                ("Son_Guncelleyen", user['Kullanici_Adi'])
            ]
            for col, val in updates:
                target = col
                if col == 'Universite' and 'Üniversite' in df_cols: target = 'Üniversite'
                if col == 'Temsilcilik' and 'Temsilcilik' in df_cols: target = 'Temsilcilik'
                if col in df_cols: ws.update_cell(row_n, df_cols.index(col)+1, val)
                elif target in df_cols: ws.update_cell(row_n, df_cols.index(target)+1, val)
            
            if ws_log:
                ws_log.append_row([datetime.now().strftime("%Y-%m-%d %H:%M"), str(sicil), kisi['Ad_Soyad'], user['Kullanici_Adi'], nk, ne, n24, n22, nt, nr, nu, nn])
            st.toast("Kaydedildi!", icon="💾")
            time.sleep(1)
            st.rerun()

# --- ANA EKRAN ---
user = st.session_state.user
df, ws, df_log, ws_log = get_data()
if df.empty:
    st.warning("Veriler yükleniyor...")
    st.stop()

menu = st.sidebar.radio("Menü", ["📊 ANALİZ RAPORU", "🎓 DEMOGRAFİK ANALİZ", "📝 Veri Girişi"] if user['Rol']=='ADMIN' else ["📝 Veri Girişi"])

# =========================================================
# 🎓 DEMOGRAFİK ANALİZ (DERİNLEMESİNE)
# =========================================================
if menu == "🎓 DEMOGRAFİK ANALİZ":
    st.title("🎓 Üniversite Bazlı Derin Analiz")
    st.caption("Aşağıdan bir üniversite seçerek o okulun mezun profilini (Yaş, Doğum Yeri, Temsilcilik) detaylı inceleyebilirsiniz.")

    # 1. ÜNİVERSİTE SEÇİMİ
    if 'Universite' in df.columns:
        uni_list = sorted([u for u in df['Universite'].unique() if len(str(u)) > 2])
        selected_uni = st.selectbox("🏛️ Hangi Üniversiteyi Analiz Etmek İstersiniz?", ["TÜMÜ"] + uni_list)
        
        # Veriyi Filtrele
        if selected_uni == "TÜMÜ":
            df_filtered = df[df['Universite'].str.len() > 2]
            title_prefix = "GENEL"
        else:
            df_filtered = df[df['Universite'] == selected_uni]
            title_prefix = selected_uni

        st.divider()
        st.markdown(f"### 🔎 {title_prefix} MEZUNLARI ANALİZİ ({len(df_filtered)} Kişi)")

        # 3 KOLONLU GÖRSELLEŞTİRME
        c1, c2, c3 = st.columns(3)

        # GRAFİK 1: YAŞ DAĞILIMI (5 Yıllık)
        with c1:
            st.subheader("🎂 Yaş Dağılımı")
            if 'Yas_Grubu_5' in df.columns and not df_filtered.empty:
                age_counts = df_filtered['Yas_Grubu_5'].value_counts().reset_index()
                age_counts.columns = ['Yaş Aralığı', 'Kişi']
                # Sıralama (Küçükten büyüğe görünmesi için)
                age_order = ["20-24", "25-29", "30-34", "35-39", "40-44", "45-49", "50-54", "55-59", "60-64", "65+", "Belirsiz"]
                fig_age = px.bar(age_counts, x='Yaş Aralığı', y='Kişi', category_orders={"Yaş Aralığı": age_order}, title="5 Yıllık Dilimler")
                st.plotly_chart(fig_age, use_container_width=True)
            else:
                st.warning("Veri yok.")

        # GRAFİK 2: DOĞUM YERİ (Memleketçilik Analizi)
        with c2:
            st.subheader("👶 Doğum Yeri")
            if 'Dogum_Yeri' in df.columns and not df_filtered.empty:
                # Sadece ilk 10 şehri göster, gerisini 'Diğer' yap ki grafik boğulmasın
                dy_counts = df_filtered['Dogum_Yeri'].value_counts().reset_index()
                dy_counts.columns = ['Şehir', 'Kişi']
                fig_dy = px.pie(dy_counts.head(10), values='Kişi', names='Şehir', hole=0.4, title="Doğdukları Şehirler")
                st.plotly_chart(fig_dy, use_container_width=True)
            else:
                st.warning("Doğum yeri verisi eksik.")

        # GRAFİK 3: TEMSİLCİLİK (Neredeler?)
        with c3:
            st.subheader("📍 Temsilcilik")
            if 'Temsilcilik' in df.columns and not df_filtered.empty:
                loc_counts = df_filtered['Temsilcilik'].value_counts().reset_index()
                loc_counts.columns = ['Bölge', 'Kişi']
                fig_loc = px.pie(loc_counts, values='Kişi', names='Bölge', hole=0.4, title="Bulundukları Bölge")
                st.plotly_chart(fig_loc, use_container_width=True)
            else:
                st.warning("Temsilcilik verisi eksik.")
                
        # DETAYLI LİSTE (İsteğe Bağlı Açılır)
        with st.expander(f"📋 {title_prefix} Mezunu Olan Üyelerin Listesini Gör"):
            st.dataframe(df_filtered[['Sicil_No', 'Ad_Soyad', 'Dogum_Yeri', 'Yas', 'Temsilcilik', 'Kurum']], use_container_width=True)

    else:
        st.error("Excel dosyasında 'Üniversite' sütunu bulunamadı.")

# =========================================================
# ANALİZ RAPORU
# =========================================================
elif menu == "📊 ANALİZ RAPORU":
    st.title("📊 Genel Durum")
    temas = df[df['Egilim'].str.len() > 1]
    bizimkiler = temas[temas['Egilim'].isin(["Tüm Listemizi Yazar", "Büyük Kısmı Yazar"])]
    c1, c2, c3 = st.columns(3)
    c1.metric("Toplam Üye", len(df))
    c2.metric("Temas Edilen", len(temas))
    c3.metric("Bizim Oylar", len(bizimkiler))
    st.divider()
    c_pie, c_bar = st.columns(2)
    with c_pie:
        if not temas.empty: st.plotly_chart(px.pie(temas, names='Egilim', title='Saha Durumu'), use_container_width=True)
    with c_bar:
        k_counts = bizimkiler['Kurum'].value_counts().reset_index()
        k_counts.columns = ['Kurum', 'Oylar']
        st.plotly_chart(px.bar(k_counts.head(10), x='Oylar', y='Kurum', orientation='h', title='En Güçlü Kurumlar'), use_container_width=True)

# =========================================================
# VERİ GİRİŞİ
# =========================================================
elif menu == "📝 Veri Girişi":
    st.header("📋 Seçmen Bilgi Girişi")
    if 'search_term' not in st.session_state: st.session_state.search_term = ""
    def update_search(): st.session_state.search_term = st.session_state.widget_search
    search = st.text_input("🔍 İsim Ara", value=st.session_state.search_term, key="widget_search", on_change=update_search)
    
    cols = ['Sicil_No', 'Ad_Soyad', 'Universite', 'Temsilcilik', 'Kurum', 'Egilim', 'Son_Guncelleyen']
    final_cols = [c for c in cols if c in df.columns]

    if search:
        df_show = df[df['Ad_Soyad'].str.contains(search, case=False, na=False)]
    else:
        page_size = 20
        if 'page_number' not in st.session_state: st.session_state.page_number = 1
        total_pages = math.ceil(len(df)/page_size)
        c1, c2, c3 = st.columns([1,2,1])
        with c1: 
            if st.button("⬅️") and st.session_state.page_number > 1: st.session_state.page_number -= 1
        with c3:
            if st.button("➡️") and st.session_state.page_number < total_pages: st.session_state.page_number += 1
        with c2: 
            target = st.number_input("Sayfa", 1, total_pages, st.session_state.page_number)
            if target != st.session_state.page_number:
                st.session_state.page_number = target
                st.rerun()
        start = (st.session_state.page_number-1)*page_size
        df_show = df.iloc[start:start+page_size]

    event = st.dataframe(df_show[final_cols], use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row")
    if len(event.selection.rows) > 0:
        idx = event.selection.rows[0]
        sicil = df_show.iloc[idx]['Sicil_No']
        g_idx = df[df['Sicil_No'] == sicil].index[0]
        entry_form_dialog(df.iloc[g_idx], g_idx + 2, sicil, user, df.columns.tolist(), ws, ws_log, df_log)
