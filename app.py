import streamlit as st
import pandas as pd
import gspread
import plotly.express as px
import plotly.graph_objects as go
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import time
import math
import itertools
from fpdf import FPDF # PDF Kütüphanesi

# =============================================================================
# 1. TEMEL AYARLAR VE BAĞLANTILAR
# =============================================================================
st.set_page_config(
    page_title="İMO Van 2026 - Karargah", 
    layout="wide", 
    page_icon="🏗️",
    initial_sidebar_state="expanded"
)

@st.cache_resource(ttl=600)
def get_connection():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    return client

# =============================================================================
# 2. VERİ ÇEKME VE İŞLEME MOTORU (GELİŞMİŞ)
# =============================================================================
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
            return pd.DataFrame(), None, pd.DataFrame(), None, []

        # Sütun Eşleştirme (Hata payını sıfıra indirmek için)
        rename_map = {
            'Üniversite': 'Universite',
            'Doğum_Tarihi': 'Dogum_Yili', 'Dogum_Tarihi': 'Dogum_Yili', 'Doğum Tarihi': 'Dogum_Yili',
            'Eğilim': 'Egilim',
            'Ulaşım': 'Ulasim',
            'Temsilcilik': 'Temsilcilik',
            'Tanıyanlar': 'Taniyanlar'
        }
        df.rename(columns=rename_map, inplace=True)

        required_cols = ['Referans', 'Sandik_No', 'Egilim', 'Kurum', 'Ad_Soyad', 'Sicil_No', 'Temas_Durumu', 'Ulasim', 'Cizikler', 'Rakip_Ekleme', 'Gecmis_2024', 'Gecmis_2022', 'Telefon', 'Universite', 'Dogum_Yili', 'Temsilcilik', 'Taniyanlar']
        for col in required_cols:
            if col not in df.columns: df[col] = ""

        # --- Temizlik İşlemleri ---
        def fix_location(x):
            x = str(x).strip().upper()
            if x in ["-", "", "NONE", "NAN"] or len(x) < 3: return "VAN MERKEZ"
            return x
        df['Temsilcilik'] = df['Temsilcilik'].apply(fix_location)
        df['Universite'] = df['Universite'].str.upper().str.strip()

        # Yaş Hesaplama (Tüm formatları destekler)
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

        # Yaş Grupları
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

        # Durum Analizleri
        df['Taninma_Durumu'] = df['Taniyanlar'].apply(lambda x: "Referanslı ✅" if len(str(x)) > 2 else "Kör Nokta (Tanınmıyor) ❌")
        df['Calisma_Durumu'] = df['Temas_Durumu'].apply(lambda x: "Görüşüldü 👍" if len(str(x)) > 2 else "Bekliyor ⏳")

        # Sicil Temizliği
        def clean_sicil(x):
            try: return int(str(x).replace(".", "").replace(" ", ""))
            except: return 999999 
        df['Sicil_Int'] = df['Sicil_No'].apply(clean_sicil)
        df = df.sort_values(by='Sicil_Int')
        
        # Sandık Atama
        try:
            df['Sandik_No'] = pd.qcut(df['Sicil_Int'].rank(method='first'), q=6, labels=[
                "1. Sandık (En Kıdemliler)", "2. Sandık", "3. Sandık", 
                "4. Sandık", "5. Sandık", "6. Sandık (En Gençler)"
            ])
        except: df['Sandik_No'] = "Belirsiz"

        # Log Sayfası
        try:
            ws_log = sheet.worksheet("log_kayitlari")
        except:
            ws_log = sheet.add_worksheet(title="log_kayitlari", rows="1000", cols="20")
        
        log_raw = ws_log.get_all_values()
        log_headers = ['Zaman', 'Sicil_No', 'Ad_Soyad', 'Kullanici', 'Kurum', 'Egilim', 'Gecmis_2024', 'Gecmis_2022', 'Temas_Durumu', 'Rakip_Ekleme', 'Ulasim', 'Cizikler', 'Taniyanlar']
        
        if not log_raw or (len(log_raw) > 0 and log_raw[0] != log_headers):
            if len(log_raw) < 5:
                ws_log.clear(); ws_log.append_row(log_headers)
                df_log = pd.DataFrame(columns=log_headers)
            else:
                 h = log_raw[0]
                 clean_h = [x if x.strip() != "" else f"Bos_{i}" for i, x in enumerate(h)]
                 df_log = pd.DataFrame(log_raw[1:], columns=clean_h)
        else:
            df_log = pd.DataFrame(log_raw[1:], columns=log_raw[0])

        if not df_log.empty and 'Sicil_No' in df_log.columns:
            df_log['Sicil_No'] = df_log['Sicil_No'].astype(str)

        # Referans Listesini Çıkar (Multiselect için)
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

