import streamlit as st
import pandas as pd
import gspread
import plotly.express as px
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

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
        data = ws.get_all_records()
        df = pd.DataFrame(data)
        df.columns = df.columns.str.strip()
        df = df.astype(str)
        
        # --- SICIL DÜZELTME VE SANDIK ATAMA ---
        def clean_sicil(x):
            try:
                return int(str(x).replace(".", "").replace(" ", ""))
            except:
                return 999999 

        df['Sicil_Int'] = df['Sicil_No'].apply(clean_sicil)
        df = df.sort_values(by='Sicil_Int')
        
        try:
            df['Sandik_No'] = pd.qcut(df['Sicil_Int'].rank(method='first'), q=6, labels=[
                "1. Sandık (En Kıdemliler)", "2. Sandık", "3. Sandık", 
                "4. Sandık", "5. Sandık", "6. Sandık (En Gençler)"
            ])
        except:
            df['Sandik_No'] = "Belirsiz"

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

# --- SAYAÇ ---
def get_countdown():
    try:
        target_date = datetime(2026, 2, 14)
        now = datetime.now()
        remaining = target_date - now
        return remaining.days
    except:
        return 400

# --- 3. GİRİŞ EKRANI ---
if 'user' not in st.session_state:
    st.session_state.user = None

if st.session_state.user is None:
    st.title("🏗️ İMO SEÇİM SİSTEMİ")
    gun = get_countdown()
    st.info(f"⏳ SEÇİME **{gun}** GÜN KALDI!")
    
    with st.form("giris_formu"):
        kadi = st.text_input("Kullanıcı Adı")
        sifre = st.text_input("Şifre", type="password")
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
gun = get_countdown()
st.sidebar.markdown(f"<div style='background-color:#d32f2f;padding:10px;border-radius:5px;text-align:center;color:white;'><h3>⏳ {gun} GÜN</h3></div>", unsafe_allow_html=True)
st.sidebar.markdown(f"### 👤 {user['Kullanici_Adi']}")

if st.sidebar.button("Çıkış Yap"):
    st.session_state.user = None
    st.rerun()

df, ws, df_log, ws_log = get_data()

if df is None:
    st.error("Bağlantı Hatası. Sayfayı yenileyin.")
    st.stop()

if user['Rol'] == 'ADMIN':
    menu = st.sidebar.radio("Menü", ["📊 360° STRATEJİK ANALİZ", "📝 Veri Girişi"])
else:
    menu = st.sidebar.radio("Menü", ["📝 Veri Girişi"])

# =========================================================
# EKRAN 1: ANALİZ
# =========================================================
if menu == "📊 360° STRATEJİK ANALİZ" and user['Rol'] == 'ADMIN':
    st.title("📊 Seçim Komuta Masası")
    
    temas = df[df['Egilim'].str.len() > 1]
    bizimkiler = temas[temas['Egilim'].isin(["Tüm Listemizi Yazar", "Büyük Kısmı Yazar"])]
    kararsizlar = temas[temas['Egilim'].isin(["Kararsızım", "Kısmen Yazar"])]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Toplam Üye", len(df))
    c2.metric("Ulaşılan", len(temas), f"%{int(len(temas)/len(df)*100)}")
    c3.metric("🟡 KEMİK OY", len(bizimkiler))
    c4.metric("⚖️ KARARSIZ", len(kararsizlar))

    st.divider()

    tabs = st.tabs(["🗳️ SANDIK ANALİZİ", "🎯 Hedefler", "🌍 Genel", "🏢 Kurumlar", "⚡ Ekip"])

    with tabs[0]:
        st.subheader("🗳️ Sandık Bazlı Güç Analizi")
        sandik_ozet = temas.groupby(['Sandik_No', 'Egilim']).size().reset_index(name='Kişi Sayısı')
        if not sandik_ozet.empty:
            fig_sandik = px.bar(sandik_ozet, x="Sandik_No", y="Kişi Sayısı", color="Egilim", 
                                title="Sandıklara Göre Oy Dağılımı", text_auto=True)
            st.plotly_chart(fig_sandik, use_container_width=True)
            st.dataframe(pd.crosstab(temas['Sandik_No'], temas['Egilim']), use_container_width=True)
        else:
            st.warning("Veri yok.")

    with tabs[1]:
        st.subheader("🎯 Fırsat Listesi")
        if not kararsizlar.empty:
            h_list = kararsizlar[['Sicil_No', 'Ad_Soyad', 'Sandik_No', 'Kurum', 'Referans']].copy()
            st.dataframe(h_list, use_container_width=True)
            st.download_button("📥 İndir", h_list.to_csv().encode('utf-8'), 'firsat_listesi.csv')
        else:
            st.success("Kararsız üye yok.")

    with tabs[2]:
        c_pie, c_bar = st.columns(2)
        with c_pie:
            fig_p = px.pie(temas, names='Egilim', title="Genel Pasta", hole=0.4)
            st.plotly_chart(fig_p, use_container_width=True)
        with c_bar:
            if 'Gecmis_2024' in temas.columns:
                gecis = temas[temas['Gecmis_2024'].str.len() > 1]
                if not gecis.empty:
                    fig_s = px.histogram(gecis, x="Gecmis_2024", color="Egilim", barmode="group", title="Geçiş Analizi")
                    st.plotly_chart(fig_s, use_container_width=True)

    with tabs[3]:
        k_genel = df['Kurum'].value_counts().reset_index()
        k_genel.columns = ['Kurum', 'Top']
        k_bizim = bizimkiler['Kurum'].value_counts().reset_index()
        k_bizim.columns = ['Kurum', 'Biz']
        m = pd.merge(k_genel, k_bizim, on='Kurum', how='left').fillna(0)
        m = m[m['Top'] > 0]
        m['Oran'] = (m['Biz'] / m['Top'] * 100).astype(int)
        fig_ku = px.bar(m, x='Kurum', y='Oran', text='Biz', color='Oran', title="Kurum Başarısı (%)")
        st.plotly_chart(fig_ku, use_container_width=True)

    with tabs[4]:
        if not df_log.empty:
            perf = df_log['Kullanici'].value_counts().reset_index()
            perf.columns = ['İsim', 'İşlem']
            st.bar_chart(perf.set_index('İsim'))
            st.dataframe(df_log.tail(10), use_container_width=True)

