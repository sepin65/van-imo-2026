import streamlit as st
import pandas as pd
import gspread
import plotly.express as px
import plotly.graph_objects as go
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import time
import math

# --- 1. SAYFA AYARLARI ---
st.set_page_config(
    page_title="İMO Van 2026 - Karargah", 
    layout="wide", 
    page_icon="🏗️",
    initial_sidebar_state="collapsed"
)

# --- 2. BAĞLANTIYI KUR ---
@st.cache_resource
def get_connection():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    return client

# --- 3. VERİLERİ ÇEK VE İŞLE ---
def get_data():
    client = get_connection()
    try:
        sheet = client.open("Van_IMO_Secim_2026")
        
        # --- ANA LİSTE ---
        ws = sheet.worksheet("secmenler")
        all_data = ws.get_all_values()
        
        if len(all_data) > 1:
            headers = [h.strip() for h in all_data[0]]
            rows = all_data[1:]
            cleaned_headers = [h if h != "" else f"Bos_Sutun_{i}" for i, h in enumerate(headers)]
            df = pd.DataFrame(rows, columns=cleaned_headers)
        else:
            return pd.DataFrame(), None, pd.DataFrame(), None

        # Sütun İsimlerini Eşleştir
        rename_map = {
            'Üniversite': 'Universite',
            'Doğum_Tarihi': 'Dogum_Tarihi',
            'Eğilim': 'Egilim',
            'Ulaşım': 'Ulasim',
            'Temsilcilik': 'Temsilcilik',
            'Tanıyanlar': 'Taniyanlar'
        }
        df.rename(columns=rename_map, inplace=True)

        required_cols = ['Referans', 'Sandik_No', 'Egilim', 'Kurum', 'Ad_Soyad', 'Sicil_No', 'Temas_Durumu', 'Ulasim', 'Cizikler', 'Rakip_Ekleme', 'Gecmis_2024', 'Gecmis_2022', 'Telefon', 'Universite', 'Dogum_Tarihi', 'Temsilcilik', 'Taniyanlar']
        for col in required_cols:
            if col not in df.columns: df[col] = ""

        # --- VERİ TEMİZLİĞİ ---
        
        # 1. Temsilcilik
        def fix_location(x):
            x = str(x).strip().upper()
            if x in ["-", "", "NONE", "NAN"] or len(x) < 3: return "VAN MERKEZ"
            return x
        df['Temsilcilik'] = df['Temsilcilik'].apply(fix_location)

        # 2. Üniversite
        df['Universite'] = df['Universite'].str.upper().str.strip()

        # 3. YAŞ HESAPLAMA (GELİŞMİŞ)
        current_year = datetime.now().year
        
        def calculate_age_robust(date_str):
            date_str = str(date_str).strip()
            if not date_str or date_str in ["-", "nan", "None"]: return 0
            try:
                if "/" in date_str:
                    dt = pd.to_datetime(date_str, dayfirst=True, errors='coerce')
                    if pd.notnull(dt): return current_year - dt.year
                elif "." in date_str:
                    dt = pd.to_datetime(date_str, format="%d.%m.%Y", errors='coerce')
                    if pd.notnull(dt): return current_year - dt.year
                elif len(date_str) == 4 and date_str.isdigit():
                    return current_year - int(date_str)
                return 0
            except: return 0

        df['Yas'] = df['Dogum_Tarihi'].apply(calculate_age_robust)

        # --- YENİ YAŞ GRUPLAMA (5 YILLIK DİLİMLER) ---
        def group_age(age):
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
            
        df['Yas_Grubu'] = df['Yas'].apply(group_age)

        # 4. Sicil
        def clean_sicil(x):
            try: return int(str(x).replace(".", "").replace(" ", ""))
            except: return 999999 
        df['Sicil_Int'] = df['Sicil_No'].apply(clean_sicil)
        df = df.sort_values(by='Sicil_Int')
        
        # 5. Sandık
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
        log_headers = ['Zaman', 'Sicil_No', 'Ad_Soyad', 'Kullanici', 'Kurum', 'Egilim', 'Gecmis_2024', 'Gecmis_2022', 'Temas_Durumu', 'Rakip_Ekleme', 'Ulasim', 'Cizikler', 'Taniyanlar']
        
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
        st.error(f"Sistem Hatası: {e}")
        return pd.DataFrame(), None, pd.DataFrame(), None

