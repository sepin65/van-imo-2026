import streamlit as st
import pandas as pd
import gspread
import plotly.express as px
import plotly.graph_objects as go
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import time
import math
import networkx as nx # YENİ KÜTÜPHANE (Kümeleme için şart)

# --- 1. SAYFA AYARLARI ---
st.set_page_config(
    page_title="İMO Van 2026 - Karargah", 
    layout="wide", 
    page_icon="🏗️",
    initial_sidebar_state="collapsed"
)

# --- 2. BAĞLANTIYI KUR ---
@st.cache_resource
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
                if "/" in date_str:
                    dt = pd.to_datetime(date_str, dayfirst=True, errors='coerce')
                    if pd.notnull(dt): return current_year - dt.year
                elif "." in date_str:
                    dt = pd.to_datetime(date_str, format="%d.%m.%Y", errors='coerce')
                    if pd.notnull(dt): return current_year - dt.year
                elif len(date_str) == 4 and date_str.isdigit():
                    return current_year - int(date_str)
                return 0
            except: return 0
        df['Yas'] = df['Dogum_Yili'].apply(calculate_age_robust)

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

        # --- LOGLAR ---
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

        return df, ws, df_log, ws_log

    except Exception as e:
        st.error(f"Sistem Hatası: {e}")
        return pd.DataFrame(), None, pd.DataFrame(), None

# --- GİRİŞ EKRANI ---
if 'user' not in st.session_state: st.session_state.user = None
if st.session_state.user is None:
    st.title("🏗️ İMO SEÇİM SİSTEMİ")
    st.info("⏳ GİRİŞ EKRANI")
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

