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

# --- 2. VERİLERİ ÇEK (OTO-TAMİR MODÜLÜ) ---
def get_data():
    client = get_connection()
    try:
        sheet = client.open("Van_IMO_Secim_2026")
        
        # --- ANA LİSTE ---
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

        # --- LOG KAYITLARI (OTO-TAMİR) ---
        try:
            ws_log = sheet.worksheet("log_kayitlari")
        except:
            ws_log = sheet.add_worksheet(title="log_kayitlari", rows="1000", cols="20")
        
        all_values = ws_log.get_all_values()
        correct_headers = ['Zaman', 'Sicil_No', 'Ad_Soyad', 'Kullanici', 'Kurum', 'Egilim', 'Gecmis_2024', 'Gecmis_2022', 'Temas_Durumu', 'Rakip_Ekleme', 'Ulasim', 'Cizikler']
        
        needs_repair = False
        if not all_values: 
            needs_repair = True
        else:
            current_headers = all_values[0]
            if len(current_headers) != len(correct_headers) or current_headers.count('Egilim') > 1:
                if len(all_values) < 5: 
                    needs_repair = True
        
        if needs_repair:
            ws_log.clear()
            ws_log.append_row(correct_headers)
            df_log = pd.DataFrame(columns=correct_headers)
        else:
            df_log = pd.DataFrame(all_values[1:], columns=all_values[0])

        if not df_log.empty and 'Sicil_No' in df_log.columns:
            df_log['Sicil_No'] = df_log['Sicil_No'].astype(str)

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

# --- 4. POP-UP FORM ---
@st.dialog("✏️ SEÇMEN KARTI & GEÇMİŞ")
def entry_form_dialog(kisi, row_n, sicil, user, df_cols, ws, ws_log, df_log):
    st.markdown(f"### 👤 {kisi['Ad_Soyad']}")
    st.caption(f"Sandık: {kisi.get('Sandik_No', '-')} | Sicil: {sicil}")
    
    is_admin = (user['Rol'] == 'ADMIN')
    def get(f): return kisi.get(f, "") if is_admin else ""

    # --- GEÇMİŞ TABLOSU ---
    st.info("🕒 **Seçmen Hafızası (Kim Ne Demiş?):**")
    
    log_found = False
    if df_log is not None and not df_log.empty and 'Sicil_No' in df_log.columns:
        sicil_str = str(sicil).strip()
        kisi_loglari = df_log[df_log['Sicil_No'].astype(str).str.strip() == sicil_str]
        
        if not kisi_loglari.empty:
            log_found = True
            try:
                gosterilecek = kisi_loglari[['Zaman', 'Kullanici', 'Egilim', 'Cizikler']].copy()
                gosterilecek.columns = ['Tarih', 'Görüşen', 'Durum', 'Not']
                gosterilecek = gosterilecek.sort_values(by='Tarih', ascending=False)
                st.dataframe(gosterilecek, use_container_width=True, hide_index=True)
            except:
                pass
            
    if not log_found:
        st.caption("📭 Bu kişiyle ilgili henüz geçmiş kayıt bulunamadı.")

    st.divider()
    
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
                for col, val in updates:
                    if col in df_cols:
                        ws.update_cell(row_n, df_cols.index(col)+1, val)
                
                if ws_log:
                    now = datetime.now().strftime("%Y-%m-%d %H:%M")
                    log_data = [now, str(sicil), kisi['Ad_Soyad'], user['Kullanici_Adi'], n_kurum, n_egilim, n_24, n_22, n_temas, n_rakip, n_ulasim, n_not]
                    ws_log.append_row(log_data)
                
                st.toast("✅ Veri ve Log Kaydedildi!", icon="💾")
                # YENİLEME YOK (Sayfa zıplamasını önlemek için)
                
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
    c1.metric("Toplam Oda Üyesi", len(df), "Hedef Kitle")
    c2.metric("Sahada Dokunulan", len(temas), f"%{int(len(temas)/len(df)*100) if len(df) else 0}")
    c3.metric("🟡 BİZİM OYLAR", bizim_sayi, f"Hedefin %{int(bizim_sayi/hedef_oy*100) if hedef_oy else 0}'i")
    c4.metric("Kazanmak İçin Gereken", hedef_oy - bizim_sayi, delta_color="inverse")
    
    st.divider()

    tabs = st.tabs(["🤖 YAPAY ZEKA", "🌍 GENEL", "🗳️ SANDIKLAR", "🏢 KURUMLAR", "🎯 FIRSAT", "⚡ EKİP"])

    with tabs[0]:
        st.subheader("🤖 YZ Seçim Simülasyonu")
        st.info("Bu modül, sahadaki kararsızların %60'ının lehimize döneceğini öngörerek hesaplama yapar.")
        potansiyel = int(len(kararsizlar) * 0.6)
        tahmin = bizim_sayi + potansiyel
        olasilik = min(int((tahmin / hedef_oy) * 100), 99) if hedef_oy > 0 else 0
        
        c_ai1, c_ai2 = st.columns([1, 2])
        with c_ai1:
            st.metric("Tahmini Oy", tahmin, f"%{int(tahmin/len(df)*100)} Oran")
            if tahmin > hedef_oy: st.success("KAZANIYORUZ! 🚀")
            else: st.warning("ÇALIŞMAYA DEVAM ⚠️")
        with c_ai2:
            fig = go.Figure(go.Indicator(mode="gauge+number", value=olasilik, title={'text': "Kazanma İhtimali"}, gauge={'axis': {'range': [0, 100]}, 'bar': {'color': "darkblue"}}))
            st.plotly_chart(fig, use_container_width=True)

    with tabs[1]:
        c1, c2 = st.columns(2)
        with c1:
            tdf = df.copy()
            tdf.loc[tdf['Egilim'] == "", 'Egilim'] = "Görüşülmedi"
            st.plotly_chart(px.pie(tdf, names='Egilim', title='Genel Durum'), use_container_width=True)
        with c2:
            if not temas.empty: st.plotly_chart(px.pie(temas, names='Egilim', title='Saha Durumu'), use_container_width=True)

    with tabs[2]:
        so = temas.groupby(['Sandik_No', 'Egilim']).size().reset_index(name='Kişi')
        if not so.empty: st.plotly_chart(px.bar(so, x="Sandik_No", y="Kişi", color="Egilim"), use_container_width=True)

    with tabs[3]:
        kg = df['Kurum'].value_counts().reset_index()
        kg.columns = ['Kurum', 'Top']
        kb = bizimkiler['Kurum'].value_counts().reset_index()
        kb.columns = ['Kurum', 'Biz']
        m = pd.merge(kg, kb, on='Kurum', how='left').fillna(0)
        m = m[m['Top'] > 0]
        m['Oran'] = (m['Biz'] / m['Top'] * 100).astype(int)
        st.plotly_chart(px.bar(m.sort_values('Oran', ascending=False), x='Kurum', y='Oran', text='Biz'), use_container_width=True)

    with tabs[4]:
        if not kararsizlar.empty:
            h = kararsizlar[['Sicil_No', 'Ad_Soyad', 'Sandik_No', 'Kurum', 'Referans']].copy()
            st.dataframe(h, use_container_width=True)
            st.download_button("İndir", h.to_csv().encode('utf-8'), 'hedef.csv')
        else: st.success("Liste Temiz")

    with tabs[5]:
        if not df_log.empty:
            perf = df_log['Kullanici'].value_counts().reset_index()
            perf.columns = ['İsim', 'İşlem']
            st.bar_chart(perf.set_index('İsim'))
            st.dataframe(df_log.tail(10), use_container_width=True)

