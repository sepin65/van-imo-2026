import streamlit as st
import pandas as pd
import gspread
import plotly.express as px
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import pytz

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

# --- 2. VERİLERİ ÇEK ---
def get_data():
    client = get_connection()
    try:
        sheet = client.open("Van_IMO_Secim_2026")
        
        # Ana Liste
        ws = sheet.worksheet("secmenler")
        data = ws.get_all_records()
        df = pd.DataFrame(data)
        # Sütun isimlerindeki boşlukları temizle
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
    st.title("🏗️ GÜVENLİ GİRİŞ")
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
st.sidebar.success(f"👤 {user['Kullanici_Adi']} | {user['Rol']}")

if st.sidebar.button("Çıkış"):
    st.session_state.user = None
    st.rerun()

df, ws, df_log, ws_log = get_data()

if df is None:
    st.error("Veri alınamadı. Sayfayı yenileyin.")
    st.stop()

# Menü Yetkilendirmesi
if user['Rol'] == 'ADMIN':
    menu_secenekleri = ["📊 360° DERİN ANALİZ", "📝 Seçmen Kartı & Giriş"]
else:
    menu_secenekleri = ["📝 Seçmen Kartı & Giriş"]

menu = st.sidebar.radio("Menü", menu_secenekleri)

# =========================================================
# EKRAN 1: 360 DERECE DERİN ANALİZ (SADECE ADMIN)
# =========================================================
if menu == "📊 360° DERİN ANALİZ" and user['Rol'] == 'ADMIN':
    st.title("📊 STRATEJİK İSTİHBARAT RAPORU")
    
    toplam_uye = len(df)
    temas_df = df[df['Egilim'].str.len() > 1]
    temas_sayisi = len(temas_df)
    
    bizimkiler = temas_df[temas_df['Egilim'].isin(["Tüm Listemizi Yazar", "Büyük Kısmı Yazar"])]
    bizim_sayi = len(bizimkiler)
    
    c1, c2, c3 = st.columns(3)
    c1.metric("Toplam Üye", toplam_uye)
    c2.metric("Sahada Dokunulan", temas_sayisi)
    c3.metric("🟡 KEMİK OYUMUZ", bizim_sayi)

    st.divider()

    tab1, tab2, tab3 = st.tabs(["Genel Durum", "Kurumsal", "Ekip Ligi"])

    with tab1:
        c_pie, c_sankey = st.columns(2)
        with c_pie:
            st.subheader("Genel Dağılım")
            fig_pie = px.pie(temas_df, names='Egilim', hole=0.4)
            st.plotly_chart(fig_pie, use_container_width=True)
        with c_sankey:
             st.subheader("Geçiş Analizi")
             if 'Gecmis_2024' in temas_df.columns:
                gecis = temas_df[temas_df['Gecmis_2024'].str.len() > 1]
                if not gecis.empty:
                    fig_s = px.histogram(gecis, x="Gecmis_2024", color="Egilim", barmode="group")
                    st.plotly_chart(fig_s, use_container_width=True)

    with tab2:
        st.subheader("Kurum Bazlı Başarı")
        kurum_genel = temas_df['Kurum'].value_counts().reset_index()
        kurum_genel.columns = ['Kurum', 'Toplam']
        kurum_bizim = bizimkiler['Kurum'].value_counts().reset_index()
        kurum_bizim.columns = ['Kurum', 'Bizim']
        merged = pd.merge(kurum_genel, kurum_bizim, on='Kurum', how='left').fillna(0)
        merged['Oran'] = (merged['Bizim'] / merged['Toplam'] * 100).astype(int)
        fig_k = px.bar(merged, x='Kurum', y='Oran', color='Oran', title="Kurum Başarı Oranı (%)", text='Bizim')
        st.plotly_chart(fig_k, use_container_width=True)
    
    with tab3:
        st.subheader("Ekip Performansı")
        if not df_log.empty:
            perf = df_log['Kullanici'].value_counts().reset_index()
            perf.columns = ['Kullanici', 'Islem']
            st.bar_chart(perf.set_index('Kullanici'))
            st.dataframe(df_log.tail(20).sort_index(ascending=False), use_container_width=True)

