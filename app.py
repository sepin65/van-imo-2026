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
    st.title("🏗️ İMO SEÇİM KOMUTA MERKEZİ")
    with st.form("giris_formu"):
        kadi = st.text_input("Kullanıcı Adı")
        sifre = st.text_input("Şifre", type="password")
        # BUTON FORMUN İÇİNDE
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
st.sidebar.success(f"👮‍♂️ {user['Kullanici_Adi']} ({user['Rol']})")
if st.sidebar.button("Çıkış"):
    st.session_state.user = None
    st.rerun()

df, ws, df_log, ws_log = get_data()

if df is None:
    st.error("Veri alınamadı. Sayfayı yenileyin.")
    st.stop()

menu = st.sidebar.radio("Menü", ["📊 360° DERİN ANALİZ", "📝 Seçmen Kartı & Giriş"])

# =========================================================
# EKRAN 1: 360 DERECE DERİN ANALİZ (İSTATİSTİK CANAVARI)
# =========================================================
if menu == "📊 360° DERİN ANALİZ":
    st.title("📊 STRATEJİK İSTİHBARAT RAPORU")
    
    # --- VERİ HAZIRLIĞI ---
    toplam_uye = len(df)
    temas_df = df[df['Egilim'].str.len() > 1]
    temas_sayisi = len(temas_df)
    temas_orani = int(temas_sayisi / toplam_uye * 100) if toplam_uye else 0
    
    # Bizimkiler
    bizimkiler = temas_df[temas_df['Egilim'].isin(["Tüm Listemizi Yazar", "Büyük Kısmı Yazar"])]
    bizim_sayi = len(bizimkiler)
    
    # Sicil Analizi için Sayısal Dönüşüm
    def clean_sicil(x):
        try:
            return int(str(x).replace(".", ""))
        except:
            return 0
    
    temas_df = temas_df.copy()
    temas_df['Sicil_Int'] = temas_df['Sicil_No'].apply(clean_sicil)

    # --- ÜST METRİKLER ---
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Toplam Üye", toplam_uye)
    c2.metric("Sahada Dokunulan", temas_sayisi, f"%{temas_orani}")
    c3.metric("🟡 KEMİK OYUMUZ", bizim_sayi, f"Temasın %{int(bizim_sayi/temas_sayisi*100) if temas_sayisi else 0}'i")
    c4.metric("Kalan Hedef", toplam_uye - temas_sayisi, delta_color="inverse")

    st.divider()

    # --- SEKME SEKME ANALİZ ---
    tab1, tab2, tab3, tab4 = st.tabs([
        "🌍 Genel Durum", 
        "🏗️ Sicil & Kuşak Analizi", 
        "🏢 Kurumsal Röntgen", 
        "🏎️ Ekip Performansı"
    ])

    # 1. GENEL DURUM
    with tab1:
        col_a, col_b = st.columns(2)
        with col_a:
            st.subheader("Ulaşılanların Tercih Dağılımı")
            fig_pie = px.pie(temas_df, names='Egilim', hole=0.4)
            st.plotly_chart(fig_pie, use_container_width=True)
        
        with col_b:
            st.subheader("2024 -> 2026 Geçişleri")
            if 'Gecmis_2024' in temas_df.columns:
                gecis_df = temas_df[temas_df['Gecmis_2024'].str.len() > 1]
                if not gecis_df.empty:
                    fig_sankey = px.histogram(gecis_df, x="Gecmis_2024", color="Egilim", barmode="group", 
                                          title="Geçmiş Tercihe Göre Şimdiki Durum")
                    st.plotly_chart(fig_sankey, use_container_width=True)
                else:
                    st.info("Geçmiş verisi girilmemiş.")

    # 2. SİCİL & KUŞAK ANALİZİ
    with tab2:
        bins = [0, 15000, 25000, 35000, 100000]
        labels = ['Eski Toprak (0-15k)', 'Kıdemli (15k-25k)', 'Orta Kuşak (25k-35k)', 'Yeni Mezun (35k+)']
        temas_df['Kusak'] = pd.cut(temas_df['Sicil_Int'], bins=bins, labels=labels)

        col_s1, col_s2 = st.columns(2)
        with col_s1:
            st.subheader("Hangi Kuşakta Güçlüyüz?")
            bizim_kusak = temas_df[temas_df['Egilim'].isin(["Tüm Listemizi Yazar", "Büyük Kısmı Yazar"])]
            fig_kusak = px.bar(bizim_kusak['Kusak'].value_counts().reset_index(), x='Kusak', y='count', 
                               title="Bize Oy Verenlerin Kuşak Dağılımı", color='Kusak')
            st.plotly_chart(fig_kusak, use_container_width=True)

        with col_s2:
            st.subheader("Kuşaklara Göre Eğilim Tablosu")
            kusak_pivot = pd.crosstab(temas_df['Kusak'], temas_df['Egilim'])
            st.dataframe(kusak_pivot, use_container_width=True)

    # 3. KURUMSAL RÖNTGEN
    with tab3:
        st.subheader("Kurum Bazlı Başarı Oranı")
        kurum_genel = temas_df['Kurum'].value_counts().reset_index()
        kurum_genel.columns = ['Kurum', 'Toplam_Gorusulen']
        
        kurum_bizim = bizimkiler['Kurum'].value_counts().reset_index()
        kurum_bizim.columns = ['Kurum', 'Bizim_Oy']
        
        merged = pd.merge(kurum_genel, kurum_bizim, on='Kurum', how='left').fillna(0)
        merged['Başarı (%)'] = (merged['Bizim_Oy'] / merged['Toplam_Gorusulen'] * 100).astype(int)
        
        fig_kurum = px.bar(merged, x='Kurum', y='Başarı (%)', color='Başarı (%)', 
                           text='Bizim_Oy', title="Kurumlardaki Hakimiyet Oranımız (%)", height=500)
        st.plotly_chart(fig_kurum, use_container_width=True)

    # 4. EKİP PERFORMANSI
    with tab4:
        st.subheader("Saha Ekibi Performans Ligi")
        if not df_log.empty:
            performans = df_log['Kullanici'].value_counts().reset_index()
            performans.columns = ['Saha Elemanı', 'İşlem Sayısı']
            fig_perf = px.bar(performans, x='Saha Elemanı', y='İşlem Sayısı', color='İşlem Sayısı', text='İşlem Sayısı')
            st.plotly_chart(fig_perf, use_container_width=True)
            
            st.markdown("##### 📝 Son 10 Hareket")
            st.dataframe(df_log.tail(10).sort_index(ascending=False), use_container_width=True)
        else:
            st.info("Henüz log kaydı oluşmadı.")