# =============================================================================
# 3. PDF OLUŞTURMA MOTORU (EMOJİ TEMİZLEYİCİLİ)
# =============================================================================
def create_pdf(df_source, referans_adi):
    def clean_text_for_pdf(text):
        if text is None: return ""
        text = str(text)
        # Türkçe karakter düzeltme
        tr_map = {'ğ':'g', 'Ğ':'G', 'ş':'s', 'Ş':'S', 'ı':'i', 'İ':'I', 'ü':'u', 'Ü':'U', 'ö':'o', 'Ö':'O', 'ç':'c', 'Ç':'C'}
        for tr, en in tr_map.items(): text = text.replace(tr, en)
        # Emoji Temizliği (Hata vermemesi için)
        text = text.replace("⏳", "(-)")
        text = text.replace("👍", "(+)")
        text = text.replace("✅", "(OK)")
        text = text.replace("❌", "(NO)")
        return text.encode('latin-1', 'ignore').decode('latin-1')

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=10)
    
    # Başlık
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 10, txt=clean_text_for_pdf(f"GOREV LISTESI: {referans_adi}"), ln=True, align='C')
    pdf.set_font("Arial", size=10)
    pdf.cell(0, 10, txt=clean_text_for_pdf(f"Rapor Tarihi: {datetime.now().strftime('%d-%m-%Y %H:%M')}"), ln=True, align='C')
    pdf.ln(5)
    
    # Tablo
    pdf.set_font("Arial", 'B', 8)
    pdf.cell(15, 8, "Sicil", 1)
    pdf.cell(60, 8, "Ad Soyad", 1)
    pdf.cell(30, 8, "Telefon", 1)
    pdf.cell(35, 8, "Durum", 1)
    pdf.cell(40, 8, "Kurum", 1)
    pdf.ln()
    
    pdf.set_font("Arial", size=8)
    for index, row in df_source.iterrows():
        sicil = clean_text_for_pdf(row['Sicil_No'])
        ad = clean_text_for_pdf(row['Ad_Soyad'])[:30]
        tel = clean_text_for_pdf(row['Telefon'])
        durum = clean_text_for_pdf(row['Calisma_Durumu'])
        kurum = clean_text_for_pdf(row['Kurum'])[:25]
        
        pdf.cell(15, 7, sicil, 1)
        pdf.cell(60, 7, ad, 1)
        pdf.cell(30, 7, tel, 1)
        pdf.cell(35, 7, durum, 1)
        pdf.cell(40, 7, kurum, 1)
        pdf.ln()
        
    return pdf.output(dest='S').encode('latin-1', 'replace')

# =============================================================================
# 4. GİRİŞ EKRANI
# =============================================================================
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

# =============================================================================
# 5. DİALOG PENCERESİ (KART)
# =============================================================================
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

# =============================================================================
# 6. ANA UYGULAMA VE MENÜLER
# =============================================================================
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

# -----------------------------------------------------------------------------
# MENÜ 1: GENEL ANALİZ
# -----------------------------------------------------------------------------
if menu == "📊 GENEL ANALİZ" and user['Rol'] == 'ADMIN':
    st.title("📊 Genel Durum")
    temas = df[df['Egilim'].str.len() > 1]
    bizim = temas[temas['Egilim'].isin(["Tüm Listemizi Yazar", "Büyük Kısmı Yazar"])]
    
    c1, c2, c3 = st.columns(3)
    c1.metric("Toplam Üye", len(df))
    c2.metric("Ulaşılan", len(temas), f"%{int(len(temas)/len(df)*100)}")
    c3.metric("Bizimle Olan", len(bizim))
    
    tab1, tab2 = st.tabs(["SAHA DURUMU", "SANDIK BAZLI"])
    with tab1:
        if not temas.empty: st.plotly_chart(px.pie(temas, names='Egilim', title="Genel Eğilim", hole=0.4), use_container_width=True)
    with tab2:
        sandik_ozet = temas.groupby(['Sandik_No', 'Egilim']).size().reset_index(name='Kişi')
        st.plotly_chart(px.bar(sandik_ozet, x="Sandik_No", y="Kişi", color="Egilim", title="Sandık Analizi"), use_container_width=True)

