import streamlit as st
import pandas as pd
import gspread
import plotly.express as px
import plotly.graph_objects as go
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import time
import math
import random

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
        ws = sheet.worksheet("secmenler")
        data = ws.get_all_records()
        df = pd.DataFrame(data)
        df.columns = df.columns.str.strip()
        df = df.astype(str)
        
        required_cols = ['Referans', 'Sandik_No', 'Egilim', 'Kurum', 'Ad_Soyad', 'Sicil_No', 'Temas_Durumu', 'Ulasim', 'Cizikler', 'Rakip_Ekleme', 'Gecmis_2024', 'Gecmis_2022', 'Telefon']
        for col in required_cols:
            if col not in df.columns:
                df[col] = ""

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

# --- 4. POP-UP FORM (HAFIZA SİSTEMİ EKLENDİ) ---
@st.dialog("✏️ SEÇMEN KARTI & GEÇMİŞ")
def entry_form_dialog(kisi, row_n, sicil, user, df_cols, ws, ws_log, df_log):
    st.markdown(f"### 👤 {kisi['Ad_Soyad']}")
    st.caption(f"Sandık: {kisi.get('Sandik_No', '-')} | Sicil: {sicil}")
    
    is_admin = (user['Rol'] == 'ADMIN')
    def get(f): return kisi.get(f, "") if is_admin else ""

    # --- GEÇMİŞ HAREKETLER TABLOSU (YENİ ÖZELLİK) ---
    st.info("🕒 **Seçmen Hafızası (Kim Ne Demiş?):**")
    if not df_log.empty:
        # Sadece bu kişiye ait logları çek
        kisi_loglari = df_log[df_log['Sicil_No'].astype(str) == str(sicil)]
        
        if not kisi_loglari.empty:
            # Okunabilir sade bir tablo yap
            gosterilecek_log = kisi_loglari[['Zaman', 'Kullanici', 'Egilim', 'Cizikler']].copy()
            gosterilecek_log.columns = ['Tarih', 'Görüşen', 'Tespit', 'Notlar']
            # En yeniden en eskiye sırala
            gosterilecek_log = gosterilecek_log.sort_values(by='Tarih', ascending=False)
            st.dataframe(gosterilecek_log, use_container_width=True, hide_index=True)
        else:
            st.caption("Bu kişiyle ilgili henüz geçmiş kayıt yok.")
    else:
        st.caption("Log kaydı bulunamadı.")

    st.divider()
    st.markdown("#### 📝 Yeni Veri Girişi")

    with st.form("popup_form"):
        c1, c2 = st.columns(2)
        with c1:
            opts_kurum = ["", "Özel Sektör", "Dsi", "Karayolları", "Büyükşehir", "Vaski", "Projeci", "Yapı Denetimci", "İlçe Belediyeleri", "Müteahhit", "Yapsat", "Çevre Şehircilik", "Emekli", "Diğer"]
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

        if st.form_submit_button("✅ GÜNCELLE VE KAYDET"):
            try:
                updates = [
                    ("Kurum", n_kurum), ("Gecmis_2024", n_24), ("Gecmis_2022", n_22),
                    ("Egilim", n_egilim), ("Temas_Durumu", n_temas), ("Ulasim", n_ulasim),
                    ("Cizikler", n_not), ("Rakip_Ekleme", n_rakip), ("Referans", n_ref),
                    ("Son_Guncelleyen", user['Kullanici_Adi'])
                ]
                # Excel Update
                for col, val in updates:
                    if col in df_cols:
                        ws.update_cell(row_n, df_cols.index(col)+1, val)
                
                # Log Update
                if ws_log:
                    now = datetime.now().strftime("%Y-%m-%d %H:%M")
                    log_data = [now, str(sicil), kisi['Ad_Soyad'], user['Kullanici_Adi'], n_kurum, n_egilim, n_24, n_22, n_temas, n_rakip, n_ulasim, n_not]
                    ws_log.append_row(log_data)
                
                st.success("✅ Veri Kaydedildi!")
                time.sleep(1)
                st.rerun() 
                
            except Exception as e:
                st.error(f"Hata: {e}")

# --- 5. ANA EKRAN ---
user = st.session_state.user
gun = get_countdown()
st.sidebar.markdown(f"<div style='background-color:#d32f2f;padding:10px;border-radius:5px;text-align:center;color:white;'><h3>⏳ {gun} GÜN</h3></div>", unsafe_allow_html=True)
st.sidebar.markdown(f"### 👤 {user['Kullanici_Adi']}")

