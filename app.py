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

# --- 2. VERİLERİ ÇEK (LOG DAHİL) ---
def get_data():
    client = get_connection()
    try:
        sheet = client.open("Van_IMO_Secim_2026")
        
        # Ana Liste
        ws = sheet.worksheet("secmenler")
        data = ws.get_all_records()
        df = pd.DataFrame(data)
        df.columns = df.columns.str.strip() # Boşluk temizliği
        df = df.astype(str)
        
        # Log Kayıtları (İstihbarat)
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
                    st.error("❌ Hatalı Kullanıcı Adı veya Şifre")
            except Exception as e:
                st.error(f"Bağlantı Hatası: {e}")
    st.stop()

# --- 4. ANA PROGRAM ---
user = st.session_state.user
st.sidebar.success(f"Aktif: {user['Kullanici_Adi']} ({user['Rol']})")

if st.sidebar.button("Çıkış Yap"):
    st.session_state.user = None
    st.rerun()

df, ws, df_log, ws_log = get_data()

if df is None:
    st.error("Veri çekilemedi. Lütfen sayfayı yenileyin.")
    st.stop()

# --- MENÜ ---
menu = st.sidebar.radio("Menü", ["📊 DETAYLI ANALİZ RAPORU", "📝 Seçmen Kartı & Veri Girişi"])

# ==========================================
# EKRAN 1: ANALİZ RAPORU (YENİ VE GELİŞMİŞ)
# ==========================================
if menu == "📊 DETAYLI ANALİZ RAPORU":
    st.title("📊 Seçim Strateji Raporu")
    
    # --- TEMEL RAKAMLAR ---
    toplam = len(df)
    # Eğilimi dolu olanlar (Veri girilmiş)
    ulasilan_df = df[df['Egilim'].str.len() > 1]
    ulasilan = len(ulasilan_df)
    
    # Bizim Oylar (Sarı Blok + Büyük Kısmı)
    bizimkiler = ulasilan_df[ulasilan_df['Egilim'].isin(["Tüm Listemizi Yazar", "Büyük Kısmı Yazar"])]
    bizim_sayi = len(bizimkiler)
    
    # Oranlar
    ulasma_orani = int(ulasilan/toplam*100) if toplam else 0
    basari_orani = int(bizim_sayi/ulasilan*100) if ulasilan else 0
    
    # Metrikler
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Toplam Seçmen", toplam)
    c2.metric("Temas Edilen", ulasilan, f"%{ulasma_orani}")
    c3.metric("🟡 KEMİK OYUMUZ", bizim_sayi, f"Temasın %{basari_orani}'si")
    c4.metric("Kalan (Ulaşılacak)", toplam - ulasilan)
    
    st.divider()
    
    if ulasilan > 0:
        # --- TAB 1: GENEL DURUM ---
        tab1, tab2, tab3 = st.tabs(["Genel Pasta", "🏢 Kurumsal Analiz", "🔄 Geçiş/Swing Analizi"])
        
        with tab1:
            col_gen1, col_gen2 = st.columns(2)
            with col_gen1:
                st.subheader("Genel Oy Dağılımı")
                fig_genel = px.pie(ulasilan_df, names='Egilim', title='Tüm Görüşülenlerin Dağılımı', hole=0.4)
                st.plotly_chart(fig_genel, use_container_width=True)
            with col_gen2:
                st.subheader("Temas Durumu")
                fig_temas = px.bar(ulasilan_df, x='Temas_Durumu', title="Nasıl Ulaşıldı?", color='Temas_Durumu')
                st.plotly_chart(fig_temas, use_container_width=True)

        # --- TAB 2: SEKTÖREL / KURUMSAL ANALİZ ---
        with tab2:
            st.info("Hangi kurumda ne kadar güçlüyüz? (Sadece 'Sarı Blok' ve 'Büyük Kısmı Yazar' oyları baz alınmıştır)")
            
            # Kurumlara göre bizimkilerin sayısı
            kurum_dagilim = bizimkiler['Kurum'].value_counts().reset_index()
            kurum_dagilim.columns = ['Kurum', 'Oylarımız']
            
            fig_kurum = px.bar(kurum_dagilim, x='Kurum', y='Oylarımız', color='Oylarımız', 
                               title="Kurumlara Göre Destekçi Sayımız", text_auto=True)
            st.plotly_chart(fig_kurum, use_container_width=True)
            
            # Detaylı Tablo
            st.markdown("##### 🕵️‍♂️ Sektör Bazlı Detay Tablo")
            pivot_table = pd.crosstab(ulasilan_df['Kurum'], ulasilan_df['Egilim'])
            st.dataframe(pivot_table, use_container_width=True)

        # --- TAB 3: SWING / GEÇİŞ ANALİZİ ---
        with tab3:
            st.subheader("2024'ten 2026'ya Oy Geçişleri")
            st.markdown("⚠️ **En Kritik Tablo:** Geçen seçim kime verdi, şimdi ne diyor?")
            
            # Sankey mantığı yerine anlaşılır Bar Chart
            # Sadece geçmiş verisi olanları al
            gecis_df = ulasilan_df[ulasilan_df['Gecmis_2024'].str.len() > 1]
            
            if not gecis_df.empty:
                fig_gecis = px.histogram(gecis_df, x="Gecmis_2024", color="Egilim", 
                                       title="2024 Tercihine Göre Şimdiki Dağılım", barmode='group')
                st.plotly_chart(fig_gecis, use_container_width=True)
                
                # ÖZEL ANALİZ: KAZANILANLAR
                # Geçmişte Mavi olup şimdi Sarı olanlar
                kazanilanlar = gecis_df[
                    (gecis_df['Gecmis_2024'].str.contains('Mavi', case=False)) & 
                    (gecis_df['Egilim'].str.contains('Yazar', case=False))
                ]
                st.success(f"🏆 **TRANSFER BAŞARISI:** Geçen seçim MAVİ LİSTE verip, bu seçim BİZİ destekleyen **{len(kazanilanlar)}** kişi var!")
                if len(kazanilanlar) > 0:
                    with st.expander("Bu Kahramanları Gör"):
                        st.dataframe(kazanilanlar[['Ad_Soyad', 'Kurum', 'Referans']])
            else:
                st.warning("Geçiş analizi için 'Gecmis_2024' verilerinin girilmesi lazım.")

    else:
        st.info("Analiz ekranının açılması için en az 1 kişiye veri girmelisiniz.")