# --- FORM DIALOG ---
@st.dialog("✏️ SEÇMEN KARTI")
def entry_form_dialog(kisi, row_n, sicil, user, df_cols, ws, ws_log, df_log):
    st.markdown(f"### 👤 {kisi['Ad_Soyad']}")
    
    yas = kisi.get('Yas', 0)
    uni = kisi.get('Universite', '')
    temsil = kisi.get('Temsilcilik', 'VAN MERKEZ')
    taniyan = kisi.get('Taniyanlar', '')
    
    c1, c2, c3 = st.columns(3)
    c1.info(f"📍 **{temsil}**")
    c2.info(f"🎓 **{uni if len(uni)>2 else '-'}**")
    c3.info(f"🎂 **{int(yas) if yas > 0 else '?'} Yaş**")
    
    if len(str(taniyan)) > 1: st.warning(f"🔗 **Tanıyanlar:** {taniyan}")
    
    is_admin = (user['Rol'] == 'ADMIN')
    def get(f): return kisi.get(f, "") if is_admin else ""

    st.markdown("##### 🕒 Geçmiş Hareketler")
    if df_log is not None and not df_log.empty and 'Sicil_No' in df_log.columns:
        logs = df_log[df_log['Sicil_No'].astype(str).str.strip() == str(sicil).strip()]
        if not logs.empty:
            st.dataframe(logs[['Zaman','Kullanici','Egilim','Cizikler']].sort_values('Zaman', ascending=False), hide_index=True, use_container_width=True)
        else: st.caption("Kayıt yok.")
    
    with st.form("form"):
        c1, c2 = st.columns(2)
        with c1:
            k_opt = ["", "Özel Sektör", "Dsi", "Karayolları", "Büyükşehir", "Vaski", "Projeci", "Yapı Denetimci", "İlçe Belediyeleri", "Müteahhit", "Yapsat", "Çevre Şehircilik", "Emekli", "Diğer"]
            nk = st.selectbox("Kurum", k_opt, index=k_opt.index(kisi.get('Kurum',"")) if kisi.get('Kurum',"") in k_opt else 0)
            n24 = st.selectbox("2024", ["", "Sarı Liste", "Mavi Liste"], index=["", "Sarı Liste", "Mavi Liste"].index(get('Gecmis_2024')) if get('Gecmis_2024') in ["", "Sarı Liste", "Mavi Liste"] else 0)
            n22 = st.selectbox("2022", ["", "Sarı Liste", "Mavi Liste", "Beyaz Liste"], index=["", "Sarı Liste", "Mavi Liste", "Beyaz Liste"].index(get('Gecmis_2022')) if get('Gecmis_2022') in ["", "Sarı Liste", "Mavi Liste", "Beyaz Liste"] else 0)
        with c2:
            e_opt = ["", "Tüm Listemizi Yazar", "Büyük Kısmı Yazar", "Kısmen Yazar", "Karşı Tarafı Destekler", "Kararsızım"]
            ne = st.selectbox("2026 EĞİLİMİ", e_opt, index=e_opt.index(get('Egilim')) if get('Egilim') in e_opt else 0)
            nt = st.selectbox("Temas", ["", "Kendim Görüştüm", "Arkadaşım/Akraba Aracılığı", "Tanımıyorum"], index=["", "Kendim Görüştüm", "Arkadaşım/Akraba Aracılığı", "Tanımıyorum"].index(get('Temas_Durumu')) if get('Temas_Durumu') in ["", "Kendim Görüştüm", "Arkadaşım/Akraba Aracılığı", "Tanımıyorum"] else 0)
            nu = st.selectbox("Ulaşım", ["", "Kendisi Gelir", "Araç Gerekir", "İlçeden Gelecek"], index=["", "Kendisi Gelir", "Araç Gerekir", "İlçeden Gelecek"].index(get('Ulasim')) if get('Ulasim') in ["", "Kendisi Gelir", "Araç Gerekir", "İlçeden Gelecek"] else 0)

        ntaniyan = st.text_input("🔗 Tanıyanlar (Virgülle ayırın)", value=get('Taniyanlar'))
        nn = st.text_area("Notlar", value=get('Cizikler'))
        nr = st.text_input("Rakip Ekleme", value=get('Rakip_Ekleme'))
        nref = st.text_input("Referans", value=get('Referans'))
        
        with st.expander("🛠️ Bilgi Düzeltme"):
            c_ex1, c_ex2 = st.columns(2)
            n_uni = c_ex1.text_input("Üniversite", value=kisi.get('Universite', ''))
            n_temsil = c_ex2.text_input("Temsilcilik", value=kisi.get('Temsilcilik', ''))

        if st.form_submit_button("✅ KAYDET"):
            updates = [
                ("Kurum", nk), ("Gecmis_2024", n24), ("Gecmis_2022", n22),
                ("Egilim", ne), ("Temas_Durumu", nt), ("Ulasim", nu),
                ("Cizikler", nn), ("Rakip_Ekleme", nr), ("Referans", nref),
                ("Universite", n_uni), ("Temsilcilik", n_temsil),
                ("Tanıyanlar", ntaniyan),
                ("Son_Guncelleyen", user['Kullanici_Adi'])
            ]
            for col, val in updates:
                target = col
                if col == 'Universite' and 'Üniversite' in df_cols: target = 'Üniversite'
                if col == 'Temsilcilik' and 'Temsilcilik' in df_cols: target = 'Temsilcilik'
                if col == 'Tanıyanlar' and 'Taniyanlar' in df_cols: target = 'Taniyanlar'
                
                if col in df_cols: ws.update_cell(row_n, df_cols.index(col)+1, val)
                elif target in df_cols: ws.update_cell(row_n, df_cols.index(target)+1, val)
            
            if ws_log:
                ws_log.append_row([datetime.now().strftime("%Y-%m-%d %H:%M"), str(sicil), kisi['Ad_Soyad'], user['Kullanici_Adi'], nk, ne, n24, n22, nt, nr, nu, nn, ntaniyan])
            st.toast("Kaydedildi!", icon="💾")
            time.sleep(1)
            st.rerun()

# --- ANA EKRAN ---
user = st.session_state.user
df, ws, df_log, ws_log = get_data()
if df.empty:
    st.warning("Veriler yükleniyor...")
    st.stop()

# --- MENÜ ---
menu_options = ["📝 Veri Girişi"]
if user['Rol'] == 'ADMIN':
    menu_options = ["📊 GENEL ANALİZ", "🕸️ AĞ İSTİHBARATI", "🎓 DEMOGRAFİK İSTİHBARAT", "📝 Veri Girişi"]

menu = st.sidebar.radio("Menü", menu_options)