# =========================================================
# EKRAN 2: SEÇMEN KARTI & VERİ GİRİŞİ (HATASIZ FORM)
# =========================================================
elif menu == "📝 Seçmen Kartı & Giriş":
    st.header("📋 Seçmen Yönetimi")
    
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
        idx = event.selection.rows[0]
        sicil_no = df_display.iloc[idx]['Sicil_No']
        
        # Gerçek veriyi bul
        gercek_index = df[df['Sicil_No'] == sicil_no].index[0]
        row_num = gercek_index + 2
        kisi = df.iloc[gercek_index]

        st.divider()
        col_main, col_hist = st.columns([2, 1])

        with col_main:
            st.markdown(f"### ✏️ Düzenle: **{kisi['Ad_Soyad']}**")
            
            # --- FORM BAŞLANGICI ---
            with st.form("veri_giris_formu"):
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

                    # 2022 (DÜZELTİLDİ: ARTIK KAYDEDİLECEK)
                    opt_22 = ["", "Sarı Liste", "Mavi Liste", "Beyaz Liste"]
                    curr_22 = kisi.get('Gecmis_2022', "")
                    yeni_22 = st.selectbox("2022 Tercihi", opt_22, index=opt_22.index(curr_22) if curr_22 in opt_22 else 0)
                    
                    yeni_referans = st.text_input("Referans", value=kisi.get('Referans', ""))

                with c2:
                    st.caption("🗳️ 2026 Durumu")
                    opt_egilim = ["", "Tüm Listemizi Yazar", "Büyük Kısmı Yazar", "Kısmen Yazar", "Karşı Tarafı Destekler", "Kararsızım"]
                    curr_egilim = kisi.get('Egilim', "")
                    yeni_egilim = st.selectbox("2026 Eğilimi", opt_egilim, index=opt_egilim.index(curr_egilim) if curr_egilim in opt_egilim else 0)

                    # Temas Durumu (DÜZELTİLDİ: ARTIK KAYDEDİLECEK)
                    opt_temas = ["", "Kendim Görüştüm", "Arkadaşım/Akraba Aracılığı", "Tanımıyorum"]
                    curr_temas = kisi.get('Temas_Durumu', "")
                    yeni_temas = st.selectbox("Temas Şekli", opt_temas, index=opt_temas.index(curr_temas) if curr_temas in opt_temas else 0)

                    opt_ulasim = ["", "Kendisi Gelir", "Araç Gerekir", "İlçeden Gelecek", "Temsilcilikten Gelecek"]
                    curr_ulasim = kisi.get('Ulasim', "")
                    yeni_ulasim = st.selectbox("Ulaşım", opt_ulasim, index=opt_ulasim.index(curr_ulasim) if curr_ulasim in opt_ulasim else 0)

                    yeni_rakip = st.text_input("Rakip Ekleme", value=kisi.get('Rakip_Ekleme', ""))

                # Notlar
                yeni_cizik = st.text_area("📝 Notlar / Çizikler", value=kisi.get('Cizikler', ""))

                # --- KAYDET BUTONU ---
                submitted = st.form_submit_button("✅ BİLGİLERİ KAYDET")
                
                if submitted:
                    try:
                        headers = df.columns.tolist()
                        # LİSTEYE EKSİK OLANLARI EKLEDİM
                        updates = [
                            ("Kurum", yeni_kurum), 
                            ("Gecmis_2024", yeni_24),
                            ("Gecmis_2022", yeni_22),     # EKLENDİ
                            ("Referans", yeni_referans), 
                            ("Egilim", yeni_egilim),
                            ("Temas_Durumu", yeni_temas), # EKLENDİ
                            ("Ulasim", yeni_ulasim), 
                            ("Cizikler", yeni_cizik), 
                            ("Rakip_Ekleme", yeni_rakip),
                            ("Son_Guncelleyen", user['Kullanici_Adi'])
                        ]
                        
                        # 1. Ana Excel Güncelleme
                        for col_name, val in updates:
                            if col_name in headers:
                                ws.update_cell(row_num, headers.index(col_name) + 1, val)
                        
                        # 2. Log Kaydı (TÜM DETAYLARIYLA)
                        if ws_log:
                            zaman = datetime.now(pytz.timezone('Turkey')).strftime("%Y-%m-%d %H:%M")
                            # Sıra: Zaman, Sicil, Isim, Kullanici, Kurum, Gecmis24, Gecmis22, Egilim, Temas, Rakip, Ulasim, Not
                            ws_log.append_row([
                                zaman, str(sicil_no), kisi['Ad_Soyad'], user['Kullanici_Adi'], 
                                yeni_kurum, yeni_24, yeni_22, yeni_egilim, 
                                yeni_temas, yeni_rakip, yeni_ulasim, yeni_cizik
                            ])
                        
                        st.success("✅ Veri ve Log Kaydedildi!")
                    except Exception as e:
                        st.error(f"Hata: {e}")

        # --- SAĞ TARAF: GEÇMİŞ (LOGLAR) ---
        with col_hist:
            st.info("🕒 Hareket Dökümü")
            if not df_log.empty:
                kisi_loglari = df_log[df_log['Sicil_No'].astype(str) == str(sicil_no)]
                if not kisi_loglari.empty:
                    for i, row in kisi_loglari.iloc[::-1].iterrows():
                        st.markdown(f"**{row['Kullanici']}** - {row['Zaman']}")
                        # Egilim sütunu var mı kontrol et
                        egilim_txt = row['Egilim'] if 'Egilim' in row else '-'
                        st.caption(f"Durum: {egilim_txt}")
                        
                        # Notlar var mı kontrol et
                        not_txt = row['Notlar'] if 'Notlar' in row else ''
                        if str(not_txt).strip():
                            st.text(f"Not: {not_txt}")
                        st.divider()
                else:
                    st.write("Geçmiş kaydı yok.")
            else:
                st.write("Log sayfası boş.")