if st.sidebar.button("Çıkış Yap"):
    st.session_state.user = None
    st.rerun()

df, ws, df_log, ws_log = get_data()

if df is None:
    st.error("Veri alınırken hata oluştu.")
    st.stop()

if user['Rol'] == 'ADMIN':
    menu = st.sidebar.radio("Menü", ["📊 ANALİZ RAPORU", "📝 Veri Girişi"])
else:
    menu = st.sidebar.radio("Menü", ["📝 Veri Girişi"])

# =========================================================
# ANALİZ
# =========================================================
if menu == "📊 ANALİZ RAPORU" and user['Rol'] == 'ADMIN':
    st.title("📊 Seçim Komuta Masası")
    
    temas = df[df['Egilim'].str.len() > 1]
    bizimkiler = temas[temas['Egilim'].isin(["Tüm Listemizi Yazar", "Büyük Kısmı Yazar"])]
    kararsizlar = temas[temas['Egilim'].isin(["Kararsızım", "Kısmen Yazar"])]
    hedef_oy = int(len(df) / 2) + 1
    bizim_sayi = len(bizimkiler)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Toplam Oda Üyesi", len(df))
    c2.metric("Sahada Dokunulan", len(temas), f"%{int(len(temas)/len(df)*100) if len(df) else 0}")
    c3.metric("🟡 BİZİM OYLAR", bizim_sayi, f"Hedefin %{int(bizim_sayi/hedef_oy*100) if hedef_oy else 0}'i")
    c4.metric("Kazanmak İçin Gereken", hedef_oy - bizim_sayi, delta_color="inverse")
    
    st.divider()

    tabs = st.tabs(["🤖 YAPAY ZEKA", "🌍 GENEL", "🗳️ SANDIKLAR", "🏢 KURUMLAR", "🎯 FIRSAT", "⚡ EKİP"])

    # 1. YAPAY ZEKA
    with tabs[0]:
        st.subheader("🤖 YZ Seçim Simülasyonu")
        st.info("Bu modül, sahadaki kararsızların %60'ının lehimize döneceğini öngörerek hesaplama yapar.")
        
        potansiyel_kazanim = int(len(kararsizlar) * 0.6) 
        tahmini_toplam = bizim_sayi + potansiyel_kazanim
        kazanma_ihtimali = min(int((tahmini_toplam / hedef_oy) * 100), 99) if hedef_oy > 0 else 0
        
        col_ai1, col_ai2 = st.columns([1, 2])
        
        with col_ai1:
            st.markdown(f"""
            ### 🔮 Tahmini Sonuç
            # %{int(tahmini_toplam / len(df) * 100) if len(df) > 0 else 0}
            **Oy Oranı**
            """)
            if tahmini_toplam > hedef_oy:
                st.success("✅ YZ Analizi: KAZANIYORUZ!")
            else:
                st.warning("⚠️ YZ Analizi: HENÜZ KRİTİK EŞİKTEYİZ.")
                
        with col_ai2:
            fig_gauge = go.Figure(go.Indicator(
                mode = "gauge+number",
                value = kazanma_ihtimali,
                title = {'text': "Kazanma İhtimali (%)"},
                gauge = {
                    'axis': {'range': [0, 100]},
                    'bar': {'color': "darkblue"},
                    'steps': [
                        {'range': [0, 50], 'color': "lightgray"},
                        {'range': [50, 100], 'color': "lightgreen"}],
                    'threshold': {
                        'line': {'color': "red", 'width': 4},
                        'thickness': 0.75,
                        'value': 50}}))
            st.plotly_chart(fig_gauge, use_container_width=True)

    with tabs[1]:
        c1, c2 = st.columns(2)
        with c1:
            temp_df = df.copy()
            temp_df.loc[temp_df['Egilim'] == "", 'Egilim'] = "Henüz Görüşülmedi"
            fig_genel = px.pie(temp_df, names='Egilim', title='Tüm Odanın Genel Dağılımı', hole=0.4)
            st.plotly_chart(fig_genel, use_container_width=True)
        with c2:
            if not temas.empty:
                fig_temas = px.pie(temas, names='Egilim', title='Sadece Ulaşılanların Dağılımı', hole=0.4)
                st.plotly_chart(fig_temas, use_container_width=True)

    with tabs[2]:
        sandik_ozet = temas.groupby(['Sandik_No', 'Egilim']).size().reset_index(name='Kişi')
        if not sandik_ozet.empty:
            fig_sandik = px.bar(sandik_ozet, x="Sandik_No", y="Kişi", color="Egilim", title="Sandık Analizi")
            st.plotly_chart(fig_sandik, use_container_width=True)
            st.dataframe(pd.crosstab(temas['Sandik_No'], temas['Egilim']), use_container_width=True)

    with tabs[3]:
        k_genel = df['Kurum'].value_counts().reset_index()
        k_genel.columns = ['Kurum', 'Top']
        k_bizim = bizimkiler['Kurum'].value_counts().reset_index()
        k_bizim.columns = ['Kurum', 'Biz']
        m = pd.merge(k_genel, k_bizim, on='Kurum', how='left').fillna(0)
        m = m[m['Top'] > 0]
        m['Oran'] = (m['Biz'] / m['Top'] * 100).astype(int)
        m = m.sort_values(by='Oran', ascending=False)
        fig_ku = px.bar(m, x='Kurum', y='Oran', text='Biz', color='Oran', title="Kurum Başarısı (%)")
        st.plotly_chart(fig_ku, use_container_width=True)

    with tabs[4]:
        if not kararsizlar.empty:
            h_list = kararsizlar[['Sicil_No', 'Ad_Soyad', 'Sandik_No', 'Kurum', 'Referans']].copy()
            st.dataframe(h_list, use_container_width=True)
            st.download_button("📥 İndir", h_list.to_csv().encode('utf-8'), 'hedef.csv')
        else:
            st.success("Kararsız yok.")

    with tabs[5]:
        if not df_log.empty:
            perf = df_log['Kullanici'].value_counts().reset_index()
            perf.columns = ['İsim', 'İşlem']
            st.bar_chart(perf.set_index('İsim'))
            st.dataframe(df_log.tail(10), use_container_width=True)