# --- GİRİŞ EKRANI ---
if 'user' not in st.session_state: st.session_state.user = None
if st.session_state.user is None:
    st.title("🏗️ İMO SEÇİM SİSTEMİ")
    st.info("⏳ GİRİŞ EKRANI")
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

# --- FORM DIALOG ---
@st.dialog("✏️ SEÇMEN KARTI")
def entry_form_dialog(kisi, row_n, sicil, user, df_cols, ws, ws_log, df_log):
    st.markdown(f"### 👤 {kisi['Ad_Soyad']}")
    
    yas = kisi.get('Yas', 0)
    uni = kisi.get('Universite', '')
    temsil = kisi.get('Temsilcilik', 'VAN MERKEZ')
    taniyan = kisi.get('Taniyanlar', '')
    
    c1, c2, c3 = st.columns(3)
    c1.info(f"📍 **{temsil}**")
    c2.info(f"🎓 **{uni if len(uni)>2 else '-'}**")
    c3.info(f"🎂 **{int(yas) if yas > 0 else '?'} Yaş**")
    
    if len(str(taniyan)) > 1:
        st.warning(f"🔗 **Tanıyanlar:** {taniyan}")
    
    is_admin = (user['Rol'] == 'ADMIN')
    def get(f): return kisi.get(f, "") if is_admin else ""

    st.markdown("##### 🕒 Geçmiş Hareketler")
    if df_log is not None and not df_log.empty and 'Sicil_No' in df_log.columns:
        logs = df_log[df_log['Sicil_No'].astype(str).str.strip() == str(sicil).strip()]
        if not logs.empty:
            st.dataframe(logs[['Zaman','Kullanici','Egilim','Cizikler']].sort_values('Zaman', ascending=False), hide_index=True, use_container_width=True)
        else: st.caption("Kayıt yok.")
    
    with st.form("form"):
        # --- ÜST BİLGİLER ---
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

        # --- YENİ ALAN: TANIYANLAR ---
        ntaniyan = st.text_input("🔗 Tanıyanlar (Virgülle ayırın)", value=get('Taniyanlar'), placeholder="Örn: Serhat, Baran, Mazlum")

        nn = st.text_area("Notlar", value=get('Cizikler'))
        nr = st.text_input("Rakip Ekleme", value=get('Rakip_Ekleme'))
        nref = st.text_input("Referans", value=get('Referans'))
        
        # --- ALT BİLGİ DÜZELTME ---
        with st.expander("🛠️ Bilgi Düzeltme (Üniversite/Bölge)"):
            c_ex1, c_ex2 = st.columns(2)
            n_uni = c_ex1.text_input("Üniversite Düzelt", value=kisi.get('Universite', ''))
            n_temsil = c_ex2.text_input("Temsilcilik Düzelt", value=kisi.get('Temsilcilik', ''))

        if st.form_submit_button("✅ KAYDET"):
            updates = [
                ("Kurum", nk), ("Gecmis_2024", n24), ("Gecmis_2022", n22),
                ("Egilim", ne), ("Temas_Durumu", nt), ("Ulasim", nu),
                ("Cizikler", nn), ("Rakip_Ekleme", nr), ("Referans", nref),
                ("Universite", n_uni), ("Temsilcilik", n_temsil),
                ("Tanıyanlar", ntaniyan),
                ("Son_Guncelleyen", user['Kullanici_Adi'])
            ]
            for col, val in updates:
                target = col
                if col == 'Universite' and 'Üniversite' in df_cols: target = 'Üniversite'
                if col == 'Temsilcilik' and 'Temsilcilik' in df_cols: target = 'Temsilcilik'
                if col == 'Tanıyanlar' and 'Taniyanlar' in df_cols: target = 'Taniyanlar'
                
                if col in df_cols: ws.update_cell(row_n, df_cols.index(col)+1, val)
                elif target in df_cols: ws.update_cell(row_n, df_cols.index(target)+1, val)
            
            if ws_log:
                ws_log.append_row([datetime.now().strftime("%Y-%m-%d %H:%M"), str(sicil), kisi['Ad_Soyad'], user['Kullanici_Adi'], nk, ne, n24, n22, nt, nr, nu, nn, ntaniyan])
            st.toast("Kaydedildi!", icon="💾")
            time.sleep(1)
            st.rerun()