# =========================================================
# 🕸️ AĞ İSTİHBARATI (KÜME ANALİZİ EKLENDİ)
# =========================================================
if menu == "🕸️ AĞ İSTİHBARATI" and user['Rol'] == 'ADMIN':
    st.title("🕸️ Ağ İstihbaratı ve Kümeleme")
    st.info("Kim kiminle ilişkili? Referansların ortak kümeleri ve etki alanları.")

    if 'Taniyanlar' in df.columns:
        df_network = df[df['Taniyanlar'].str.len() > 1].copy()
        df_network['Ref_List'] = df_network['Taniyanlar'].astype(str).str.split(',')
        df_exploded = df_network.explode('Ref_List')
        df_exploded['Ref_List'] = df_exploded['Ref_List'].str.strip()
        df_exploded = df_exploded[df_exploded['Ref_List'].str.len() > 1]

        # Ana Referans Listesi
        all_refs = sorted(df_exploded['Ref_List'].unique())

        tab1, tab2, tab3 = st.tabs(["🕸️ KÜME HARİTASI (NETWORK)", "🔥 KESİŞİM MATRİSİ", "🏆 LİDERLER"])

        # --- TAB 1: KÜME HARİTASI (NETWORK GRAPH) ---
        with tab1:
            st.subheader("İlişki Ağı Haritası")
            st.caption("Bu harita, referansların birbirine olan yakınlığını gösterir. Çizgi varsa, ortak tanıdıkları var demektir.")
            
            # Filtreleme (Çok kalabalık olmasın diye)
            min_overlap = st.slider("En Az Ortak Tanıdık Sayısı (Bağlantı Gücü)", 1, 20, 3)
            selected_network_refs = st.multiselect("Haritaya Dahil Edilecekler:", all_refs, default=all_refs[:15])
            
            if len(selected_network_refs) > 1:
                # Graph Oluşturma
                G = nx.Graph()
                
                # Düğümleri Ekle
                for ref in selected_network_refs:
                    count = len(df_exploded[df_exploded['Ref_List'] == ref])
                    G.add_node(ref, size=count)
                
                # Kenarları (Edges) Ekle
                import itertools
                for r1, r2 in itertools.combinations(selected_network_refs, 2):
                    set1 = set(df_exploded[df_exploded['Ref_List'] == r1]['Sicil_No'])
                    set2 = set(df_exploded[df_exploded['Ref_List'] == r2]['Sicil_No'])
                    common = len(set1.intersection(set2))
                    if common >= min_overlap:
                        G.add_edge(r1, r2, weight=common)
                
                # Pozisyonlama
                pos = nx.spring_layout(G, seed=42)
                
                # Çizim (Plotly)
                edge_x = []
                edge_y = []
                edge_text = []
                for edge in G.edges(data=True):
                    x0, y0 = pos[edge[0]]
                    x1, y1 = pos[edge[1]]
                    edge_x.extend([x0, x1, None])
                    edge_y.extend([y0, y1, None])
                    edge_text.append(f"Ortak: {edge[2]['weight']}")

                edge_trace = go.Scatter(
                    x=edge_x, y=edge_y,
                    line=dict(width=0.5, color='#888'),
                    hoverinfo='text',
                    mode='lines')

                node_x = []
                node_y = []
                node_text = []
                node_size = []
                for node in G.nodes():
                    x, y = pos[node]
                    node_x.append(x)
                    node_y.append(y)
                    count = G.nodes[node]['size']
                    node_text.append(f"{node} ({count} kişi)")
                    node_size.append(10 + (count / 2)) # Boyutlandırma

                node_trace = go.Scatter(
                    x=node_x, y=node_y,
                    mode='markers+text',
                    text=[node for node in G.nodes()],
                    textposition="top center",
                    hovertext=node_text,
                    marker=dict(
                        showscale=True,
                        colorscale='YlGnBu',
                        size=node_size,
                        color=node_size,
                        line_width=2))

                fig_net = go.Figure(data=[edge_trace, node_trace],
                                    layout=go.Layout(
                                        showlegend=False,
                                        hovermode='closest',
                                        margin=dict(b=0,l=0,r=0,t=0),
                                        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                                        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False))
                                    )
                st.plotly_chart(fig_net, use_container_width=True)
            else:
                st.warning("Lütfen en az 2 referans seçin.")

        # --- TAB 2: KESİŞİM MATRİSİ ---
        with tab2:
            st.subheader("Kesişim Matrisi")
            selected_matrix_refs = st.multiselect("Matris Kişileri:", all_refs, default=all_refs[:10])
            
            if len(selected_matrix_refs) > 1:
                matrix_data = []
                for r1 in selected_matrix_refs:
                    row = []
                    set1 = set(df_exploded[df_exploded['Ref_List'] == r1]['Sicil_No'])
                    for r2 in selected_matrix_refs:
                        set2 = set(df_exploded[df_exploded['Ref_List'] == r2]['Sicil_No'])
                        intersection = len(set1.intersection(set2))
                        row.append(intersection)
                    matrix_data.append(row)
                
                fig_heat = px.imshow(matrix_data,
                                    labels=dict(x="Referans B", y="Referans A", color="Ortak"),
                                    x=selected_matrix_refs, y=selected_matrix_refs, text_auto=True)
                st.plotly_chart(fig_heat, use_container_width=True)

        # --- TAB 3: LİDERLER ---
        with tab3:
            ref_counts = df_exploded['Ref_List'].value_counts().reset_index()
            ref_counts.columns = ['Referans', 'Kişi Sayısı']
            st.plotly_chart(px.bar(ref_counts.head(20), x='Kişi Sayısı', y='Referans', orientation='h'), use_container_width=True)

