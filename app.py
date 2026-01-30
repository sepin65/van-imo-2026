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
@st.cache_resource(ttl=600)
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
        ws = sheet.worksheet("secmenler")
        all_data = ws.get_all_values()
        
        if len(all_data) > 1:
            headers = [h.strip() for h in all_data[0]]
            rows = all_data[1:]
            cleaned_headers = [h if h != "" else f"Bos_Sutun_{i}" for i, h in enumerate(headers)]
            df = pd.DataFrame(rows, columns=cleaned_headers)
        else:
            return pd.DataFrame(), None, pd.DataFrame(), None

        rename_map = {
            'Üniversite': 'Universite',
            'Doğum_Tarihi': 'Dogum_Yili',
            'Eğilim': 'Egilim',
            'Ulaşım': 'Ulasim',
            'Temsilcilik': 'Temsilcilik',
            'Tanıyanlar': 'Taniyanlar'
        }
        df.rename(columns=rename_map, inplace=True)

        required_cols = ['Referans', 'Sandik_No', 'Egilim', 'Kurum', 'Ad_Soyad', 'Sicil_No', 'Temas_Durumu', 'Ulasim', 'Cizikler', 'Rakip_Ekleme', 'Gecmis_2024', 'Gecmis_2022', 'Telefon', 'Universite', 'Dogum_Yili', 'Temsilcilik', 'Taniyanlar']
        for col in required_cols:
            if col not in df.columns: df[col] = ""

        # --- VERİ TEMİZLİĞİ ---
        def fix_location(x):
            x = str(x).strip().upper()
            if x in ["-", "", "NONE", "NAN"] or len(x) < 3: return "VAN MERKEZ"
            return x
        df['Temsilcilik'] = df['Temsilcilik'].apply(fix_location)
        df['Universite'] = df['Universite'].str.upper().str.strip()

        current_year = datetime.now().year
        def calculate_age_robust(date_str):
            date_str = str(date_str).strip()
            if not date_str or date_str in ["-", "nan", "None"]: return 0
            try:
                if "/" in date_str: dt = pd.to_datetime(date_str, dayfirst=True, errors='coerce')
                elif "." in date_str: dt = pd.to_datetime(date_str, format="%d.%m.%Y", errors='coerce')
                elif len(date_str) == 4 and date_str.isdigit(): return current_year - int(date_str)
                else: return 0
                if pd.notnull(dt): return current_year - dt.year
                return 0
            except: return 0
        df['Yas'] = df['Dogum_Yili'].apply(calculate_age_robust)

        df['Taninma_Durumu'] = df['Taniyanlar'].apply(lambda x: "Referanslı ✅" if len(str(x)) > 2 else "Kör Nokta (Tanınmıyor) ❌")
        
        # Temas Analizi (Çalışılmış mı?)
        df['Calisma_Durumu'] = df['Temas_Durumu'].apply(lambda x: "Görüşüldü 👍" if len(str(x)) > 2 else "Bekliyor ⏳")

        def clean_sicil(x):
            try: return int(str(x).replace(".", "").replace(" ", ""))
            except: return 999999 
        df['Sicil_Int'] = df['Sicil_No'].apply(clean_sicil)
        df = df.sort_values(by='Sicil_Int')
        
        try:
            df['Sandik_No'] = pd.qcut(df['Sicil_Int'].rank(method='first'), q=6, labels=[
                "1. Sandık (En Kıdemliler)", "2. Sandık", "3. Sandık", 
                "4. Sandık", "5. Sandık", "6. Sandık (En Gençler)"
            ])
        except: df['Sandik_No'] = "Belirsiz"

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

        # Referans Listesini Çıkar
        all_refs = []
        if 'Taniyanlar' in df.columns:
            raw_refs = df['Taniyanlar'].dropna().astype(str).tolist()
            for r in raw_refs:
                parts = [x.strip() for x in r.split(',')]
                all_refs.extend([x for x in parts if len(x) > 1])
        unique_refs = sorted(list(set(all_refs)))

        return df, ws, df_log, ws_log, unique_refs

    except Exception as e:
        return pd.DataFrame(), None, pd.DataFrame(), None, []