# =========================================================
# EKRAN 2: VERİ GİRİŞİ
# =========================================================
elif menu == "📝 Veri Girişi":
    st.header("📋 Seçmen Bilgi Girişi")
    is_admin = (user['Rol'] == 'ADMIN')
    
    if is_admin: st.success("YETKİLİ MODU")
    else: st.info("SAHA MODU (Gizli Giriş)")

    search = st.text_input("🔍 İsim Ara", placeholder="Ad Soyad...")
    cols = ['Sicil_No', 'Ad_Soyad', 'Sandik_No', 'Kurum', 'Egilim', 'Son_Guncelleyen'] if is_admin else ['Sicil_No', 'Ad_Soyad', 'Sandik_No', 'Kurum']
    
    if search:
        df_show = df[df['Ad_Soyad'].str.contains(search, case=False, na=False)]
    else:
        df_show = df
        
    event = st.dataframe(df_show[cols], use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row")

    if len(event.selection.rows) > 0:
        idx = event.selection.rows[0]
        sicil = df_show.iloc[idx]['Sicil_No']
        g_idx = df[df['Sicil_No'] == sicil].index[0]
        row_n = g_idx + 2
        kisi = df.iloc[g_idx]

        st.divider()
        st.markdown(f"### ✏️ **{kisi['Ad_Soyad']}**")
        st.caption(f"📌 {kisi.get('Sandik_No', 'Belirsiz')}")

        with st.form("entry_form"):
            def get(f): return kisi.get(f, "") if is_admin else ""
            
            c1, c2 = st.columns(2)
            with c1:
                # --- GÜNCELLENMİŞ KURUM LİSTESİ ---
                opts_kurum = [
                    "", "Özel Sektör", "Dsi", "Karayolları", "Büyükşehir", "Vaski", 
                    "Projeci", "Yapı Denetimci", "İlçe Belediyeleri", "Müteahhit", 
                    "Yapsat", "Çevre Şehircilik", "Emekli", "Diğer"
                ]
                curr_k = kisi.get('Kurum', "") 
                n_kurum = st.selectbox("Kurum", opts_kurum, index=opts_kurum.index(curr_k) if curr_k in opts_kurum else 0)

                opts_24 = ["", "Sarı Liste", "Mavi Liste"]
                curr_24 = get('Gecmis_2024')
                n_24 = st.selectbox("2024", opts_24, index=opts_24.index(curr_24) if curr_24 in opts_24 else 0)
                
                opts_22 = ["", "Sarı Liste", "Mavi Liste", "Beyaz Liste"]
                curr_22 = get('Gecmis_2022')
                n_22 = st.selectbox("2022", opts_22, index=opts_22.index(curr_22) if curr_22 in opts_22 else 0)

            with c2:
                opts_egilim = ["", "Tüm Listemizi Yazar", "Büyük Kısmı Yazar", "Kısmen Yazar", "Karşı Tarafı Destekler", "Kararsızım"]
                curr_e = get('Egilim')
                n_egilim = st.selectbox("2026 EĞİLİMİ", opts_egilim, index=opts_egilim.index(curr_e) if curr_e in opts_egilim else 0)

                opts_temas = ["", "Kendim Görüştüm", "Arkadaşım/Akraba Aracılığı", "Tanımıyorum"]
                curr_t = get('Temas_Durumu')
                n_temas = st.selectbox("Temas", opts_temas, index=opts_temas.index(curr_t) if curr_t in opts_temas else 0)

                opts_ulasim = ["", "Kendisi Gelir", "Araç Gerekir", "İlçeden Gelecek", "Temsilcilikten Gelecek"]
                curr_u = get('Ulasim')
                n_ulasim = st.selectbox("Ulaşım", opts_ulasim, index=opts_ulasim.index(curr_u) if curr_u in opts_ulasim else 0)

            n_not = st.text_area("Notlar", value=get('Cizikler'))
            n_rakip = st.text_input("Rakip Ekleme", value=get('Rakip_Ekleme'))
            n_ref = st.text_input("Referans", value=get('Referans'))

            if st.form_submit_button("✅ KAYDET"):
                try:
                    headers = df.columns.tolist()
                    updates = [
                        ("Kurum", n_kurum), ("Gecmis_2024", n_24), ("Gecmis_2022", n_22),
                        ("Egilim", n_egilim), ("Temas_Durumu", n_temas), ("Ulasim", n_ulasim),
                        ("Cizikler", n_not), ("Rakip_Ekleme", n_rakip), ("Referans", n_ref),
                        ("Son_Guncelleyen", user['Kullanici_Adi'])
                    ]
                    for col, val in updates:
                        if col in headers:
                            ws.update_cell(row_n, headers.index(col)+1, val)
                    
                    if ws_log:
                        now = datetime.now().strftime("%Y-%m-%d %H:%M")
                        log_data = [now, str(sicil), kisi['Ad_Soyad'], user['Kullanici_Adi'], n_kurum, n_egilim, n_24, n_22, n_temas, n_rakip, n_ulasim, n_not]
                        ws_log.append_row(log_data)
                    st.success("Kaydedildi!")
                except Exception as e:
                    st.error(f"Hata: {e}")
