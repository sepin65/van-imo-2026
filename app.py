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

# --- 2. VERİLERİ ÇEK ---
def get_data():
    client = get_connection()
    try:
        sheet = client.open("Van_IMO_Secim_2026")
        
        # --- ANA LİSTE ---
        ws = sheet.worksheet("secmenler")
        all_data = ws.get_all_values()
        
        if len(all_data) > 1:
            headers = all_data[0]
            rows = all_data[1:]
            cleaned_headers = [h if h.strip() != "" else f"Bos_Sutun_{i}" for i, h in enumerate(headers)]
            df = pd.DataFrame(rows, columns=cleaned_headers)
        else:
            df = pd.DataFrame()

        # Sütun Temizliği
        df.columns = df.columns.str.strip()
        df = df.astype(str)
        
        # YENİ SÜTUNLAR EKLENDİ: Universite, Dogum_Yili, Temsilcilik
        required_cols = ['Referans', 'Sandik_No', 'Egilim', 'Kurum', 'Ad_Soyad', 'Sicil_No', 'Temas_Durumu', 'Ulasim', 'Cizikler', 'Rakip_Ekleme', 'Gecmis_2024', 'Gecmis_2022', 'Telefon', 'Universite', 'Dogum_Yili', 'Temsilcilik']
        for col in required_cols:
            if col not in df.columns:
                df[col] = ""

        # Sicil Temizleme
        def clean_sicil(x):
            try:
                return int(str(x).replace(".", "").replace(" ", ""))
            except:
                return 999999 
        df['Sicil_Int'] = df['Sicil_No'].apply(clean_sicil)
        df = df.sort_values(by='Sicil_Int')
        
        # Yaş Hesaplama
        current_year = datetime.now().year
        def calculate_age(year):
            try:
                y = int(str(year).strip())
                if 1940 < y < current_year: return current_year - y
                return 0
            except:
                return 0
        
        df['Yas'] = df['Dogum_Yili'].apply(calculate_age)
        
        # Yaş Gruplama
        def group_age(age):
            if age == 0: return "Belirsiz"
            if age < 30: return "20-29 (Genç)"
            if age < 40: return "30-39 (Dinamik)"
            if age < 50: return "40-49 (Olgun)"
            if age < 60: return "50-59 (Kıdemli)"
            return "60+ (Duayen)"
            
        df['Yas_Grubu'] = df['Yas'].apply(group_age)

        # Sandık Atama
        try:
            df['Sandik_No'] = pd.qcut(df['Sicil_Int'].rank(method='first'), q=6, labels=[
                "1. Sandık (Kıdemliler)", "2. Sandık", "3. Sandık", 
                "4. Sandık", "5. Sandık", "6. Sandık (Gençler)"
            ])
        except:
            df['Sandik_No'] = "Belirsiz"

        # --- LOG KAYITLARI ---
        try:
            ws_log = sheet.worksheet("log_kayitlari")
        except:
            ws_log = sheet.add_worksheet(title="log_kayitlari", rows="1000", cols="20")
        
        log_data_raw = ws_log.get_all_values()
        correct_headers = ['Zaman', 'Sicil_No', 'Ad_Soyad', 'Kullanici', 'Kurum', 'Egilim', 'Gecmis_2024', 'Gecmis_2022', 'Temas_Durumu', 'Rakip_Ekleme', 'Ulasim', 'Cizikler']
        
        if not log_data_raw or (len(log_data_raw) > 0 and log_data_raw[0] != correct_headers):
            if len(log_data_raw) < 5:
                ws_log.clear()
                ws_log.append_row(correct_headers)
                df_log = pd.DataFrame(columns=correct_headers)
            else:
                 headers = log_data_raw[0]
                 cleaned_log_headers = [h if h.strip() != "" else f"Bos_{i}" for i, h in enumerate(headers)]
                 df_log = pd.DataFrame(log_data_raw[1:], columns=cleaned_log_headers)
        else:
            df_log = pd.DataFrame(log_data_raw[1:], columns=log_data_raw[0])

        if not df_log.empty and 'Sicil_No' in df_log.columns:
            df_log['Sicil_No'] = df_log['Sicil_No'].astype(str)

        return df, ws, df_log, ws_log
    except Exception as e:
        return pd.DataFrame(), None, pd.DataFrame(), None

# --- SAYAÇ ---
def get_countdown():
    try:
        target = datetime(2026, 2, 14)
        return (target - datetime.now()).days
    except:
        return 400

# --- 3. GİRİŞ ---
if 'user' not in st.session_state: st.session_state.user = None