# =========================================================
# 🎓 DEMOGRAFİK İSTİHBARAT
# =========================================================
elif menu == "🎓 DEMOGRAFİK İSTİHBARAT" and user['Rol'] == 'ADMIN':
    st.title("🎓 Stratejik Demografi")
    df_valid_age = df[df['Yas'] > 18]
    tab1, tab2, tab3 = st.tabs(["🏛️ ÜNİVERSİTE", "🌍 BÖLGESEL", "🏢 KURUMSAL"])

    with tab1:
        if 'Universite' in df.columns:
            uni_list = sorted([u for u in df['Universite'].unique() if len(str(u)) > 2])
            selected_uni = st.selectbox("Üniversite Seçin:", ["TÜMÜ"] + uni_list)
            df_uni = df[df['Universite'] == selected_uni] if selected_uni != "TÜMÜ" else df[df['Universite'].str.len() > 2]
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Kişi", len(df_uni))
            valid_ages = df_uni[df_uni['Yas'] > 18]['Yas']
            c2.metric("Yaş Ort.", int(valid_ages.mean()) if not valid_ages.empty else "-")
            c3.metric("Bölge", df_uni['Temsilcilik'].mode()[0] if not df_uni.empty else "-")
            
            c_g1, c_g2 = st.columns(2)
            with c_g1:
                df_pie = df_uni[df_uni['Yas'] > 18]
                if not df_pie.empty:
                    age_labels = ["20-24", "25-29", "30-34", "35-39", "40-44", "45-49", "50-54", "55-59", "60-64", "65+"]
                    age_counts = df_pie['Yas_Grubu'].value_counts().reindex(age_labels, fill_value=0).reset_index()
                    st.plotly_chart(px.bar(age_counts[age_counts['count']>0], x='Yas_Grubu', y='count', title="Yaş Dağılımı"), use_container_width=True)
            with c_g2:
                st.plotly_chart(px.bar(df_uni['Temsilcilik'].value_counts().reset_index(), x='Temsilcilik', y='count', title="Bölge"), use_container_width=True)

    with tab2:
        target_region = st.selectbox("Bölge Seçin:", sorted([l for l in df['Temsilcilik'].unique() if len(str(l))>2]))
        if target_region:
            df_reg = df[df['Temsilcilik'] == target_region]
            c1, c2, c3 = st.columns(3)
            c1.metric("Üye", len(df_reg))
            c2.metric("Yaş Ort.", int(df_reg[df_reg['Yas']>18]['Yas'].mean()) if not df_reg[df_reg['Yas']>18].empty else "-")
            c3.metric("Üniversite", df_reg['Universite'].mode()[0] if not df_reg.empty else "-")
            st.divider()
            c_d1, c_d2 = st.columns(2)
            with c_d1: 
                uni_c = df_reg[df_reg['Universite'].str.len()>2]['Universite'].value_counts().head(7).reset_index()
                st.plotly_chart(px.bar(uni_c, x='count', y='Universite', orientation='h'), use_container_width=True)
            with c_d2:
                st.dataframe(df_reg[['Ad_Soyad', 'Universite', 'Yas', 'Taniyanlar']], use_container_width=True)

    with tab3:
        sel_kurum = st.selectbox("Kurum Seçin:", ["TÜMÜ"] + sorted([k for k in df['Kurum'].unique() if len(str(k))>2]))
        df_kurum = df[df['Kurum'] == sel_kurum] if sel_kurum != "TÜMÜ" else df
        c1, c2 = st.columns(2)
        with c1:
            u_data = df_kurum[df_kurum['Universite'].str.len()>2]['Universite'].value_counts().head(10)
            st.bar_chart(u_data)
        with c2:
            if not df_kurum[df_kurum['Yas']>18].empty:
                st.plotly_chart(px.pie(df_kurum[df_kurum['Yas']>18], names='Yas_Grubu', hole=0.5), use_container_width=True)

