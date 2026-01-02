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
# EKRAN 1: 360 DERECE DERİN ANALİZ (SADECE ADMIN) - TAM KAPSAMLI
# =========================================================
if menu == "📊 360° DERİN ANALİZ" and user['Rol'] == 'ADMIN':
    st.title("📊 STRATEJİK İSTİHBARAT RAPORU")
    
    # Veri Hazırlığı
    toplam_uye = len(df)
    temas_df = df[df['Egilim'].str.len() > 1]
    temas_sayisi = len(temas_df)
    temas_orani = int(temas_sayisi / toplam_uye * 100) if toplam_uye else 0
    
    bizimkiler = temas_df[temas_df['Egilim'].isin(["Tüm Listemizi Yazar", "Büyük Kısmı Yazar"])]
    bizim_sayi = len(bizimkiler)
    
    # Sicil Temizleme ve Dönüştürme
    def clean_sicil(x):
        try:
            return int(str(x).replace(".", ""))
        except:
            return 0
    
    # Kopya oluşturup işlem yapıyoruz (Hata önleyici)
    analiz_df = temas_df.copy()
    analiz_df['Sicil_Int'] = analiz_df['Sicil_No'].apply(clean_sicil)

    # --- ÜST METRİKLER ---
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Toplam Üye", toplam_uye)
    c2.metric("Sahada Dokunulan", temas_sayisi, f"%{temas_orani}")
    c3.metric("🟡 KEMİK OYUMUZ", bizim_sayi, f"Temasın %{int(bizim_sayi/temas_sayisi*100) if temas_sayisi else 0}'i")
    c4.metric("Kalan Hedef", toplam_uye - temas_sayisi, delta_color="inverse")

    st.divider()

    # --- DETAYLI ANALİZ SEKMELERİ (ESKİ KALİTE GERİ GELDİ) ---
    tab1, tab2, tab3, tab4 = st.tabs([
        "🌍 Genel Durum", 
        "🏗️ Sicil & Kuşak Analizi", 
        "🏢 Kurumsal Röntgen", 
        "🏎️ Ekip Ligi"
    ])

    # 1. GENEL DURUM
    with tab1:
        c_pie, c_sankey = st.columns(2)
        with c_pie:
            st.subheader("Genel Dağılım")
            fig_pie = px.pie(analiz_df, names='Egilim', hole=0.4, title="Ulaşılanların Tercihleri")
            st.plotly_chart(fig_pie, use_container_width=True)
        with c_sankey:
             st.subheader("2024 -> 2026 Geçiş Analizi")
             if 'Gecmis_2024' in analiz_df.columns:
                gecis = analiz_df[analiz_df['Gecmis_2024'].str.len() > 1]
                if not gecis.empty:
                    fig_s = px.histogram(gecis, x="Gecmis_2024", color="Egilim", barmode="group", title="Sadakat ve Kayma Analizi")
                    st.plotly_chart(fig_s, use_container_width=True)
                else:
                    st.info("2024 verisi girilmemiş.")

    # 2. SİCİL & KUŞAK ANALİZİ (GERİ GELDİ!)
    with tab2:
        st.info("Genç Mühendisler (Yüksek Sicil) vs Eski Topraklar (Düşük Sicil) Analizi")
        # Kuşakları Belirle
        bins = [0, 15000, 25000, 35000, 100000]
        labels = ['Eski Toprak (0-15k)', 'Kıdemli (15k-25k)', 'Orta Kuşak (25k-35k)', 'Yeni Mezun (35k+)']
        analiz_df['Kusak'] = pd.cut(analiz_df['Sicil_Int'], bins=bins, labels=labels)

        col_s1, col_s2 = st.columns(2)
        with col_s1:
            st.subheader("Hangi Kuşakta Güçlüyüz?")
            # Sadece bizim oyların kuşak dağılımı
            bizim_kusak = analiz_df[analiz_df['Egilim'].isin(["Tüm Listemizi Yazar", "Büyük Kısmı Yazar"])]
            if not bizim_kusak.empty:
                fig_kusak = px.bar(bizim_kusak['Kusak'].value_counts().reset_index(), x='Kusak', y='count', 
                                   title="Bize Oy Verenlerin Kuşak Dağılımı", color='Kusak')
                st.plotly_chart(fig_kusak, use_container_width=True)
            else:
                st.warning("Henüz yeterli veri yok.")

        with col_s2:
            st.subheader("Kuşaklara Göre Tüm Eğilimler")
            kusak_pivot = pd.crosstab(analiz_df['Kusak'], analiz_df['Egilim'])
            st.dataframe(kusak_pivot, use_container_width=True)

    # 3. KURUMSAL RÖNTGEN
    with tab3:
        st.subheader("Kurum Bazlı Başarı")
        kurum_genel = analiz_df['Kurum'].value_counts().reset_index()
        kurum_genel.columns = ['Kurum', 'Toplam']
        kurum_bizim = bizimkiler['Kurum'].value_counts().reset_index()
        kurum_bizim.columns = ['Kurum', 'Bizim']
        
        merged = pd.merge(kurum_genel, kurum_bizim, on='Kurum', how='left').fillna(0)
        # Sadece en az 1 kişinin olduğu kurumları al
        merged = merged[merged['Toplam'] > 0]
        merged['Oran'] = (merged['Bizim'] / merged['Toplam'] * 100).astype(int)
        
        fig_k = px.bar(merged, x='Kurum', y='Oran', color='Oran', title="Kurumlardaki Başarı Oranımız (%)", text='Bizim')
        st.plotly_chart(fig_k, use_container_width=True)
    
    # 4. EKİP PERFORMANSI
    with tab4:
        st.subheader("Saha Ekibi Ligi")
        if not df_log.empty:
            perf = df_log['Kullanici'].value_counts().reset_index()
            perf.columns = ['Kullanici', 'Islem']
            st.bar_chart(perf.set_index('Kullanici'))
            
            st.markdown("##### 📝 Son Log Hareketleri")
            st.dataframe(df_log.tail(15).sort_index(ascending=False), use_container_width=True)
        else:
            st.info("Log kaydı bulunamadı.")