if st.session_state.user is None:
    st.title("🏗️ İMO SEÇİM SİSTEMİ")
    gun = get_countdown()
    st.info(f"⏳ SEÇİME **{gun}** GÜN KALDI!")
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

# --- 4. POP-UP FORM ---
@st.dialog("✏️ SEÇMEN KARTI")
def entry_form_dialog(kisi, row_n, sicil, user, df_cols, ws, ws_log, df_log):
    st.markdown(f"### 👤 {kisi['Ad_Soyad']}")
    # Demografik Bilgi Gösterimi
    yas = kisi.get('Yas', 0)
    uni = kisi.get('Universite', '-')
    st.caption(f"🎓 {uni} | 🎂 {yas} Yaş | 📍 {kisi.get('Temsilcilik', 'Merkez')}")
    
    is_admin = (user['Rol'] == 'ADMIN')
    def get(f): return kisi.get(f, "") if is_admin else ""

    # Geçmiş Tablosu
    st.info("🕒 **Seçmen Hafızası:**")
    found = False
    if not df_log.empty and 'Sicil_No' in df_log.columns:
        logs = df_log[df_log['Sicil_No'].astype(str).str.strip() == str(sicil).strip()]
        if not logs.empty:
            found = True
            st.dataframe(logs[['Zaman','Kullanici','Egilim','Cizikler']].sort_values('Zaman', ascending=False), hide_index=True)
    if not found: st.caption("Kayıt yok.")
    st.divider()
    
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
        
        # Telefon & Üniversite Güncelleme (Opsiyonel)
        c_extra1, c_extra2 = st.columns(2)
        with c_extra1:
             n_uni = st.text_input("Üniversite (Düzeltme)", value=kisi.get('Universite', ''))
        with c_extra2:
             n_temsil = st.text_input("Temsilcilik/İlçe", value=kisi.get('Temsilcilik', ''))

        if st.form_submit_button("✅ KAYDET"):
            updates = [
                ("Kurum", nk), ("Gecmis_2024", n24), ("Gecmis_2022", n22),
                ("Egilim", ne), ("Temas_Durumu", nt), ("Ulasim", nu),
                ("Cizikler", nn), ("Rakip_Ekleme", nr), ("Referans", nref),
                ("Universite", n_uni), ("Temsilcilik", n_temsil),
                ("Son_Guncelleyen", user['Kullanici_Adi'])
            ]
            for col, val in updates:
                if col in df_cols: ws.update_cell(row_n, df_cols.index(col)+1, val)
            
            if ws_log:
                ws_log.append_row([datetime.now().strftime("%Y-%m-%d %H:%M"), str(sicil), kisi['Ad_Soyad'], user['Kullanici_Adi'], nk, ne, n24, n22, nt, nr, nu, nn])
            st.toast("Kaydedildi!", icon="💾")

# --- 5. ANA EKRAN ---
user = st.session_state.user
df, ws, df_log, ws_log = get_data()
if df.empty: st.stop()

menu = st.sidebar.radio("Menü", ["📊 ANALİZ RAPORU", "🎓 DEMOGRAFİK ANALİZ", "📝 Veri Girişi"] if user['Rol']=='ADMIN' else ["📝 Veri Girişi"])

