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

# --- 2. VERİLERİ ÇEK (AKILLI DÜZELTME MODU) ---
def get_data():
    client = get_connection()
    try:
        sheet = client.open("Van_IMO_Secim_2026")
        
        # --- ANA LİSTE ---
        ws = sheet.worksheet("secmenler")
        all_data = ws.get_all_values()
        
        if len(all_data) > 1:
            headers = all_data[0]
            # Başlıklardaki boşlukları temizle
            headers = [h.strip() for h in headers]
            rows = all_data[1:]
            
            # Boş başlıkları "Bos_Sutun" olarak adlandır
            cleaned_headers = [h if h != "" else f"Bos_Sutun_{i}" for i, h in enumerate(headers)]
            df = pd.DataFrame(rows, columns=cleaned_headers)
        else:
            return pd.DataFrame(), None, pd.DataFrame(), None

        # --- KRİTİK DÜZELTME: SÜTUN İSİMLERİNİ EŞLEŞTİRME ---
        # Excel'deki Türkçe isimleri, kodun beklediği İngilizce isimlere çeviriyoruz
        rename_map = {
            'Üniversite': 'Universite',
            'Doğum_Tarihi': 'Dogum_Yili', # Tarihi alıp yılı biz çekeceğiz
            'Dogum_Tarihi': 'Dogum_Yili',
            'Eğilim': 'Egilim',
            'Ulaşım': 'Ulasim'
        }
        df.rename(columns=rename_map, inplace=True)

        # Eksik sütunları oluştur (Hata vermemesi için)
        required_cols = ['Referans', 'Sandik_No', 'Egilim', 'Kurum', 'Ad_Soyad', 'Sicil_No', 'Temas_Durumu', 'Ulasim', 'Cizikler', 'Rakip_Ekleme', 'Gecmis_2024', 'Gecmis_2022', 'Telefon', 'Universite', 'Dogum_Yili', 'Temsilcilik']
        for col in required_cols:
            if col not in df.columns:
                df[col] = ""

        # --- VERİ TEMİZLİĞİ VE DÖNÜŞÜMLER ---

        # 1. TEMSİLCİLİK DÜZELTME (Otomatik VAN MERKEZ yapma)
        def fix_location(x):
            x = str(x).strip()
            if x in ["-", "", "None", "nan"] or len(x) < 3:
                return "VAN MERKEZ"
            return x.upper() # Hepsini büyük harf yap
        
        df['Temsilcilik'] = df['Temsilcilik'].apply(fix_location)

        # 2. ÜNİVERSİTE DÜZELTME
        df['Universite'] = df['Universite'].str.upper().str.strip()

        # 3. YAŞ HESAPLAMA (Tarihten Yıl Çıkarma: 11/02/1947 -> 1947)
        current_year = datetime.now().year
        
        def extract_age_from_date(val):
            val = str(val).strip()
            year = 0
            try:
                # Eğer format 11/02/1947 veya 11.02.1947 ise
                if "/" in val:
                    year = int(val.split("/")[-1])
                elif "." in val:
                    year = int(val.split(".")[-1])
                elif len(val) == 4 and val.isdigit(): # Sadece yıl yazılmışsa
                    year = int(val)
                
                if 1930 < year < current_year:
                    return current_year - year
                return 0
            except:
                return 0
        
        # 'Dogum_Yili' sütunu aslında tarihi tutuyor, onu yaşa çeviriyoruz
        df['Yas'] = df['Dogum_Yili'].apply(extract_age_from_date)

        # Yaş Gruplama
        def group_age(age):
            if age == 0: return "Belirsiz"
            if age < 30: return "20-29 (Genç)"
            if age < 40: return "30-39 (Dinamik)"
            if age < 50: return "40-49 (Olgun)"
            if age < 60: return "50-59 (Kıdemli)"
            return "60+ (Duayen)"
        
        df['Yas_Grubu'] = df['Yas'].apply(group_age)

        # 4. SİCİL NO TEMİZLİĞİ
        def clean_sicil(x):
            try:
                return int(str(x).replace(".", "").replace(" ", ""))
            except:
                return 999999 
        df['Sicil_Int'] = df['Sicil_No'].apply(clean_sicil)
        df = df.sort_values(by='Sicil_Int')
        
        # 5. SANDIK ATAMA
        try:
            df['Sandik_No'] = pd.qcut(df['Sicil_Int'].rank(method='first'), q=6, labels=[
                "1. Sandık (En Kıdemliler)", "2. Sandık", "3. Sandık", 
                "4. Sandık", "5. Sandık", "6. Sandık (En Gençler)"
            ])
        except:
            df['Sandik_No'] = "Belirsiz"

        # --- LOG VERİLERİNİ ÇEK ---
        try:
            ws_log = sheet.worksheet("log_kayitlari")
        except:
            ws_log = sheet.add_worksheet(title="log_kayitlari", rows="1000", cols="20")
        
        log_data_raw = ws_log.get_all_values()
        correct_headers = ['Zaman', 'Sicil_No', 'Ad_Soyad', 'Kullanici', 'Kurum', 'Egilim', 'Gecmis_2024', 'Gecmis_2022', 'Temas_Durumu', 'Rakip_Ekleme', 'Ulasim', 'Cizikler']
        
        # Log Başlık Onarımı
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
    
    # Bilgi Gösterimi
    yas = kisi.get('Yas', 0)
    uni = kisi.get('Universite', '')
    temsil = kisi.get('Temsilcilik', 'VAN MERKEZ')
    
    c_info1, c_info2, c_info3 = st.columns(3)
    c_info1.info(f"📍 **{temsil}**")
    c_info2.info(f"🎓 **{uni if len(uni)>2 else 'Belirtilmemiş'}**")
    c_info3.info(f"🎂 **{int(yas) if yas > 0 else '?'} Yaş**")
    
    is_admin = (user['Rol'] == 'ADMIN')
    def get(f): return kisi.get(f, "") if is_admin else ""

    # Geçmiş Tablosu
    st.markdown("##### 🕒 Seçmen Hafızası")
    found = False
    if df_log is not None and not df_log.empty and 'Sicil_No' in df_log.columns:
        logs = df_log[df_log['Sicil_No'].astype(str).str.strip() == str(sicil).strip()]
        if not logs.empty:
            found = True
            st.dataframe(logs[['Zaman','Kullanici','Egilim','Cizikler']].sort_values('Zaman', ascending=False), hide_index=True, use_container_width=True)
    if not found: st.caption("Henüz kayıt girilmemiş.")
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
        
        # Hızlı Düzenleme
        c_ex1, c_ex2 = st.columns(2)
        n_uni = c_ex1.text_input("Üniversite (Düzelt)", value=kisi.get('Universite', ''))
        n_temsil = c_ex2.text_input("Temsilcilik (Düzelt)", value=kisi.get('Temsilcilik', ''))

        if st.form_submit_button("✅ KAYDET"):
            updates = [
                ("Kurum", nk), ("Gecmis_2024", n24), ("Gecmis_2022", n22),
                ("Egilim", ne), ("Temas_Durumu", nt), ("Ulasim", nu),
                ("Cizikler", nn), ("Rakip_Ekleme", nr), ("Referans", nref),
                ("Universite", n_uni), ("Temsilcilik", n_temsil),
                ("Son_Guncelleyen", user['Kullanici_Adi'])
            ]
            for col, val in updates:
                # Kolon ismini tekrar kontrol et (Excel'de Türkçe olabilir)
                target_col = col
                if col == 'Universite' and 'Üniversite' in df_cols: target_col = 'Üniversite'
                if col == 'Temsilcilik' and 'Temsilcilik' in df_cols: target_col = 'Temsilcilik'
                
                # Excel'de kolon varsa güncelle
                if col in df_cols: 
                    ws.update_cell(row_n, df_cols.index(col)+1, val)
                # Alternatif isimlerle kontrol (Türkçe karakter)
                elif target_col in df_cols:
                    ws.update_cell(row_n, df_cols.index(target_col)+1, val)
            
            if ws_log:
                ws_log.append_row([datetime.now().strftime("%Y-%m-%d %H:%M"), str(sicil), kisi['Ad_Soyad'], user['Kullanici_Adi'], nk, ne, n24, n22, nt, nr, nu, nn])
            st.toast("Kaydedildi!", icon="💾")
            time.sleep(1)
            st.rerun()