# -----------------------------------------------------------------------------
# MENÜ 2: REFERANS YÖNETİMİ (PDF & ATAMA)
# -----------------------------------------------------------------------------
elif menu == "🤝 REFERANS YÖNETİMİ":
    st.title("🤝 Referans Yönetim & Denetim")
    
    tab1, tab2 = st.tabs(["🕵️‍♀️ ATAMA MERKEZİ", "📋 GÖREV & PDF"])

    # ATAMA
    with tab1:
        st.subheader("Sahipsiz Üyelere Referans Ata")
        c_f1, c_f2 = st.columns([3, 1])
        search_atama = c_f1.text_input("İsim Ara (Kör Nokta)", placeholder="Ad Soyad...")
        reg_filter = c_f2.selectbox("Bölge:", ["HEPSİ"] + sorted(df['Temsilcilik'].unique().tolist()))

        df_atama = df[df['Taninma_Durumu'] == "Kör Nokta (Tanınmıyor) ❌"]
        if reg_filter != "HEPSİ": df_atama = df_atama[df_atama['Temsilcilik'] == reg_filter]
        if search_atama: df_atama = df_atama[df_atama['Ad_Soyad'].str.contains(search_atama, case=False, na=False)]

        st.info(f"Bekleyen: **{len(df_atama)}** kişi")
        
        event = st.dataframe(df_atama[['Sicil_No', 'Ad_Soyad', 'Universite', 'Temsilcilik']], use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row", height=500)
        
        if len(event.selection.rows) > 0:
            idx = event.selection.rows[0]
            sicil = df_atama.iloc[idx]['Sicil_No']
            g_idx = df[df['Sicil_No'] == sicil].index[0]
            entry_form_dialog(df.iloc[g_idx], g_idx + 2, sicil, user, df.columns.tolist(), ws, ws_log, df_log, unique_refs)

    # GÖREV TAKİP & PDF
    with tab2:
        st.subheader("Hesap Sorma & PDF Çıktı")
        target_ref = st.selectbox("Hangi Referansın Listesi?", ["Seçiniz..."] + unique_refs)
        
        if target_ref != "Seçiniz...":
            df_gorev = df[df['Taniyanlar'].str.contains(target_ref, case=False, na=False)]
            
            total = len(df_gorev)
            done = len(df_gorev[df_gorev['Calisma_Durumu'] == "Görüşüldü 👍"])
            ratio = int((done/total)*100) if total > 0 else 0
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Toplam Sorumluluk", total)
            c2.metric("Tamamlanan", done, f"%{ratio} Başarı")
            c3.metric("Kalan", total - done, delta_color="inverse")
            
            st.divider()
            
            if total > 0:
                try:
                    pdf_bytes = create_pdf(df_gorev, target_ref)
                    st.download_button(
                        label="📄 PDF OLARAK İNDİR",
                        data=pdf_bytes,
                        file_name=f"{target_ref}_Liste.pdf",
                        mime="application/pdf",
                        type="primary"
                    )
                except Exception as e:
                    st.error(f"PDF Hatası: {e}")

            # Tablo
            def color_status(val): return f'background-color: {"#ffcdd2" if val == "Bekliyor ⏳" else "#c8e6c9"}'
            
            st.dataframe(df_gorev[['Sicil_No','Ad_Soyad','Telefon','Calisma_Durumu','Kurum']].style.map(color_status, subset=['Calisma_Durumu']), use_container_width=True, height=600, hide_index=True)
            
            # Düzenleme için alt tablo
            st.caption("Düzenlemek için aşağıdan seçin:")
            event_gorev = st.dataframe(df_gorev[['Sicil_No','Ad_Soyad']], use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row")
            if len(event_gorev.selection.rows) > 0:
                idx = event_gorev.selection.rows[0]
                sicil = df_gorev.iloc[idx]['Sicil_No']
                g_idx = df[df['Sicil_No'] == sicil].index[0]
                entry_form_dialog(df.iloc[g_idx], g_idx + 2, sicil, user, df.columns.tolist(), ws, ws_log, df_log, unique_refs)

# -----------------------------------------------------------------------------
# MENÜ 3: KÖR NOKTA ANALİZİ
# -----------------------------------------------------------------------------
elif menu == "📉 'KÖR NOKTA' ANALİZİ" and user['Rol'] == 'ADMIN':
    st.title("📉 Risk Analizi")
    
    reg_list = ["TÜMÜ"] + sorted(df['Temsilcilik'].unique().tolist())
    sel_reg = st.selectbox("Bölge Seç:", reg_list)
    
    df_anl = df if sel_reg == "TÜMÜ" else df[df['Temsilcilik'] == sel_reg]
    df_unt = df_anl[df_anl['Taninma_Durumu'] == "Kör Nokta (Tanınmıyor) ❌"]
    
    c1, c2 = st.columns(2)
    c1.metric("Toplam Üye", len(df_anl))
    c2.metric("Kör Nokta Sayısı", len(df_unt), delta_color="inverse")
    
    tab1, tab2, tab3 = st.tabs(["BÖLGESEL AÇIK", "AKADEMİK AÇIK", "HEDEF LİSTE"])
    
    with tab1:
        if sel_reg == "TÜMÜ":
            # Genel Karşılaştırma
            tot = df['Temsilcilik'].value_counts().reset_index()
            unt = df_unt['Temsilcilik'].value_counts().reset_index()
            merged = pd.merge(tot, unt, on='Temsilcilik', how='left').fillna(0)
            merged.columns = ['Bölge', 'Toplam', 'Taninmayan']
            merged['Oran'] = (merged['Taninmayan'] / merged['Toplam'] * 100).astype(int)
            merged['Etiket'] = merged.apply(lambda x: f"%{x['Oran']} Açık", axis=1)
            st.plotly_chart(px.bar(merged.sort_values('Oran', ascending=False), x='Oran', y='Bölge', text='Etiket', color='Oran', color_continuous_scale='Reds'), use_container_width=True)
        else:
            st.info("Tek bölge seçili, detayları diğer sekmelerde görebilirsiniz.")

    with tab2:
        uni_tot = df_anl['Universite'].value_counts().reset_index()
        uni_unt = df_unt['Universite'].value_counts().reset_index()
        m_uni = pd.merge(uni_tot, uni_unt, on='Universite', how='left').fillna(0)
        m_uni.columns = ['Okul', 'Toplam', 'Taninmayan']
        m_uni['Oran'] = (m_uni['Taninmayan'] / m_uni['Toplam'] * 100).astype(int)
        st.plotly_chart(px.bar(m_uni.head(15), x='Oran', y='Okul', color='Oran', title="Üniversite Bazlı Risk"), use_container_width=True)

    with tab3:
        st.dataframe(df_unt[['Sicil_No', 'Ad_Soyad', 'Telefon', 'Universite']], use_container_width=True)

# -----------------------------------------------------------------------------
# MENÜ 4: AĞ İSTİHBARATI (GEPHI)
# -----------------------------------------------------------------------------
elif menu == "🕸️ AĞ İSTİHBARATI" and user['Rol'] == 'ADMIN':
    st.title("🕸️ Ağ İstihbaratı")
    try:
        import networkx as nx
        import scipy
        
        if 'Taniyanlar' in df.columns:
            df_net = df[df['Taniyanlar'].str.len() > 1].copy()
            df_net['Ref_List'] = df_net['Taniyanlar'].astype(str).str.split(',')
            df_exp = df_net.explode('Ref_List')
            df_exp['Ref_List'] = df_exp['Ref_List'].str.strip()
            df_exp = df_exp[df_exp['Ref_List'].str.len() > 1]
            
            all_refs = df_exp['Ref_List'].value_counts().index.tolist()
            
            n_ref = st.slider("Görüntülenecek Referans Sayısı", 3, 40, 10)
            
            with st.spinner("Harita çiziliyor..."):
                sel_refs = all_refs[:n_ref]
                G = nx.Graph()
                for r in sel_refs: G.add_node(r, type='ref', size=30, color='red')
                
                filt = df_exp[df_exp['Ref_List'].isin(sel_refs)]
                # Renk Haritası
                u_loc = df['Temsilcilik'].unique()
                colors = px.colors.qualitative.Dark24
                c_map = {l: colors[i%len(colors)] for i,l in enumerate(u_loc)}
                sicil_loc = dict(zip(df['Sicil_No'].astype(str), df['Temsilcilik']))
                sicil_name = dict(zip(df['Sicil_No'].astype(str), df['Ad_Soyad']))

                for i, row in filt.iterrows():
                    s = str(row['Sicil_No'])
                    r = row['Ref_List']
                    loc = sicil_loc.get(s, "Bilinmiyor")
                    if not G.has_node(s): G.add_node(s, type='mem', size=5, color=c_map.get(loc, '#ccc'), label=sicil_name.get(s,""))
                    G.add_edge(r, s)
                
                pos = nx.spring_layout(G, k=0.6, iterations=50, seed=42)
                
                edge_x, edge_y = [], []
                for e in G.edges():
                    x0, y0 = pos[e[0]]; x1, y1 = pos[e[1]]
                    edge_x.extend([x0, x1, None]); edge_y.extend([y0, y1, None])
                
                et = go.Scatter(x=edge_x, y=edge_y, line=dict(width=0.2, color='#ddd'), hoverinfo='none', mode='lines')
                
                rx, ry, rt = [], [], []
                for n in G.nodes():
                    if G.nodes[n]['type'] == 'ref': rx.append(pos[n][0]); ry.append(pos[n][1]); rt.append(n)
                rt_trace = go.Scatter(x=rx, y=ry, mode='markers+text', text=rt, textposition="top center", marker=dict(size=25, color='red'))
                
                mx, my, mt, mc = [], [], [], []
                for n in G.nodes():
                    if G.nodes[n]['type'] == 'mem': mx.append(pos[n][0]); my.append(pos[n][1]); mt.append(G.nodes[n]['label']); mc.append(G.nodes[n]['color'])
                mt_trace = go.Scatter(x=mx, y=my, mode='markers', hovertext=mt, marker=dict(size=5, color=mc))
                
                st.plotly_chart(go.Figure(data=[et, mt_trace, rt_trace], layout=go.Layout(showlegend=False, height=700, plot_bgcolor='white')), use_container_width=True)

    except ImportError: st.error("Lütfen requirements.txt dosyasına 'networkx' ve 'scipy' ekleyin.")

# -----------------------------------------------------------------------------
# MENÜ 5: DEMOGRAFİK
# -----------------------------------------------------------------------------
elif menu == "🎓 DEMOGRAFİK İSTİHBARAT" and user['Rol'] == 'ADMIN':
    st.title("🎓 Demografik Analiz")
    c1, c2 = st.columns(2)
    with c1:
        uni_c = df['Universite'].value_counts().head(10).reset_index()
        st.plotly_chart(px.bar(uni_c, x='count', y='Universite', title="Top 10 Üniversite"), use_container_width=True)
    with c2:
        age_c = df[df['Yas']>18]['Yas_Grubu'].value_counts().reset_index()
        st.plotly_chart(px.pie(age_c, names='Yas_Grubu', values='count', title="Yaş Dağılımı"), use_container_width=True)

# -----------------------------------------------------------------------------
# MENÜ 6: VERİ GİRİŞİ (TEMEL)
# -----------------------------------------------------------------------------
elif menu == "📝 Veri Girişi":
    st.header("📋 Hızlı Arama")
    search = st.text_input("İsim Ara:", key="main_search")
    
    df_show = df
    if search: df_show = df[df['Ad_Soyad'].str.contains(search, case=False, na=False)]
    
    event = st.dataframe(df_show[['Sicil_No', 'Ad_Soyad', 'Temsilcilik', 'Taniyanlar']], use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row")
    if len(event.selection.rows) > 0:
        idx = event.selection.rows[0]
        sicil = df_show.iloc[idx]['Sicil_No']
        g_idx = df[df['Sicil_No'] == sicil].index[0]
        entry_form_dialog(df.iloc[g_idx], g_idx + 2, sicil, user, df.columns.tolist(), ws, ws_log, df_log, unique_refs)