# ==========================================
# EKRAN 2: SEÇMEN KARTI & VERİ GİRİŞİ (LOGLU)
# ==========================================
elif menu == "📝 Seçmen Kartı & Veri Girişi":
    st.header("📋 Seçmen Yönetimi")
    
    # Arama
    search_term = st.text_input("🔎 İsimle Hızlı Ara", placeholder="Örn: Ahmet")
    
    desired_columns = ['Sicil_No', 'Ad_Soyad', 'Kurum', 'Egilim', 'Son_Guncelleyen']
    available_columns = [col for col in desired_columns if col in df.columns]

    if search_term:
        df_display = df[df['Ad_Soyad'].str.contains(search_term, case=False, na=False)]
    else:
        df_display = df

    event = st.dataframe(
        df_display[available_columns],
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row"
    )

    if len(event.selection.rows) > 0:
        selected_row_idx = event.selection.rows[0]
        sicil_no = df_display.iloc[selected_row_idx]['Sicil_No']
        
        # Kişiyi bul
        gercek_index = df[df['Sicil_No'] == sicil_no].index[0]
        row_num = gercek_index + 2
        kisi = df.iloc[gercek_index]

        st.divider()
        
        # İki kolonlu yapı: Sol Taraf Giriş, Sağ Taraf Tarihçe
        col_main, col_hist = st.columns([2, 1])

        with col_main:
            st.markdown(f"### ✏️ Düzenle: **{kisi['Ad_Soyad']}**")
            with st.form("guncelleme_formu"):
                c1, c2 = st.columns(2)
                with c1:
                    st.caption("🏢 Kurumsal & Geçmiş")
                    # Kurum
                    opt_kurum = ["", "Özel Sektör", "Dsi", "Karayolları", "Büyükşehir", "Vaski", "Projeci", "Yapı Denetimci", "İlçe Belediyeleri", "Müteahhit", "Yapsat", "Diğer"]
                    curr_kurum = kisi.get('Kurum', "")
                    yeni_kurum = st.selectbox("Kurum", opt_kurum, index=opt_kurum.index(curr_kurum) if curr_kurum in opt_kurum else 0)
                    
                    # 2024
                    opt_24 = ["", "Sarı Liste", "Mavi Liste"]
                    curr_24 = kisi.get('Gecmis_2024', "")
                    yeni_24 = st.selectbox("2024 Tercihi", opt_24, index=opt_24.index(curr_24) if curr_24 in opt_24 else 0)
                    
                    # Referans
                    yeni_referans = st.text_input("Referans", value=kisi.get('Referans', ""))

                with c2:
                    st.caption("🗳️ 2026 Durumu")
                    # Eğilim
                    opt_egilim = ["", "Tüm Listemizi Yazar", "Büyük Kısmı Yazar", "Kısmen Yazar", "Karşı Tarafı Destekler", "Kararsızım"]
                    curr_egilim = kisi.get('Egilim', "")
                    yeni_egilim = st.selectbox("2026 Eğilimi", opt_egilim, index=opt_egilim.index(curr_egilim) if curr_egilim in opt_egilim else 0)

                    # Temas
                    opt_temas = ["", "Kendim Görüştüm", "Arkadaşım/Akraba Aracılığı", "Tanımıyorum"]
                    curr_temas = kisi.get('Temas_Durumu', "")
                    yeni_temas = st.selectbox("Temas Şekli", opt_temas, index=opt_temas.index(curr_temas) if curr_temas in opt_temas else 0)
                    
                    # Ulaşım
                    opt_ulasim = ["", "Kendisi Gelir", "Araç Gerekir", "İlçeden Gelecek", "Temsilcilikten Gelecek"]
                    curr_ulasim = kisi.get('Ulasim', "")
                    yeni_ulasim = st.selectbox("Ulaşım", opt_ulasim, index=opt_ulasim.index(curr_ulasim) if curr_ulasim in opt_ulasim else 0)
                
                # Notlar (Geni