# --- 5. ANA EKRAN ---
user = st.session_state.user
df, ws, df_log, ws_log = get_data()

if df.empty:
    st.warning("Veriler yükleniyor... (Eğer uzun sürerse sayfayı yenileyin)")
    st.stop()

menu = st.sidebar.radio("Menü", ["📊 ANALİZ RAPORU", "🎓 DEMOGRAFİK ANALİZ", "📝 Veri Girişi"] if user['Rol']=='ADMIN' else ["📝 Veri Girişi"])

# =========================================================
# DEMOGRAFİK ANALİZ
# =========================================================
if menu == "🎓 DEMOGRAFİK ANALİZ":
    st.title("🎓 Stratejik Demografi Analizi")

    tab1, tab2, tab3 = st.tabs(["🏛️ ÜNİVERSİTE LOBİSİ", "👶/👴 KUŞAK ANALİZİ", "📍 BÖLGESEL GÜÇ"])

    with tab1:
        st.subheader("Üniversite Mezun Dağılımı")
        uni_df = df[df['Universite'].str.len() > 2]
        if not uni_df.empty:
            uni_counts = uni_df['Universite'].value_counts().reset_index()
            uni_counts.columns = ['Üniversite', 'Kişi Sayısı']
            fig_uni = px.bar(uni_counts.head(15), x='Kişi Sayısı', y='Üniversite', orientation='h', title="Top 15 Üniversite", text_auto=True)
            fig_uni.update_layout(yaxis={'categoryorder':'total ascending'})
            st.plotly_chart(fig_uni, use_container_width=True)
        else:
            st.warning("⚠️ Üniversite verisi okunamadı. Excel'de 'Üniversite' başlığı olduğundan emin olun.")

    with tab2:
        st.subheader("Yaş Grupları")
        age_counts = df['Yas_Grubu'].value_counts().reset_index()
        age_counts.columns = ['Yaş Grubu', 'Kişi Sayısı']
        
        c1, c2 = st.columns(2)
        with c1:
            fig_age = px.pie(age_counts, names='Yaş Grubu', values='Kişi Sayısı', title="Kuşak Dağılımı", hole=0.4)
            st.plotly_chart(fig_age, use_container_width=True)
        with c2:
            valid_ages = df[df['Yas'] > 0]['Yas']
            if not valid_ages.empty:
                st.metric("Oda Yaş Ortalaması", f"{int(valid_ages.mean())}")
            else:
                st.metric("Oda Yaş Ortalaması", "Hesaplanamadı")
            st.info("Yaş verisi 'Doğum_Tarihi' sütunundan (Örn: 11/02/1947) otomatik çekilmiştir.")

    with tab3:
        st.subheader("Bölgesel (Temsilcilik) Dağılımı")
        rep_counts = df['Temsilcilik'].value_counts().reset_index()
        rep_counts.columns = ['Bölge', 'Üye Sayısı']
        fig_rep = px.bar(rep_counts, x='Bölge', y='Üye Sayısı', color='Üye Sayısı', title="İlçe Gücü")
        st.plotly_chart(fig_rep, use_container_width=True)

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
        if not temas.empty:
            st.plotly_chart(px.pie(temas, names='Egilim', title='Saha Durumu'), use_container_width=True)
    with c_bar:
        k_counts = bizimkiler['Kurum'].value_counts().reset_index()
        k_counts.columns = ['Kurum', 'Oylar']
        st.plotly_chart(px.bar(k_counts.head(10), x='Oylar', y='Kurum', orientation='h', title='En Güçlü Olduğumuz Kurumlar'), use_container_width=True)

# =========================================================
# VERİ GİRİŞİ
# =========================================================
elif menu == "📝 Veri Girişi":
    st.header("📋 Seçmen Bilgi Girişi")
    if 'search_term' not in st.session_state: st.session_state.search_term = ""
    def update_search(): st.session_state.search_term = st.session_state.widget_search
    search = st.text_input("🔍 İsim Ara", value=st.session_state.search_term, key="widget_search", on_change=update_search)
    
    # Sütun seçimi (Güvenli)
    cols = ['Sicil_No', 'Ad_Soyad', 'Universite', 'Temsilcilik', 'Kurum', 'Egilim', 'Son_Guncelleyen']
    # Mevcut olanları göster
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