# =========================================================
# VERİ GİRİŞİ
# =========================================================
elif menu == "📝 Veri Girişi":
    st.header("📋 Seçmen Bilgi Girişi")
    
    is_admin = (user['Rol'] == 'ADMIN')
    if is_admin: st.success("YETKİLİ MODU")
    else: st.info("SAHA MODU")

    # Arama
    if 'search_term' not in st.session_state: st.session_state.search_term = ""
    def update_search(): st.session_state.search_term = st.session_state.widget_search
    search = st.text_input("🔍 İsim Ara (Liste aşağıdadır)", value=st.session_state.search_term, key="widget_search", on_change=update_search)
    
    cols = ['Sicil_No', 'Ad_Soyad', 'Sandik_No', 'Kurum', 'Egilim', 'Son_Guncelleyen'] if is_admin else ['Sicil_No', 'Ad_Soyad', 'Sandik_No', 'Kurum']
    
    if search:
        df_show = df[df['Ad_Soyad'].str.contains(search, case=False, na=False)]
        st.caption(f"🔍 '{search}' araması için {len(df_show)} sonuç.")
    else:
        page_size = 20
        total_pages = math.ceil(len(df) / page_size)
        if 'page_number' not in st.session_state: st.session_state.page_number = 1
            
        c_prev, c_page, c_next = st.columns([1, 2, 1])
        with c_prev:
            if st.button("⬅️ Önceki") and st.session_state.page_number > 1: st.session_state.page_number -= 1
        with c_next:
            if st.button("Sonraki ➡️") and st.session_state.page_number < total_pages: st.session_state.page_number += 1
        with c_page:
            st.markdown(f"**Sayfa {st.session_state.page_number} / {total_pages}**")

        start_idx = (st.session_state.page_number - 1) * page_size
        end_idx = start_idx + page_size
        df_show = df.iloc[start_idx:end_idx]

    event = st.dataframe(df_show[cols], use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row")

    if len(event.selection.rows) > 0:
        idx = event.selection.rows[0]
        sicil = df_show.iloc[idx]['Sicil_No']
        g_idx = df[df['Sicil_No'] == sicil].index[0]
        row_n = g_idx + 2
        kisi = df.iloc[g_idx]
        
        # POP-UP'A LOG DATAFRAME'İNİ DE GÖNDERİYORUZ
        entry_form_dialog(kisi, row_n, sicil, user, df.columns.tolist(), ws, ws_log, df_log)