# =========================================================
# GENEL ANALİZ
# =========================================================
elif menu == "📊 GENEL ANALİZ" and user['Rol'] == 'ADMIN':
    st.title("📊 Genel Durum")
    temas = df[df['Egilim'].str.len() > 1]
    bizim = temas[temas['Egilim'].isin(["Tüm Listemizi Yazar", "Büyük Kısmı Yazar"])]
    c1, c2, c3 = st.columns(3)
    c1.metric("Toplam", len(df))
    c2.metric("Ulaşılan", len(temas))
    c3.metric("Bizim", len(bizim))
    st.plotly_chart(px.pie(temas, names='Egilim', title="Saha Durumu", hole=0.4), use_container_width=True)

# =========================================================
# VERİ GİRİŞİ
# =========================================================
elif menu == "📝 Veri Girişi":
    st.header("📋 Veri Girişi")
    if 'search_term' not in st.session_state: st.session_state.search_term = ""
    def update_search(): st.session_state.search_term = st.session_state.widget_search
    search = st.text_input("🔍 Ara", value=st.session_state.search_term, key="widget_search", on_change=update_search)
    
    ref_list = sorted([str(x) for x in df['Taniyanlar'].unique() if len(str(x)) > 1]) if 'Taniyanlar' in df.columns else []
    sel_ref = st.selectbox("Referans Filtre:", ["HEPSİ"] + ref_list)
    
    df_show = df
    if sel_ref != "HEPSİ": df_show = df_show[df_show['Taniyanlar'] == sel_ref]
    if search: 
        df_show = df_show[df_show['Ad_Soyad'].str.contains(search, case=False, na=False) | df_show['Taniyanlar'].str.contains(search, case=False, na=False)]

    cols = ['Sicil_No', 'Ad_Soyad', 'Universite', 'Temsilcilik', 'Kurum', 'Egilim', 'Taniyanlar']
    final_cols = [c for c in cols if c in df.columns]
    
    page_size = 20
    if 'page_number' not in st.session_state: st.session_state.page_number = 1
    total_pages = math.ceil(len(df_show)/page_size) if len(df_show) > 0 else 1
    
    if len(df_show) > 0:
        c1, c2, c3 = st.columns([1,2,1])
        with c1: 
            if st.button("⬅️") and st.session_state.page_number > 1: st.session_state.page_number -= 1
        with c3:
            if st.button("➡️") and st.session_state.page_number < total_pages: st.session_state.page_number += 1
        with c2: 
            target = st.number_input("Sayfa", 1, total_pages, st.session_state.page_number)
            if target != st.session_state.page_number:
                st.session_state.page_number = target
                st.rerun()
        
        start = (st.session_state.page_number-1)*page_size
        event = st.dataframe(df_show.iloc[start:start+page_size][final_cols], use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row")
        
        if len(event.selection.rows) > 0:
            idx = event.selection.rows[0]
            sicil = df_show.iloc[start:start+page_size].iloc[idx]['Sicil_No']
            g_idx = df[df['Sicil_No'] == sicil].index[0]
            entry_form_dialog(df.iloc[g_idx], g_idx + 2, sicil, user, df.columns.tolist(), ws, ws_log, df_log)
    else: st.warning("Kayıt yok.")