# --- GİRİŞ EKRANI ---
if 'user' not in st.session_state: st.session_state.user = None
if st.session_state.user is None:
    st.title("🏗️ İMO SEÇİM SİSTEMİ")
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

# --- FORM ---
@st.dialog("✏️ SEÇMEN KARTI")
def entry_form_dialog(kisi, row_n, sicil, user, df_cols, ws, ws_log, df_log, unique_refs):
    st.markdown(f"### 👤 {kisi['Ad_Soyad']}")
    
    yas = kisi.get('Yas', 0)
    uni = kisi.get('Universite', '')
    temsil = kisi.get('Temsilcilik', 'VAN MERKEZ')
    mevcut_taniyanlar_str = str(kisi.get('Taniyanlar', ''))
    mevcut_taniyanlar_list = [x.strip() for x in mevcut_taniyanlar_str.split(',') if len(x.strip()) > 1]
    
    c1, c2, c3 = st.columns(3)
    c1.info(f"📍 **{temsil}**")
    c2.info(f"🎓 **{uni if len(uni)>2 else '-'}**")
    c3.info(f"🎂 **{int(yas) if yas > 0 else '?'} Yaş**")
    
    if len(mevcut_taniyanlar_list) > 0:
        st.success(f"🔗 **Tanıyanlar:** {', '.join(mevcut_taniyanlar_list)}")
    else:
        st.error("⚠️ Tanıyan Kimse Yok (Kör Nokta)")

    with st.form("form"):
        # --- REFERANS EKLEME (AKILLI KUTU) ---
        st.markdown("#### 🤝 Referans Ekle / Düzenle")
        yeni_taniyanlar = st.multiselect(
            "Listeden Seç veya Yazıp Enter'a Bas:", 
            options=unique_refs, 
            default=[x for x in mevcut_taniyanlar_list if x in unique_refs] + [x for x in mevcut_taniyanlar_list if x not in unique_refs]
        )
        
        st.divider()
        c1, c2 = st.columns(2)
        with c1:
            k_opt = ["", "Özel Sektör", "Dsi", "Karayolları", "Büyükşehir", "Vaski", "Projeci", "Yapı Denetimci", "İlçe Belediyeleri", "Müteahhit", "Yapsat", "Çevre Şehircilik", "Emekli", "Diğer"]
            nk = st.selectbox("Kurum", k_opt, index=k_opt.index(kisi.get('Kurum',"")) if kisi.get('Kurum',"") in k_opt else 0)
            n24 = st.selectbox("2024", ["", "Sarı Liste", "Mavi Liste"], index=["", "Sarı Liste", "Mavi Liste"].index(kisi.get('Gecmis_2024','')) if kisi.get('Gecmis_2024','') in ["", "Sarı Liste", "Mavi Liste"] else 0)
        with c2:
            e_opt = ["", "Tüm Listemizi Yazar", "Büyük Kısmı Yazar", "Kısmen Yazar", "Karşı Tarafı Destekler", "Kararsızım"]
            ne = st.selectbox("2026 EĞİLİMİ", e_opt, index=e_opt.index(kisi.get('Egilim','')) if kisi.get('Egilim','') in e_opt else 0)
            nt = st.selectbox("Temas", ["", "Kendim Görüştüm", "Arkadaşım/Akraba Aracılığı", "Tanımıyorum"], index=["", "Kendim Görüştüm", "Arkadaşım/Akraba Aracılığı", "Tanımıyorum"].index(kisi.get('Temas_Durumu','')) if kisi.get('Temas_Durumu','') in ["", "Kendim Görüştüm", "Arkadaşım/Akraba Aracılığı", "Tanımıyorum"] else 0)

        nn = st.text_area("Notlar", value=kisi.get('Cizikler',''))
        
        if st.form_submit_button("✅ KAYDET"):
            taniyanlar_str = ", ".join(yeni_taniyanlar)
            updates = [
                ("Kurum", nk), ("Gecmis_2024", n24),
                ("Egilim", ne), ("Temas_Durumu", nt),
                ("Cizikler", nn), ("Tanıyanlar", taniyanlar_str),
                ("Son_Guncelleyen", user['Kullanici_Adi'])
            ]
            
            for col, val in updates:
                target = col
                if col == 'Tanıyanlar' and 'Taniyanlar' in df_cols: target = 'Taniyanlar'
                if col in df_cols: ws.update_cell(row_n, df_cols.index(col)+1, val)
                elif target in df_cols: ws.update_cell(row_n, df_cols.index(target)+1, val)
            
            if ws_log:
                ws_log.append_row([datetime.now().strftime("%Y-%m-%d %H:%M"), str(sicil), kisi['Ad_Soyad'], user['Kullanici_Adi'], nk, ne, n24, "", nt, "", "", nn, taniyanlar_str])
            st.toast("Kaydedildi!", icon="💾")
            time.sleep(1)
            st.rerun()