# =========================================================
# VERİ GİRİŞİ (SAYFA NUMARASI GİRME ÖZELLİKLİ)
# =========================================================
elif menu == "📝 Veri Girişi":
    st.header("📋 Seçmen Bilgi Girişi")
    
    is_admin = (user['Rol'] == 'ADMIN')
    if is_admin: st.success("YETKİLİ MODU")
    else: st.info("SAHA MODU")

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
        
        # --- GELİŞMİŞ NAVİGASYON ---
        c1, c2, c3 = st.columns([1, 2, 1])
        with c1: 
            if st.button("⬅️ Önceki") and st.session_state.page_number > 1: st.session_state.page_number -= 1
        with c3:
            if st.button("Sonraki ➡️") and st.session_state.page_number < total_pages: st.session_state.page_number += 1
        with c2:
            # Buraya Text Input yerine Number Input koyduk, Enter'a basınca gider
            target_page = st.number_input("Sayfa No Gir (Enter'a bas)", min_value=1, max_value=total_pages, value=st.session_state.page_number)
            if target_page != st.session_state.page_number:
                st.session_state.page_number = target_page
                st.rerun()
        
        start = (st.session_state.page_number - 1) * page_size
        df_show = df.iloc[start:start+page_size]

    event = st.dataframe(df_show[cols], use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row")

    if len(event.selection.rows) > 0:
        idx = event.selection.rows[0]
        sicil = df_show.iloc[idx]['Sicil_No']
        g_idx = df[df['Sicil_No'] == sicil].index[0]
        entry_form_dialog(df.iloc[g_idx], g_idx + 2, sicil, user, df.columns.tolist(), ws, ws_log, df_log)