# --- ANA EKRAN ---
user = st.session_state.user
df, ws, df_log, ws_log = get_data()
if df.empty:
    st.warning("Veriler yükleniyor...")
    st.stop()

# --- SIDEBAR MENU ---
menu_options = ["📝 Veri Girişi"]
if user['Rol'] == 'ADMIN':
    menu_options = ["📊 GENEL ANALİZ", "🎓 DEMOGRAFİK İSTİHBARAT", "📝 Veri Girişi"]

menu = st.sidebar.radio("Menü", menu_options)

# =========================================================
# 🎓 DEMOGRAFİK İSTİHBARAT (5 YILLIK DİLİMLER)
# =========================================================
if menu == "🎓 DEMOGRAFİK İSTİHBARAT" and user['Rol'] == 'ADMIN':
    st.title("🎓 Stratejik Demografi & İstihbarat")
    
    # 0 yaş (Bilinmeyen) olanları analiz dışı bırak
    df_valid_age = df[df['Yas'] > 18]

    tab1, tab2, tab3 = st.tabs(["🏛️ ÜNİVERSİTE ANALİZİ", "🌍 BÖLGESEL DERİNLİK", "🏢 KURUMSAL İSTİHBARAT"])

    # ---------------- TAB 1: ÜNİVERSİTE ANALİZİ ----------------
    with tab1:
        st.subheader("Üniversite Tabanlı Çözümleme")
        
        if 'Universite' in df.columns:
            uni_list = sorted([u for u in df['Universite'].unique() if len(str(u)) > 2])
            selected_uni = st.selectbox("Analiz Edilecek Üniversiteyi Seçin:", ["TÜMÜ"] + uni_list)
            
            if selected_uni == "TÜMÜ":
                df_uni = df[df['Universite'].str.len() > 2]
                title = "GENEL DAĞILIM"
            else:
                df_uni = df[df['Universite'] == selected_uni]
                title = f"{selected_uni} MEZUNLARI"
            
            st.divider()
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Kişi Sayısı", len(df_uni))
            
            valid_ages_uni = df_uni[df_uni['Yas'] > 18]['Yas']
            avg_age = valid_ages_uni.mean() if not valid_ages_uni.empty else 0
            c2.metric("Yaş Ortalaması", f"{int(avg_age) if avg_age > 0 else '-'}")
            
            top_loc = df_uni['Temsilcilik'].mode()[0] if not df_uni.empty else "-"
            c3.metric("En Yoğun Bölge", top_loc)

            col_g1, col_g2 = st.columns(2)
            with col_g1:
                st.caption(f"📊 {title} - Yaş Aralıkları (5 Yıllık)")
                df_pie = df_uni[df_uni['Yas'] > 18]
                if not df_pie.empty:
                    # Yaş gruplarını sıralı göstermek için
                    age_labels = ["20-24", "25-29", "30-34", "35-39", "40-44", "45-49", "50-54", "55-59", "60-64", "65+"]
                    age_counts = df_pie['Yas_Grubu'].value_counts().reindex(age_labels, fill_value=0).reset_index()
                    age_counts.columns = ['Yaş Aralığı', 'Kişi']
                    # 0 olanları gösterme
                    age_counts = age_counts[age_counts['Kişi'] > 0]
                    
                    age_fig = px.bar(age_counts, x='Yaş Aralığı', y='Kişi', title=f"Yaş Dağılımı", text_auto=True)
                    st.plotly_chart(age_fig, use_container_width=True)
                else:
                    st.warning("Bu grupta yaş verisi olan kimse yok.")
            
            with col_g2:
                st.caption(f"📍 {title} - Bölgesel Dağılım")
                if 'Temsilcilik' in df_uni.columns:
                    loc_fig = px.bar(df_uni['Temsilcilik'].value_counts().reset_index(), x='Temsilcilik', y='count', title="Temsilciliklere Göre Dağılım")
                    st.plotly_chart(loc_fig, use_container_width=True)

            with st.expander(f"📋 {title} Listesini Görüntüle"):
                st.dataframe(df_uni[['Sicil_No', 'Ad_Soyad', 'Yas', 'Temsilcilik', 'Kurum']], use_container_width=True)

    # ---------------- TAB 2: BÖLGESEL DERİNLİK ----------------
    with tab2:
        st.subheader("🌍 Bölgesel Derin İstihbarat")
        st.info("Ağrı, Yüksekova, Erciş gibi bölgeleri seçip analiz edin.")
        
        all_locs = sorted([l for l in df['Temsilcilik'].unique() if len(str(l))>2])
        target_region = st.selectbox("📍 Bölge Seçin:", all_locs)
        
        if target_region:
            df_reg = df[df['Temsilcilik'] == target_region]
            
            c_r1, c_r2, c_r3 = st.columns(3)
            c_r1.metric("Üye Sayısı", len(df_reg))
            
            valid_ages = df_reg[df_reg['Yas'] > 18]['Yas']
            avg_reg_age = int(valid_ages.mean()) if not valid_ages.empty else "-"
            c_r2.metric("Yaş Ortalaması", avg_reg_age)
            
            top_uni = df_reg['Universite'].mode()[0] if not df_reg.empty else "-"
            c_r3.metric("Hakim Üniversite", top_uni)
            
            st.divider()
            
            col_d1, col_d2, col_d3 = st.columns(3)
            
            with col_d1:
                st.markdown("**🎓 Üniversiteler**")
                if not df_reg.empty:
                    uni_counts = df_reg[df_reg['Universite'].str.len()>2]['Universite'].value_counts().head(7).reset_index()
                    if not uni_counts.empty:
                        fig_ru = px.bar(uni_counts, x='count', y='Universite', orientation='h', text_auto=True, height=350)
                        fig_ru.update_layout(yaxis={'categoryorder':'total ascending'}, margin=dict(l=0, r=0, t=0, b=0))
                        st.plotly_chart(fig_ru, use_container_width=True)
                    else: st.warning("Veri yok")
                
            with col_d2:
                st.markdown("**👶/👴 Yaş Yapısı**")
                df_reg_age = df_reg[df_reg['Yas'] > 18]
                if not df_reg_age.empty:
                    # Bar grafik daha okunaklı olur
                    age_labels = ["20-24", "25-29", "30-34", "35-39", "40-44", "45-49", "50-54", "55-59", "60-64", "65+"]
                    age_counts_reg = df_reg_age['Yas_Grubu'].value_counts().reindex(age_labels, fill_value=0).reset_index()
                    age_counts_reg.columns = ['Yaş Aralığı', 'Kişi']
                    age_counts_reg = age_counts_reg[age_counts_reg['Kişi'] > 0]
                    
                    fig_ra = px.bar(age_counts_reg, x='Yaş Aralığı', y='Kişi', text_auto=True, height=350)
                    fig_ra.update_layout(margin=dict(l=0, r=0, t=0, b=0))
                    st.plotly_chart(fig_ra, use_container_width=True)
                else:
                    st.info("Yaş verisi yok.")
                
            with col_d3:
                st.markdown("**🏢 Kurumsal Yapı**")
                if not df_reg.empty:
                    kurum_counts = df_reg[df_reg['Kurum'].str.len()>1]['Kurum'].value_counts().head(7).reset_index()
                    if not kurum_counts.empty:
                        fig_rk = px.bar(kurum_counts, x='Kurum', y='count', text_auto=True, height=350)
                        fig_rk.update_layout(margin=dict(l=0, r=0, t=0, b=0))
                        st.plotly_chart(fig_rk, use_container_width=True)
            
            with st.expander(f"📋 {target_region} Üye Listesi & Tanıyanlar"):
                st.dataframe(df_reg[['Sicil_No', 'Ad_Soyad', 'Universite', 'Yas', 'Taniyanlar']], use_container_width=True)

    # ---------------- TAB 3: KURUMSAL İSTİHBARAT ----------------
    with tab3:
        st.subheader("Kurum İçi Dengeler")
        
        kurum_list = [k for k in df['Kurum'].unique() if len(str(k))>2]
        sel_kurum = st.selectbox("Kurum Seçiniz:", ["TÜMÜ"] + sorted(kurum_list))
        
        if sel_kurum != "TÜMÜ":
            df_kurum = df[df['Kurum'] == sel_kurum]
        else:
            df_kurum = df
            
        c_k1, c_k2 = st.columns(2)
        
        with c_k1:
            st.markdown(f"**{sel_kurum} - Üniversite Dağılımı**")
            u_data = df_kurum[df_kurum['Universite'].str.len()>2]['Universite'].value_counts().head(10)
            st.bar_chart(u_data)
            
        with c_k2:
            st.markdown(f"**{sel_kurum} - Yaş Grupları**")
            df_kurum_age = df_kurum[df_kurum['Yas'] > 18]
            if not df_kurum_age.empty:
                # Kurumlar için Pie daha iyi olabilir
                fig_ka = px.pie(df_kurum_age, names='Yas_Grubu', hole=0.5)
                st.plotly_chart(fig_ka, use_container_width=True)