# =========================================================
# EKRAN 2: SEÇMEN KARTI (KÖR GİRİŞ SİSTEMİ)
# =========================================================
elif menu == "📝 Seçmen Kartı & Giriş":
    st.header("📋 Seçmen Veri Girişi")
    
    if user['Rol'] == 'ADMIN':
        st.info("🔓 ADMIN MODU: Mevcut verileri görüyorsunuz.")
    else:
        st.warning("🔒 SAHA MODU: Gizli Veri Girişi (Sıfırdan giriş yapıyorsunuz).")

    search_term = st.text_input("🔎 İsimle Ara", placeholder="Örn: Ahmet")
    
    # SAHA ELEMANI LİSTEDE EĞİLİMİ GÖRMESİN
    if user['Rol'] == 'ADMIN':
        cols_show = ['Sicil_No', 'Ad_Soyad', 'Kurum', 'Egilim', 'Son_Guncelleyen']
    else:
        cols_show = ['Sicil_No', 'Ad_Soyad', 'Kurum'] 

    if search_term:
        df_display = df[df['Ad_Soyad'].str.contains(search_term, case=False, na=False)]
    else:
        df_display = df

    event = st.dataframe(
        df_display[cols_show],
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row"
    )

    if len(event.selection.rows) > 0:
        idx = event.selection.rows[0]
        sicil_no = df_display.iloc[idx]['Sicil_No']
        gercek_index = df[df['Sicil_No'] == sicil_no].index[0]
        row_num = gercek_index + 2
        kisi = df.iloc[gercek_index]

        st.divider()
        c_main, c_log = st.columns([2, 1])

        with c_main:
            st.markdown(f"### ✏️ **{kisi['Ad_Soyad']}**")
            
            with st.form("veri_giris"):
                # Veri Getirme Fonksiyonu (Admin görür, Saha göremez)
                def get_val(field):
                    if user['Rol'] == 'ADMIN':
                        return kisi.get(field, "")
                    else:
                        return "" # Saha elemanına boş döner
                
                # Kurum genelde sabittir, herkes görsün
                curr_kurum = kisi.get('Kurum', "") 
                
                c1, c2 = st.columns(2)
                with c1:
                    opt_kurum = ["", "Özel Sektör", "Dsi", "Karayolları", "Büyükşehir", "Vaski", "Projeci", "Yapı Denetimci", "İlçe Belediyeleri", "Müteahhit", "Yapsat", "Diğer"]
                    idx_k = opt_kurum.index(curr_kurum) if curr_kurum in opt_kurum else 0
                    yeni_kurum = st.selectbox("Kurum", opt_kurum, index=idx_k)
                    
                    # GEÇMİŞ (Kör giriş için gizli)
                    opt_24 = ["", "Sarı Liste", "Mavi Liste"]
                    curr_24 = get_val('Gecmis_2024')
                    idx_24 = opt_24.index(curr_24) if curr_24 in opt_24 else 0
                    yeni_24 = st.selectbox("2024 Tercihi", opt_24, index=idx_24)

                    opt_22 = ["", "Sarı Liste", "Mavi Liste", "Beyaz Liste"]
                    curr_22 = get_val('Gecmis_2022')
                    idx_22 = opt_22.index(curr_22) if curr_22 in opt_22 else 0
                    yeni_22 = st.selectbox("2022 Tercihi", opt_22, index=idx_22)

                with c2:
                    # EĞİLİM (KESİNLİKLE GİZLİ)
                    opt_egilim = ["", "Tüm Listemizi Yazar", "Büyük Kısmı Yazar", "Kısmen Yazar", "Karşı Tarafı Destekler", "Kararsızım"]
                    curr_egilim = get_val('Egilim')
                    idx_e = opt_egilim.index(curr_egilim) if curr_egilim in opt_egilim else 0
                    yeni_egilim = st.selectbox("2026 Eğilimi", opt_egilim, index=idx_e)

                    opt_temas = ["", "Kendim Görüştüm", "Arkadaşım/Akraba Aracılığı", "Tanımıyorum"]
                    curr_temas = get_val('Temas_Durumu')
                    idx_t = opt_temas.index(curr_temas) if curr_temas in opt_temas else 0
                    yeni_temas = st.selectbox("Temas Şekli", opt_temas, index=idx_t)

                    opt_ulasim = ["", "Kendisi Gelir", "Araç Gerekir", "İlçeden Gelecek", "Temsilcilikten Gelecek"]
                    curr_ulasim = get_val('Ulasim')
                    idx_u = opt_ulasim.index(curr_ulasim) if curr_ulasim in opt_ulasim else 0
                    yeni_ulasim = st.selectbox("Ulaşım", opt_ulasim, index=idx_u)

                yeni_not = st.text_area("📝 Notlar (Sıfırdan Girin)", value=get_val('Cizikler'))
                yeni_rakip = st.text_input("Rakip Ekleme", value=get_val('Rakip_Ekleme'))
                yeni_referans = st.text_input("Referans", value=get_val('Referans'))

                # --- KAYDETME İŞLEMİ (HATASIZ) ---
                if st.form_submit_button("✅ KAYDET"):
                    try:
                        headers = df.columns.tolist()
                        updates = [
                            ("Kurum", yeni_kurum), ("Gecmis_2024", yeni_24), ("Gecmis_2022", yeni_22),
                            ("Referans", yeni_referans), ("Egilim", yeni_egilim), ("Temas_Durumu", yeni_temas),
                            ("Ulasim", yeni_ulasim), ("Cizikler", yeni_not), ("Rakip_Ekleme", yeni_rakip),
                            ("Son_Guncelleyen", user['Kullanici_Adi'])
                        ]
                        
                        # Ana Tabloyu Güncelle
                        for col, val in updates:
                            if col in headers:
                                ws.update_cell(row_num, headers.index(col) + 1, val)
                        
                        # LOGLARA EKLE
                        if ws_log:
                            now = datetime.now(pytz.timezone('Turkey')).strftime("%Y-%m-%d %H:%M")
                            ws_log.append_row([
                                now, str(sicil_no), kisi['Ad_Soyad'], user['Kullanici_Adi'],
                                yeni_kurum, yeni_24, yeni_22, yeni_egilim, yeni_temas, yeni_rakip, yeni_ulasim, yeni_not
                            ])
                        st.success("Veri başarıyla işlendi!")
                    except Exception as e:
                        st.error(f"Hata: {e}")

        # --- SAĞ TARAF (GEÇMİŞ) ---
        with c_log:
            if user['Rol'] == 'ADMIN':
                st.info("🕒 Geçmiş Loglar (Sadece Admin)")
                if not df_log.empty:
                    logs = df_log[df_log['Sicil_No'].astype(str) == str(sicil_no)]
                    if not logs.empty:
                        for i, r in logs.iloc[::-1].iterrows():
                            st.caption(f"{r['Zaman']} - {r['Kullanici']}")
                            # Egilim sütununu kontrol ederek yazdır
                            e_val = r['Egilim'] if 'Egilim' in r else '-'
                            st.write(f"**{e_val}**")
                            st.divider()
                    else:
                        st.write("Kayıt yok.")
            else:
                st.info("🔒 Geçmiş kayıtlar gizlidir.")