# =========================================================
# EKRAN 2: SEÇMEN KARTI (KÖR GİRİŞ + SAĞLAM LOGLAMA)
# =========================================================
elif menu == "📝 Seçmen Kartı & Giriş":
    st.header("📋 Seçmen Veri Girişi")
    
    # MOD BİLGİLENDİRMESİ
    if user['Rol'] == 'ADMIN':
        st.info("🔓 ADMIN MODU: Tüm veriler açık.")
    else:
        st.warning("🔒 SAHA MODU: Gizli Veri Girişi (Kör Giriş Aktif).")

    search_term = st.text_input("🔎 İsimle Ara", placeholder="Örn: Ahmet")
    
    # LİSTE GÖRÜNÜMÜ: SAHA ELEMANI KRİTİK VERİYİ LİSTEDE GÖRMESİN
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
                # --- KÖR GİRİŞ MANTIĞI ---
                def get_val(field):
                    if user['Rol'] == 'ADMIN':
                        return kisi.get(field, "")
                    else:
                        return "" # Saha elemanına boş göster
                
                curr_kurum = kisi.get('Kurum', "") 
                
                c1, c2 = st.columns(2)
                with c1:
                    opt_kurum = ["", "Özel Sektör", "Dsi", "Karayolları", "Büyükşehir", "Vaski", "Projeci", "Yapı Denetimci", "İlçe Belediyeleri", "Müteahhit", "Yapsat", "Diğer"]
                    idx_k = opt_kurum.index(curr_kurum) if curr_kurum in opt_kurum else 0
                    yeni_kurum = st.selectbox("Kurum", opt_kurum, index=idx_k)
                    
                    # GEÇMİŞ (Admin Görür, Saha Görmez)
                    opt_24 = ["", "Sarı Liste", "Mavi Liste"]
                    curr_24 = get_val('Gecmis_2024')
                    idx_24 = opt_24.index(curr_24) if curr_24 in opt_24 else 0
                    yeni_24 = st.selectbox("2024 Tercihi", opt_24, index=idx_24)

                    opt_22 = ["", "Sarı Liste", "Mavi Liste", "Beyaz Liste"]
                    curr_22 = get_val('Gecmis_2022')
                    idx_22 = opt_22.index(curr_22) if curr_22 in opt_22 else 0
                    yeni_22 = st.selectbox("2022 Tercihi", opt_22, index=idx_22)

                with c2:
                    # EĞİLİM (Admin Görür, Saha Görmez)
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

                yeni_not = st.text_area("📝 Notlar", value=get_val('Cizikler'))
                yeni_rakip = st.text_input("Rakip Ekleme", value=get_val('Rakip_Ekleme'))
                yeni_referans = st.text_input("Referans", value=get_val('Referans'))

                # --- KAYDETME İŞLEMİ ---
                if st.form_submit_button("✅ KAYDET"):
                    try:
                        headers = df.columns.tolist()
                        updates = [
                            ("Kurum", yeni_kurum), ("Gecmis_2024", yeni_24), ("Gecmis_2022", yeni_22),
                            ("Referans", yeni_referans), ("Egilim", yeni_egilim), ("Temas_Durumu", yeni_temas),
                            ("Ulasim", yeni_ulasim), ("Cizikler", yeni_not), ("Rakip_Ekleme", yeni_rakip),
                            ("Son_Guncelleyen", user['Kullanici_Adi'])
                        ]
                        
                        # 1. ANA TABLOYU GÜNCELLE
                        for col, val in updates:
                            if col in headers:
                                ws.update_cell(row_num, headers.index(col) + 1, val)
                        
                        # 2. LOGLARA EKLE (RESİMDEKİ SÜTUN SIRASINA GÖRE)
                        # Sıra: Zaman | Sicil | Ad | Kullanici | Kurum | Gecmis24 | Gecmis22 | Egilim | Temas | Rakip | Ulasim | Not
                        if ws_log:
                            now = datetime.now(pytz.timezone('Turkey')).strftime("%Y-%m-%d %H:%M")
                            
                            # Excel'deki log sayfasına uygun liste
                            log_row = [
                                now,                    # A: Zaman
                                str(sicil_no),          # B: Sicil_No
                                kisi['Ad_Soyad'],       # C: Ad_Soyad
                                user['Kullanici_Adi'],  # D: Kullanici
                                yeni_kurum,             # E: Kurum
                                yeni_egilim,            # F: Egilim (Senin resimde burda var)
                                yeni_24,                # G: Gecmis_2024
                                yeni_22,                # H: Gecmis_2022
                                yeni_temas,             # I: Temas_Durumu
                                yeni_rakip,             # J: Rakip_Ekleme
                                yeni_ulasim,            # K: Ulasim
                                yeni_not                # L: Notlar (Varsa)
                            ]
                            ws_log.append_row(log_row)
                            
                        st.success(f"{kisi['Ad_Soyad']} için veri kaydedildi ve loglandı!")
                    except Exception as e:
                        st.error(f"Hata oluştu: {e}")

        # --- SAĞ TARAF (GEÇMİŞ) ---
        with c_log:
            if user['Rol'] == 'ADMIN':
                st.info("🕒 Geçmiş Hareketler")
                if not df_log.empty:
                    logs = df_log[df_log['Sicil_No'].astype(str) == str(sicil_no)]
                    if not logs.empty:
                        for i, r in logs.iloc[::-1].iterrows():
                            # Log gösterimi
                            st.caption(f"{r['Zaman']} - {r['Kullanici']}")
                            # Veri varsa göster
                            e_val = r['Egilim'] if 'Egilim' in r else '-'
                            st.markdown(f"**{e_val}**")
                            st.divider()
                    else:
                        st.write("Bu kişi için geçmiş kayıt yok.")
            else:
                st.info("🔒 Geçmiş kayıtlar gizlidir.")