# =========================================================
# GENEL ANALİZ RAPORU
# =========================================================
elif menu == "📊 GENEL ANALİZ" and user['Rol'] == 'ADMIN':
    st.title("📊 Seçim Komuta Masası")
    
    temas = df[df['Egilim'].str.len() > 1]
    bizimkiler = temas[temas['Egilim'].isin(["Tüm Listemizi Yazar", "Büyük Kısmı Yazar"])]
    kararsizlar = temas[temas['Egilim'].isin(["Kararsızım", "Kısmen Yazar"])]
    hedef_oy = int(len(df) / 2) + 1
    
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Toplam Seçmen", len(df))
    c2.metric("Ulaşılan", len(temas), f"%{int(len(temas)/len(df)*100) if len(df)>0 else 0}")
    c3.metric("🟡 KEMİK OY", len(bizimkiler), f"Hedef: {hedef_oy}")
    c4.metric("⚖️ KARARSIZ", len(kararsizlar))
    
    st.divider()
    
    tabs = st.tabs(["📈 SAHA DURUMU", "🗳️ SANDIK GÜCÜ", "🏢 KURUMLAR"])
    
    with tabs[0]:
        if not temas.empty:
            fig_main = px.pie(temas, names='Egilim', title="Saha Eğilim Dağılımı", hole=0.4)
            st.plotly_chart(fig_main, use_container_width=True)
        else:
            st.info("Henüz veri girişi yapılmamış.")
            
    with tabs[1]:
        sandik_ozet = temas.groupby(['Sandik_No', 'Egilim']).size().reset_index(name='Kişi')
        if not sandik_ozet.empty:
            fig_san = px.bar(sandik_ozet, x="Sandik_No", y="Kişi", color="Egilim", title="Sandık Bazlı Durum")
            st.plotly_chart(fig_san, use_container_width=True)
            
    with tabs[2]:
        kurum_data = bizimkiler['Kurum'].value_counts().reset_index()
        kurum_data.columns = ['Kurum', 'Oy Sayısı']
        fig_kur = px.bar(kurum_data.head(10), x='Oy Sayısı', y='Kurum', orientation='h', title="En Güçlü Olduğumuz Kurumlar")
        st.plotly_chart(fig_kur, use_container_width=True)

# =========================================================
# VERİ GİRİŞİ
# =========================================================
elif menu == "📝 Veri Girişi":
    st.header("📋 Seçmen Bilgi Girişi")
    if 'search_term' not in st.session_state: st.session_state.search_term = ""
    def update_search(): st.session_state.search_term = st.session_state.widget_search
    search = st.text_input("🔍 İsim Ara", value=st.session_state.search_term, key="widget_search", on_change=update_search)
    
    cols = ['Sicil_No', 'Ad_Soyad', 'Universite', 'Temsilcilik', 'Kurum', 'Egilim', 'Taniyanlar']
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