# --- ANA EKRAN ---
user = st.session_state.user
df, ws, df_log, ws_log, unique_refs = get_data()
if df.empty:
    st.warning("Veriler yükleniyor...")
    st.stop()

if user['Rol'] == 'ADMIN':
    menu_list = ["📊 GENEL ANALİZ", "🤝 REFERANS YÖNETİMİ", "📉 'KÖR NOKTA' ANALİZİ", "🕸️ AĞ İSTİHBARATI", "🎓 DEMOGRAFİK İSTİHBARAT", "📝 Veri Girişi"]
else:
    menu_list = ["🤝 REFERANS YÖNETİMİ", "📝 Veri Girişi"]

menu = st.sidebar.radio("Menü", menu_list)

# =========================================================
# 🤝 REFERANS YÖNETİMİ (ÇİFT MODÜL)
# =========================================================
if menu == "🤝 REFERANS YÖNETİMİ":
    st.title("🤝 Referans Yönetim & Denetim Merkezi")
    
    tab1, tab2 = st.tabs(["🕵️‍♀️ REFERANS ATAMA (KÖR NOKTALAR)", "📋 GÖREV & HESAP SORMA LİSTESİ"])

    # --- TAB 1: KİM KİMİ TANIYOR? (ATAMA) ---
    with tab1:
        st.subheader("🕵️‍♀️ Sahipsiz Üyelere Referans Ekle")
        st.caption("Aşağıdaki listede henüz kimsenin 'Ben tanıyorum' demediği üyeler var. Tanıyanları seçip ekleyin.")
        
        # Filtreler
        c_f1, c_f2 = st.columns([3, 1])
        search_atama = c_f1.text_input("🔍 İsim Ara (Atama)", placeholder="Kör noktalarda ara...")
        region_filter = c_f2.selectbox("Bölge Filtre:", ["HEPSİ"] + sorted(df['Temsilcilik'].unique().tolist()), key="reg_atama")

        # Sadece Kör Noktalar
        df_atama = df[df['Taninma_Durumu'] == "Kör Nokta (Tanınmıyor) ❌"]
        
        if region_filter != "HEPSİ":
            df_atama = df_atama[df_atama['Temsilcilik'] == region_filter]
        
        if search_atama:
            df_atama = df_atama[df_atama['Ad_Soyad'].str.contains(search_atama, case=False, na=False)]

        st.info(f"📌 Atanmayı bekleyen **{len(df_atama)}** kişi var.")
        
        # Tablo
        cols_atama = ['Sicil_No', 'Ad_Soyad', 'Universite', 'Temsilcilik', 'Taninma_Durumu']
        
        event = st.dataframe(
            df_atama[cols_atama], 
            use_container_width=True, hide_index=True, 
            on_select="rerun", selection_mode="single-row", height=500
        )
        
        if len(event.selection.rows) > 0:
            idx = event.selection.rows[0]
            sicil = df_atama.iloc[idx]['Sicil_No']
            g_idx = df[df['Sicil_No'] == sicil].index[0]
            entry_form_dialog(df.iloc[g_idx], g_idx + 2, sicil, user, df.columns.tolist(), ws, ws_log, df_log, unique_refs)

    # --- TAB 2: GÖREV LİSTESİ (HESAP SORMA) ---
    with tab2:
        st.subheader("📋 Kişiye Özel Görev Listesi (Denetim)")
        st.caption("Bir referans seçin ve 'Tanıyorum' dediği kişilerle görüşüp görüşmediğini kontrol edin.")
        
        # Referans Seçimi
        target_ref = st.selectbox("👉 Hangi Referansın Listesi Gelsin?", ["Seçiniz..."] + unique_refs)
        
        if target_ref != "Seçiniz...":
            # Seçilen kişinin tanıdıklarını filtrele
            df_gorev = df[df['Taniyanlar'].str.contains(target_ref, case=False, na=False)]
            
            # İstatistikler
            total_gorev = len(df_gorev)
            done_gorev = len(df_gorev[df_gorev['Calisma_Durumu'] == "Görüşüldü 👍"])
            pending_gorev = total_gorev - done_gorev
            basari_orani = int((done_gorev / total_gorev) * 100) if total_gorev > 0 else 0
            
            # Kartlar
            c1, c2, c3 = st.columns(3)
            c1.metric(f"{target_ref} Listesi", total_gorev)
            c2.metric("Görüşülen", done_gorev, f"%{basari_orani} Başarı")
            c3.metric("Görüşülmeyen (Açık)", pending_gorev, delta_color="inverse")
            
            if basari_orani < 50:
                st.error(f"⚠️ **{target_ref}**, listendeki kişilerin çoğunu henüz aramamışsın!")
            else:
                st.success(f"✅ Tebrikler **{target_ref}**, iyi gidiyorsun.")
            
            st.divider()
            
            # Görüşülmeyenleri öne çıkar
            df_gorev_sorted = df_gorev.sort_values('Calisma_Durumu', ascending=True) # Bekleyenler üstte
            
            cols_gorev = ['Sicil_No', 'Ad_Soyad', 'Telefon', 'Calisma_Durumu', 'Egilim', 'Kurum']
            
            # Renkli Tablo (Style)
            def color_status(val):
                color = '#ffcdd2' if val == "Bekliyor ⏳" else '#c8e6c9'
                return f'background-color: {color}'

            st.dataframe(
                df_gorev_sorted[cols_gorev].style.map(color_status, subset=['Calisma_Durumu']),
                use_container_width=True,
                height=600,
                hide_index=True
            )
            
            # Tıklayınca yine kart açılsın (Sonuç girmek için)
            # Not: Styled dataframe'de on_select çalışmaz, bu yüzden ham dataframe ile seçim yapıyoruz
            st.caption("👇 Sonuç girmek için aşağıdaki listeden seçiniz:")
            event_gorev = st.dataframe(df_gorev_sorted[cols_gorev], use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row")
            
            if len(event_gorev.selection.rows) > 0:
                idx = event_gorev.selection.rows[0]
                sicil = df_gorev_sorted.iloc[idx]['Sicil_No']
                g_idx = df[df['Sicil_No'] == sicil].index[0]
                entry_form_dialog(df.iloc[g_idx], g_idx + 2, sicil, user, df.columns.tolist(), ws, ws_log, df_log, unique_refs)

# =========================================================
# DİĞER MODÜLLER (KISALTILDI)
# =========================================================
# (Aşağısı diğer modüllerdir, V36 ile aynıdır)
elif menu == "📉 'KÖR NOKTA' ANALİZİ" and user['Rol'] == 'ADMIN':
    st.title("📉 'Kör Nokta' Analizi")
    # ... (V36 Kodu Buraya Gelecek - Yer kazanmak için eklemedim, önceki kodun aynısı)
    # Eğer istersen tam kodu tek parça da verebilirim.