# =========================================================
# DEMOGRAFİK ANALİZ (YENİ SEKME)
# =========================================================
if menu == "🎓 DEMOGRAFİK ANALİZ":
    st.title("🎓 Stratejik Demografi Analizi")
    st.info("Bu ekran, elinizdeki üniversite, yaş ve temsilcilik verilerini analiz ederek 'Kime, Nasıl Konuşmalıyız?' sorusuna cevap verir.")

    tab1, tab2, tab3 = st.tabs(["🏛️ ÜNİVERSİTE LOBİSİ", "👶/👴 KUŞAK ANALİZİ", "📍 TEMSİLCİLİKLER"])

    with tab1:
        st.subheader("Hangi Okul Mezunları Çoğunlukta?")
        if 'Universite' in df.columns:
            # Boş olanları filtrele
            uni_df = df[df['Universite'].str.len() > 2]
            uni_counts = uni_df['Universite'].value_counts().reset_index()
            uni_counts.columns = ['Üniversite', 'Kişi Sayısı']
            
            c1, c2 = st.columns([2, 1])
            with c1:
                fig_uni = px.bar(uni_counts.head(15), x='Kişi Sayısı', y='Üniversite', orientation='h', title="En Çok Mezunu Olan Top 15 Üniversite", text_auto=True)
                fig_uni.update_layout(yaxis={'categoryorder':'total ascending'})
                st.plotly_chart(fig_uni, use_container_width=True)
            with c2:
                st.write("👉 **Strateji:** İlk 3 sıradaki üniversitelerden (Örn: KTÜ, YYÜ) sorumlu 'Abiler' belirleyin. O grubun oyları blok hareket edebilir.")
                st.dataframe(uni_counts, use_container_width=True)
        else:
            st.warning("Excel'de 'Universite' sütunu bulunamadı.")

    with tab2:
        st.subheader("Üye Yaş Dağılımı")
        if 'Yas_Grubu' in df.columns:
            age_counts = df['Yas_Grubu'].value_counts().reset_index()
            age_counts.columns = ['Yaş Grubu', 'Kişi Sayısı']
            
            c1, c2 = st.columns(2)
            with c1:
                fig_age = px.pie(age_counts, names='Yaş Grubu', values='Kişi Sayısı', title="Kuşak Dağılımı", hole=0.4)
                st.plotly_chart(fig_age, use_container_width=True)
            with c2:
                st.markdown("""
                **İletişim Stratejisi:**
                * **20-30 Yaş:** İş, maaş, sosyal etkinlik, dijitalleşme.
                * **30-50 Yaş:** Sektör sorunları, denetim, ihale.
                * **50+ Yaş:** İtibar, saygı, vefa, kurumsallık.
                """)
                if 'Yas' in df.columns:
                    avg_age = df[df['Yas'] > 0]['Yas'].mean()
                    st.metric("Oda Yaş Ortalaması", f"{int(avg_age)}")
        else:
            st.warning("Doğum Yılı verisi olmadığı için yaş hesaplanamadı.")

    with tab3:
        st.subheader("İlçe ve Temsilcilik Dağılımı")
        if 'Temsilcilik' in df.columns:
            rep_df = df[df['Temsilcilik'].str.len() > 2]
            rep_counts = rep_df['Temsilcilik'].value_counts().reset_index()
            rep_counts.columns = ['Bölge', 'Üye Sayısı']
            
            fig_rep = px.bar(rep_counts, x='Bölge', y='Üye Sayısı', color='Üye Sayısı', title="Bölgesel Güç Haritası", text_auto=True)
            st.plotly_chart(fig_rep, use_container_width=True)
            st.info("💡 Üye sayısı 20'nin üzerinde olan ilçelere özel araç/minibüs, 100'ün üzerinde olanlara otobüs kaldırılmalı.")

# =========================================================
# ANALİZ RAPORU (ESKİ EKRAN)
# =========================================================
elif menu == "📊 ANALİZ RAPORU":
    # ... (Buraya eski analiz kodları gelecek, yer kazanmak için kısa tuttum, 
    # V18'deki analiz kodları aynen kalabilir)
    st.title("📊 Genel Durum")
    temas = df[df['Egilim'].str.len() > 1]
    bizimkiler = temas[temas['Egilim'].isin(["Tüm Listemizi Yazar", "Büyük Kısmı Yazar"])]
    c1, c2, c3 = st.columns(3)
    c1.metric("Toplam Üye", len(df))
    c2.metric("Temas Edilen", len(temas))
    c3.metric("Bizim Oylar", len(bizimkiler))
    
    tabs = st.tabs(["GENEL", "SANDIKLAR", "KURUMLAR", "HEDEF"])
    with tabs[0]:
        st.plotly_chart(px.pie(temas, names='Egilim', title='Saha Durumu'), use_container_width=True)

# =========================================================
# VERİ GİRİŞİ
# =========================================================
elif menu == "📝 Veri Girişi":
    st.header("📋 Seçmen Bilgi Girişi")
    if 'search_term' not in st.session_state: st.session_state.search_term = ""
    def update_search(): st.session_state.search_term = st.session_state.widget_search
    search = st.text_input("🔍 İsim Ara", value=st.session_state.search_term, key="widget_search", on_change=update_search)
    
    cols = ['Sicil_No', 'Ad_Soyad', 'Universite', 'Temsilcilik', 'Kurum', 'Egilim', 'Son_Guncelleyen']
    
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
        with c2: st.markdown(f"**{st.session_state.page_number}/{total_pages}**")
        start = (st.session_state.page_number-1)*page_size
        df_show = df.iloc[start:start+page_size]

    event = st.dataframe(df_show[cols], use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row")
    if len(event.selection.rows) > 0:
        idx = event.selection.rows[0]
        sicil = df_show.iloc[idx]['Sicil_No']
        g_idx = df[df['Sicil_No'] == sicil].index[0]
        entry_form_dialog(df.iloc[g_idx], g_idx + 2, sicil, user, df.columns.tolist(), ws, ws_log, df_log)
