import streamlit as st
import pandas as pd
import gspread
import plotly.express as px
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import pytz

# --- MOBİL UYUMLU AYARLAR ---
st.set_page_config(
    page_title="İMO Van 2026", 
    layout="wide", 
    page_icon="🏗️",
    initial_sidebar_state="collapsed" # Telefondan girince menü kapalı gelsin, yer kaplamasın
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
        ws = sheet.worksheet("secmenler")
        data = ws.get_all_records()
        df = pd.DataFrame(data)
        df.columns = df.columns.str.strip()
        df = df.astype(str)
        
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
    st.title("🏗️ İMO SEÇİM SİSTEMİ")
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
st.sidebar.markdown(f"### 👤 {user['Kullanici_Adi']}")
if st.sidebar.button("Çıkış Yap"):
    st.session_state.user = None
    st.rerun()

df, ws, df_log, ws_log = get_data()

if df is None:
    st.error("Veri alınamadı. Sayfayı yenileyin.")
    st.stop()

# Menü Yapılandırması
if user['Rol'] == 'ADMIN':
    menu = st.sidebar.radio("Menü", ["📊 360° STRATEJİK ANALİZ", "📝 Veri Girişi"])
else:
    menu = st.sidebar.radio("Menü", ["📝 Veri Girişi"])

# =========================================================
# EKRAN 1: 360 DERECE STRATEJİK ANALİZ (SADECE ADMIN)
# =========================================================
if menu == "📊 360° STRATEJİK ANALİZ" and user['Rol'] == 'ADMIN':
    st.title("📊 Seçim Komuta Masası")
    
    # Veri Hazırlığı
    toplam = len(df)
    temas = df[df['Egilim'].str.len() > 1]
    bizimkiler = temas[temas['Egilim'].isin(["Tüm Listemizi Yazar", "Büyük Kısmı Yazar"])]
    kararsizlar = temas[temas['Egilim'].isin(["Kararsızım", "Kısmen Yazar"])]
    
    # Sicil Dönüşüm
    def clean_sicil(x):
        try:
            return int(str(x).replace(".", ""))
        except:
            return 0
    analiz_df = temas.copy()
    analiz_df['Sicil_Int'] = analiz_df['Sicil_No'].apply(clean_sicil)

    # Özet Kartlar
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Toplam Üye", toplam)
    c2.metric("Ulaşılan", len(temas), f"%{int(len(temas)/toplam*100) if toplam else 0}")
    c3.metric("🟡 KEMİK OY", len(bizimkiler))
    c4.metric("⚖️ KARARSIZ (Fırsat)", len(kararsizlar), delta_color="off")

    st.divider()

    # Sekmeler
    tabs = st.tabs(["🎯 AKILLI HEDEF LİSTESİ", "🌍 Genel Durum", "🏗️ Kuşak Analizi", "🏢 Kurumlar", "⚡ Ekip Ligi"])

    # 1. AKILLI HEDEF LİSTESİ (YENİ VE ÖNEMLİ)
    with tabs[0]:
        st.subheader("🎯 Kazanabileceğimiz Seçmenler (Fırsat Listesi)")
        st.info("Bu liste, 'Kararsız' veya 'Kısmen Yazar' diyenleri, senin müdahalenle dönebilecek kişileri gösterir.")
        
        if not kararsizlar.empty:
            # Sadece önemli sütunları al
            hedef_liste = kararsizlar[['Sicil_No', 'Ad_Soyad', 'Kurum', 'Referans', 'Temas_Durumu']].copy()
            st.dataframe(hedef_liste, use_container_width=True, hide_index=True)
            
            st.download_button(
                label="📥 Bu Listeyi İndir (Excel)",
                data=hedef_liste.to_csv(index=False).encode('utf-8'),
                file_name='aranacak_kararsizlar.csv',
                mime='text/csv'
            )
        else:
            st.success("Harika! Şu an sistemde kayıtlı 'Kararsız' üye yok.")

    # 2. GENEL DURUM
    with tabs[1]:
        c_pie, c_bar = st.columns(2)
        with c_pie:
            fig_p = px.pie(analiz_df, names='Egilim', title="Saha Genel Eğilimi", hole=0.4)
            st.plotly_chart(fig_p, use_container_width=True)
        with c_bar:
            if 'Gecmis_2024' in analiz_df.columns:
                gecis = analiz_df[analiz_df['Gecmis_2024'].str.len() > 1]
                if not gecis.empty:
                    fig_s = px.histogram(gecis, x="Gecmis_2024", color="Egilim", barmode="group", title="Sadakat Analizi")
                    st.plotly_chart(fig_s, use_container_width=True)

    # 3. KUŞAK ANALİZİ
    with tabs[2]:
        bins = [0, 15000, 25000, 35000, 100000]
        labels = ['Eski Toprak (0-15k)', 'Kıdemli (15k-25k)', 'Orta Kuşak (25k-35k)', 'Genç (35k+)']
        analiz_df['Kusak'] = pd.cut(analiz_df['Sicil_Int'], bins=bins, labels=labels)
        
        col_k1, col_k2 = st.columns(2)
        with col_k1:
            bizim_kusak = analiz_df[analiz_df['Egilim'].isin(["Tüm Listemizi Yazar", "Büyük Kısmı Yazar"])]
            if not bizim_kusak.empty:
                fig_k = px.bar(bizim_kusak['Kusak'].value_counts().reset_index(), x='Kusak', y='count', title="Kemik Oylarımızın Yaş Dağılımı", color='Kusak')
                st.plotly_chart(fig_k, use_container_width=True)
        with col_k2:
            st.dataframe(pd.crosstab(analiz_df['Kusak'], analiz_df['Egilim']), use_container_width=True)

    # 4. KURUMLAR
    with tabs[3]:
        kurum_genel = analiz_df['Kurum'].value_counts().reset_index()
        kurum_genel.columns = ['Kurum', 'Toplam']
        kurum_bizim = bizimkiler['Kurum'].value_counts().reset_index()
        kurum_bizim.columns = ['Kurum', 'Bizim']
        merged = pd.merge(kurum_genel, kurum_bizim, on='Kurum', how='left').fillna(0)
        merged = merged[merged['Toplam'] > 0]
        merged['Oran'] = (merged['Bizim'] / merged['Toplam'] * 100).astype(int)
        
        fig_kurum = px.bar(merged, x='Kurum', y='Oran', text='Bizim', color='Oran', title="Kurum Bazlı Hakimiyet (%)")
        st.plotly_chart(fig_kurum, use_container_width=True)

    # 5. EKİP LİGİ
    with tabs[4]:
        if not df_log.empty:
            perf = df_log['Kullanici'].value_counts().reset_index()
            perf.columns = ['Saha Elemanı', 'Veri Sayısı']
            st.bar_chart(perf.set_index('Saha Elemanı'))
            st.caption("Son Veri Girişleri:")
            st.dataframe(df_log.tail(10).sort_index(ascending=False), use_container_width=True)

# =========================================================
# EKRAN 2: SEÇMEN KARTI (KÖR GİRİŞ AKTİF)
# =========================================================
elif menu == "📝 Veri Girişi":
    st.header("📋 Seçmen Bilgi Girişi")
    
    # YETKİ KONTROLÜ
    is_admin = (user['Rol'] == 'ADMIN')
    
    if is_admin:
        st.success("YETKİLİ: Tüm veriler açık.")
    else:
        st.info("SAHA MODU: Gizli giriş aktif.")

    search = st.text_input("🔍 İsim Ara", placeholder="Ad Soyad...")
    
    # Liste Görünümü Ayarı
    cols = ['Sicil_No', 'Ad_Soyad', 'Kurum', 'Egilim', 'Son_Guncelleyen'] if is_admin else ['Sicil_No', 'Ad_Soyad', 'Kurum']
    
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
        c_form, c_hist = st.columns([2, 1])

        with c_form:
            st.markdown(f"### ✏️ **{kisi['Ad_Soyad']}**")
            with st.form("entry_form"):
                
                # --- Kör Giriş Fonksiyonu ---
                def get(f): return kisi.get(f, "") if is_admin else ""
                
                # 1. Satır
                c1, c2 = st.columns(2)
                with c1:
                    opts_kurum = ["", "Özel Sektör", "Dsi", "Karayolları", "Büyükşehir", "Vaski", "Projeci", "Yapı Denetimci", "İlçe Belediyeleri", "Müteahhit", "Yapsat", "Diğer"]
                    curr_k = kisi.get('Kurum', "") # Kurum hep görünür
                    idx_k = opts_kurum.index(curr_k) if curr_k in opts_kurum else 0
                    n_kurum = st.selectbox("Kurum", opts_kurum, index=idx_k)

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
                        
                        # Excel Update
                        for col, val in updates:
                            if col in headers:
                                ws.update_cell(row_n, headers.index(col)+1, val)
                        
                        # Log Update
                        if ws_log:
                            now = datetime.now(pytz.timezone('Turkey')).strftime("%Y-%m-%d %H:%M")
                            log_data = [
                                now, str(sicil), kisi['Ad_Soyad'], user['Kullanici_Adi'],
                                n_kurum, n_egilim, n_24, n_22, n_temas, n_rakip, n_ulasim, n_not
                            ]
                            ws_log.append_row(log_data)
                            
                        st.success("Kaydedildi!")
                    except Exception as e:
                        st.error(f"Hata: {e}")

        with c_hist:
            if is_admin:
                st.info("🕒 Geçmiş")
                if not df_log.empty:
                    l = df_log[df_log['Sicil_No'].astype(str) == str(sicil)]
                    if not l.empty:
                        for i, r in l.iloc[::-1].iterrows():
                            st.caption(f"{r['Zaman']} - {r['Kullanici']}")
                            e_txt = r['Egilim'] if 'Egilim' in r else '-'
                            st.markdown(f"**{e_txt}**")
                            st.divider()
                    else:
                        st.write("-")
            else:
                st.caption("🔒 Geçmiş Gizli")
