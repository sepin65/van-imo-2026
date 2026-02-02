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
from fpdf import FPDF
import networkx as nx

# =============================================================================
# 1. AYARLAR & BAĞLANTI
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
# 2. VERİ MOTORU (AKILLI HAFIZA - 10 DK)
# =============================================================================
@st.cache_data(ttl=600) 
def fetch_data_from_google():
    client = get_connection()
    try:
        sheet = client.open("Van_IMO_Secim_2026")
        ws = sheet.worksheet("secmenler")
        all_data = ws.get_all_values()
        try:
            ws_log = sheet.worksheet("log_kayitlari")
            log_data = ws_log.get_all_values()
        except: log_data = []
        return all_data, log_data
    except Exception as e: return None, None

def get_data():
    all_data, log_raw = fetch_data_from_google()
    client = get_connection()
    try:
        sheet = client.open("Van_IMO_Secim_2026")
        ws = sheet.worksheet("secmenler")
        try: ws_log = sheet.worksheet("log_kayitlari")
        except: ws_log = sheet.add_worksheet("log_kayitlari", 1000, 20)
    except: return pd.DataFrame(), None, pd.DataFrame(), None, []

    if not all_data or len(all_data) < 2: return pd.DataFrame(), ws, pd.DataFrame(), ws_log, []

    headers = [h.strip() for h in all_data[0]]
    rows = all_data[1:]
    cleaned_headers = [h if h != "" else f"Bos_Sutun_{i}" for i, h in enumerate(headers)]
    df = pd.DataFrame(rows, columns=cleaned_headers)

    if log_raw and len(log_raw) > 1: df_log = pd.DataFrame(log_raw[1:], columns=log_raw[0])
    else: df_log = pd.DataFrame(columns=['Zaman', 'Sicil_No', 'Ad_Soyad', 'Kullanici'])

    rename_map = {'Üniversite': 'Universite', 'Doğum_Tarihi': 'Dogum_Tarihi', 'Doğum Tarihi': 'Dogum_Tarihi', 'Doğum_Yeri': 'Dogum_Yeri', 'Doğum Yeri': 'Dogum_Yeri', 'Eğilim': 'Egilim', 'Ulaşım': 'Ulasim', 'Temsilcilik': 'Temsilcilik', 'Tanıyanlar': 'Taniyanlar'}
    df.rename(columns=rename_map, inplace=True)

    required = ['Referans', 'Sandik_No', 'Egilim', 'Kurum', 'Ad_Soyad', 'Sicil_No', 'Temas_Durumu', 'Ulasim', 'Cizikler', 'Telefon', 'Universite', 'Dogum_Tarihi', 'Dogum_Yeri', 'Temsilcilik', 'Taniyanlar']
    for col in required:
        if col not in df.columns: df[col] = ""

    df['Temsilcilik'] = df['Temsilcilik'].apply(lambda x: str(x).strip().upper() if len(str(x))>2 else "VAN MERKEZ")
    df['Universite'] = df['Universite'].str.upper().str.strip()
    
    curr = datetime.now().year
    def get_age(d):
        try:
            if "/" in str(d): return curr - pd.to_datetime(d, dayfirst=True).year
            elif "." in str(d): return curr - pd.to_datetime(d, format="%d.%m.%Y").year
            elif len(str(d))==4: return curr - int(d)
            return 0
        except: return 0
    df['Yas'] = df['Dogum_Tarihi'].apply(get_age)
    
    def grp_age(a):
        if a==0: return "Belirsiz"; 
        if a<30: return "20-29"; 
        if a<40: return "30-39"; 
        if a<50: return "40-49"; 
        return "50+"
    df['Yas_Grubu'] = df['Yas'].apply(grp_age)

    df['Taninma_Durumu'] = df['Taniyanlar'].apply(lambda x: "Referanslı ✅" if len(str(x)) > 2 else "Kör Nokta (Tanınmıyor) ❌")
    df['Calisma_Durumu'] = df['Temas_Durumu'].apply(lambda x: "Görüşüldü 👍" if len(str(x)) > 2 else "Bekliyor ⏳")
    
    def cat_egilim(x):
        x = str(x).lower()
        if "tüm" in x or "büyük" in x: return "BİZİM (NET)"
        elif "kısmen" in x or "kararsız" in x: return "KARARSIZ / ORTADA"
        elif "karşı" in x: return "RAKİP"
        else: return "BELİRSİZ"
    df['Egilim_Kategori'] = df['Egilim'].apply(cat_egilim)

    try: df['Sandik_No'] = pd.qcut(df['Sicil_No'].astype(int).rank(method='first'), q=6, labels=["1. Sandık", "2. Sandık", "3. Sandık", "4. Sandık", "5. Sandık", "6. Sandık"])
    except: df['Sandik_No'] = "Belirsiz"

    all_refs = []
    for r in df['Taniyanlar'].dropna().astype(str):
        all_refs.extend([x.strip() for x in r.split(',') if len(x.strip()) > 1])
    unique_refs = sorted(list(set(all_refs)))

    return df, ws, df_log, ws_log, unique_refs

# --- PDF MOTORU ---
def create_pdf(df_s, ref_name):
    def clean(t):
        t = str(t).replace('ğ','g').replace('Ğ','G').replace('ş','s').replace('Ş','S').replace('ı','i').replace('İ','I').replace('ü','u').replace('Ü','U').replace('ö','o').replace('Ö','O').replace('ç','c').replace('Ç','C')
        return t.replace("⏳","(-)").replace("👍","(+)").replace("✅","(OK)").replace("❌","(NO)").encode('latin-1','ignore').decode('latin-1')
    pdf = FPDF(); pdf.add_page(); pdf.set_font("Arial", size=10)
    pdf.set_font("Arial", 'B', 14); pdf.cell(0, 10, clean(f"GOREV LISTESI: {ref_name}"), ln=True, align='C'); pdf.ln(5)
    pdf.set_font("Arial", 'B', 8); pdf.cell(15,8,"Sicil",1); pdf.cell(60,8,"Ad Soyad",1); pdf.cell(30,8,"Tel",1); pdf.cell(35,8,"Durum",1); pdf.cell(40,8,"Kurum",1); pdf.ln()
    pdf.set_font("Arial", size=8)
    for i, r in df_s.iterrows():
        pdf.cell(15,7,clean(r['Sicil_No']),1); pdf.cell(60,7,clean(r['Ad_Soyad'])[:30],1); pdf.cell(30,7,clean(r['Telefon']),1); pdf.cell(35,7,clean(r['Calisma_Durumu']),1); pdf.cell(40,7,clean(r['Kurum'])[:25],1); pdf.ln()
    return pdf.output(dest='S').encode('latin-1','replace')

# --- GİRİŞ ---
if 'user' not in st.session_state: st.session_state.user = None
if st.session_state.user is None:
    st.title("🏗️ İMO SEÇİM SİSTEMİ")
    with st.form("giris"):
        u = st.text_input("Kullanıcı"); p = st.text_input("Şifre", type="password")
        if st.form_submit_button("Giriş Yap"):
            try:
                c = get_connection(); users_ws = c.open("Van_IMO_Secim_2026").worksheet("kullanicilar"); ur = pd.DataFrame(users_ws.get_all_records())
                ur.rename(columns={'Ad Soyad': 'Ad_Soyad', 'isim': 'Ad_Soyad', 'İsim': 'Ad_Soyad'}, inplace=True)
                login = ur[ur['Kullanici_Adi'] == u]
                if not login.empty and str(login.iloc[0]['Sifre']) == p:
                    user_dict = login.iloc[0].to_dict()
                    if 'Ad_Soyad' not in user_dict: user_dict['Ad_Soyad'] = user_dict['Kullanici_Adi']
                    st.session_state.user = user_dict; st.rerun()
                else: st.error("Hatalı Giriş")
            except Exception as e: st.error(f"Bağlantı Hatası: {e}")
    st.stop()

# --- ADMIN KARTI ---
@st.dialog("✏️ YÖNETİCİ KARTI")
def admin_card(kisi, row_n, sicil, user, df_cols, ws, ws_log, unique_refs):
    st.markdown(f"### {kisi['Ad_Soyad']}")
    st.info(f"📍 {kisi.get('Temsilcilik','')} | 🎓 {kisi.get('Universite','')} | {kisi.get('Dogum_Yeri','')}")
    if len(str(kisi.get('Taniyanlar','')))>2: st.success(f"🔗 {kisi.get('Taniyanlar','')}")
    with st.form("af"):
        cur_refs = [x.strip() for x in str(kisi.get('Taniyanlar','')).split(',') if len(x.strip())>1]
        nr = st.multiselect("Referanslar", unique_refs, default=cur_refs)
        c1, c2 = st.columns(2)
        nk = c1.selectbox("Kurum", ["", "Özel Sektör", "Dsi", "Karayolları", "Büyükşehir", "Vaski", "Projeci", "Yapı Denetimci", "İlçe Belediyeleri", "Müteahhit", "Yapsat", "Çevre Şehircilik", "Emekli", "Diğer"], index=0 if not kisi.get('Kurum') else ["", "Özel Sektör", "Dsi", "Karayolları", "Büyükşehir", "Vaski", "Projeci", "Yapı Denetimci", "İlçe Belediyeleri", "Müteahhit", "Yapsat", "Çevre Şehircilik", "Emekli", "Diğer"].index(kisi.get('Kurum')) if kisi.get('Kurum') in ["", "Özel Sektör", "Dsi", "Karayolları", "Büyükşehir", "Vaski", "Projeci", "Yapı Denetimci", "İlçe Belediyeleri", "Müteahhit", "Yapsat", "Çevre Şehircilik", "Emekli", "Diğer"] else 0)
        ne = c2.selectbox("Eğilim", ["", "Tüm Listemizi Yazar", "Büyük Kısmı Yazar", "Kısmen Yazar", "Karşı Tarafı Destekler", "Kararsızım"], index=0 if not kisi.get('Egilim') else ["", "Tüm Listemizi Yazar", "Büyük Kısmı Yazar", "Kısmen Yazar", "Karşı Tarafı Destekler", "Kararsızım"].index(kisi.get('Egilim')) if kisi.get('Egilim') in ["", "Tüm Listemizi Yazar", "Büyük Kısmı Yazar", "Kısmen Yazar", "Karşı Tarafı Destekler", "Kararsızım"] else 0)
        nt = st.selectbox("Temas", ["", "Kendim Görüştüm", "Arkadaşım/Akraba Aracılığı", "Tanımıyorum"], index=0 if not kisi.get('Temas_Durumu') else ["", "Kendim Görüştüm", "Arkadaşım/Akraba Aracılığı", "Tanımıyorum"].index(kisi.get('Temas_Durumu')) if kisi.get('Temas_Durumu') in ["", "Kendim Görüştüm", "Arkadaşım/Akraba Aracılığı", "Tanımıyorum"] else 0)
        nn = st.text_area("Not", value=kisi.get('Cizikler',''))
        if st.form_submit_button("KAYDET"):
            r_str = ", ".join(nr)
            ups = [("Kurum",nk), ("Egilim",ne), ("Temas_Durumu",nt), ("Cizikler",nn), ("Tanıyanlar",r_str), ("Son_Guncelleyen",user['Kullanici_Adi'])]
            for c, v in ups:
                t = c if c in df_cols else 'Taniyanlar'; 
                if t in df_cols: ws.update_cell(row_n, df_cols.index(t)+1, v)
            ws_log.append_row([datetime.now().strftime("%Y-%m-%d %H:%M"), str(sicil), kisi['Ad_Soyad'], user['Kullanici_Adi'], nk, ne, "", "", nt, "", "", nn, r_str])
            fetch_data_from_google.clear(); st.toast("Kaydedildi!"); time.sleep(1); st.rerun()

# --- MAIN LOAD ---
user = st.session_state.user
if st.sidebar.button("🔄 VERİLERİ GÜNCELLE"): fetch_data_from_google.clear(); st.toast("Veriler taze!"); time.sleep(0.5); st.rerun()
df, ws, df_log, ws_log, unique_refs = get_data()
if df.empty: st.warning("Veriler yükleniyor..."); st.stop()

# =========================================================
# 👷‍♂️ SAHA EKRANI
# =========================================================
if user['Rol'] != 'ADMIN':
    display_name = user.get('Ad_Soyad', user.get('Kullanici_Adi', 'Kullanıcı'))
    st.header(f"👷‍♂️ Saha Paneli: {display_name}")
    c1, c2 = st.columns([2,1]); search = c1.text_input("🔍 İsim Ara"); regions = ["HEPSİ"] + sorted(df['Temsilcilik'].unique().tolist()); selected_region = c2.selectbox("📍 Bölge:", regions)
    df_saha = df.copy()
    if selected_region != "HEPSİ": df_saha = df_saha[df_saha['Temsilcilik'] == selected_region]
    if search: df_saha = df_saha[df_saha['Ad_Soyad'].str.contains(search, case=False, na=False)]
    cols_saha = ['Sicil_No', 'Ad_Soyad', 'Universite', 'Dogum_Tarihi', 'Temsilcilik', 'Dogum_Yeri']; df_saha['Tanıyorum'] = False
    
    if 'saha_page' not in st.session_state: st.session_state.saha_page = 1
    page_size = 20; total_records = len(df_saha); total_pages = math.ceil(total_records / page_size) if total_records > 0 else 1
    if search != st.session_state.get('ls','') or selected_region != st.session_state.get('lr',''):
        st.session_state.saha_page=1; st.session_state.ls=search; st.session_state.lr=selected_region
    st.info(f"📋 {total_records} Kişi (Sayfa {st.session_state.saha_page}/{total_pages})")
    cp1, cp2, cp3 = st.columns([1, 2, 1])
    if cp1.button("⬅️ Geri", disabled=(st.session_state.saha_page<=1)): st.session_state.saha_page-=1; st.rerun()
    with cp2: 
        sp = st.number_input("Git:", 1, total_pages, st.session_state.saha_page)
        if sp!=st.session_state.saha_page: st.session_state.saha_page=sp; st.rerun()
    if cp3.button("İleri ➡️", disabled=(st.session_state.saha_page>=total_pages)): st.session_state.saha_page+=1; st.rerun()
    
    start=(st.session_state.saha_page-1)*page_size; end=start+page_size; df_p = df_saha.iloc[start:end].copy()
    edited = st.data_editor(df_p[['Tanıyorum']+cols_saha], column_config={"Tanıyorum":st.column_config.CheckboxColumn(default=False)}, disabled=cols_saha, hide_index=True, use_container_width=True, height=750)
    if st.button("✅ KAYDET", type="primary"):
        sel = edited[edited['Tanıyorum']==True]
        if not sel.empty:
            prog=st.progress(0); cnt=0
            for i, r in sel.iterrows():
                if user.get('Ad_Soyad') not in str(df.at[df.index[df['Sicil_No']==r['Sicil_No']][0], 'Taniyanlar']):
                    orig = df.index[df['Sicil_No']==r['Sicil_No']][0]
                    curr = df.at[orig, 'Taniyanlar']; nv = f"{curr}, {user.get('Ad_Soyad')}" if curr else user.get('Ad_Soyad')
                    ws.update_cell(orig+2, df.columns.get_loc('Taniyanlar')+1, nv)
                cnt+=1; prog.progress(cnt/len(sel))
            fetch_data_from_google.clear(); st.success("Eklendi!"); time.sleep(1); st.rerun()
        else: st.warning("Seçim Yok")

# =========================================================
# 👔 ADMIN EKRANI
# =========================================================
else:
    menu = st.sidebar.radio("Menü", ["📊 STRATEJİK ANALİZ", "🤝 REFERANS & PDF", "📉 KÖR NOKTA", "🕸️ AĞ HARİTASI (V48)", "🎓 DEMOGRAFİK & HEDEFLEME", "📝 YÖNETİCİ GİRİŞİ"])

    if menu == "📊 STRATEJİK ANALİZ":
        st.title("📊 Stratejik Komuta"); c1,c2,c3,c4=st.columns(4)
        c1.metric("Toplam", len(df)); c2.metric("Bizim", len(df[df['Egilim_Kategori']=="BİZİM (NET)"]))
        c3.metric("Kararsız", len(df[df['Egilim_Kategori']=="KARARSIZ / ORTADA"]), delta_color="off"); c4.metric("Görüşülen", len(df[df['Calisma_Durumu']=="Görüşüldü 👍"]))
        t1,t2,t3=st.tabs(["EĞİLİM","PERFORMANS","KARARSIZ"])
        with t1:
            st.plotly_chart(px.pie(df, names='Egilim_Kategori', hole=0.4, color='Egilim_Kategori', color_discrete_map={"BİZİM (NET)":"green","KARARSIZ / ORTADA":"gold","RAKİP":"red","BELİRSİZ":"grey"}), use_container_width=True)
            grp = df.groupby(['Sandik_No', 'Egilim_Kategori']).size().reset_index(name='Kişi')
            st.plotly_chart(px.bar(grp, x="Sandik_No", y="Kişi", color="Egilim_Kategori", barmode="group", color_discrete_map={"BİZİM (NET)":"green","KARARSIZ / ORTADA":"gold","RAKİP":"red","BELİRSİZ":"grey"}), use_container_width=True)
        with t2:
            if 'Taniyanlar' in df.columns:
                exp = df.assign(Ref=df['Taniyanlar'].str.split(',')).explode('Ref'); exp['Ref']=exp['Ref'].str.strip(); exp=exp[exp['Ref'].str.len()>1]
                perf = exp.groupby('Ref').agg(Top=('Sicil_No','count'), Ok=('Calisma_Durumu', lambda x:(x=="Görüşüldü 👍").sum())).reset_index(); perf['%']=(perf['Ok']/perf['Top']*100).astype(int)
                st.plotly_chart(px.bar(perf.sort_values('Top', ascending=False).head(20), x='%', y='Ref', orientation='h', title="Performans %"), use_container_width=True)
        with t3: st.dataframe(df[df['Egilim_Kategori']=="KARARSIZ / ORTADA"][['Sicil_No','Ad_Soyad','Taniyanlar']], use_container_width=True)

    elif menu == "🤝 REFERANS & PDF":
        st.title("🤝 Referans Yönetim")
        t1, t2 = st.tabs(["ATAMA", "GÖREV & PDF"])
        with t1:
            s = st.text_input("Kör Nokta Ara"); r = st.selectbox("Bölge", ["HEPSİ"]+sorted(df['Temsilcilik'].unique().tolist()))
            df_a = df[df['Taninma_Durumu'].str.contains("Kör")]; df_a = df_a[df_a['Temsilcilik']==r] if r!="HEPSİ" else df_a
            if s: df_a=df_a[df_a['Ad_Soyad'].str.contains(s, case=False, na=False)]
            ev = st.dataframe(df_a[['Sicil_No','Ad_Soyad','Temsilcilik']], on_select="rerun", selection_mode="single-row", use_container_width=True)
            if len(ev.selection.rows)>0: idx=ev.selection.rows[0]; admin_card(df_a.iloc[idx], df[df['Sicil_No']==df_a.iloc[idx]['Sicil_No']].index[0]+2, df_a.iloc[idx]['Sicil_No'], user, df.columns.tolist(), ws, ws_log, unique_refs)
        with t2:
            tr = st.selectbox("Hangi Referans?", ["Seç..."]+unique_refs)
            if tr!="Seç...":
                df_g = df[df['Taniyanlar'].str.contains(tr, na=False)]; c1,c2=st.columns(2); c1.metric("Toplam",len(df_g)); c2.metric("Görüşülen", len(df_g[df_g['Calisma_Durumu'].str.contains("👍")]))
                try: st.download_button("📄 PDF İNDİR", create_pdf(df_g, tr), f"{tr}.pdf", "application/pdf", type="primary")
                except: st.error("PDF Hatası")
                def clr(v): return f'background-color: {"#ffcdd2" if "Bekliyor" in str(v) else "#c8e6c9"}'
                st.dataframe(df_g[['Sicil_No','Ad_Soyad','Calisma_Durumu']].style.map(clr, subset=['Calisma_Durumu']), use_container_width=True)
                ev_g = st.dataframe(df_g[['Sicil_No','Ad_Soyad']], on_select="rerun", selection_mode="single-row", use_container_width=True)
                if len(ev_g.selection.rows)>0: idx=ev_g.selection.rows[0]; admin_card(df_g.iloc[idx], df[df['Sicil_No']==df_g.iloc[idx]['Sicil_No']].index[0]+2, df_g.iloc[idx]['Sicil_No'], user, df.columns.tolist(), ws, ws_log, unique_refs)

    elif menu == "📉 KÖR NOKTA":
        st.title("📉 Kör Nokta"); sr=st.selectbox("Bölge:", ["TÜMÜ"]+sorted(df['Temsilcilik'].unique().tolist())); da=df if sr=="TÜMÜ" else df[df['Temsilcilik']==sr]; du=da[da['Taninma_Durumu'].str.contains("Kör")]
        c1,c2=st.columns(2); c1.metric("Toplam",len(da)); c2.metric("Kör",len(du),delta_color="inverse")
        t1,t2=st.tabs(["BÖLGE","OKUL"]); 
        with t1: st.plotly_chart(px.bar(du['Temsilcilik'].value_counts().reset_index(), x='count', y='Temsilcilik', orientation='h'), use_container_width=True)
        with t2: st.plotly_chart(px.bar(du['Universite'].value_counts().head(15).reset_index(), x='count', y='Universite'), use_container_width=True)

    elif menu == "🕸️ AĞ HARİTASI (V48)":
        st.title("🕸️ Ağ Haritası")
        try:
            import networkx as nx; n_ref = st.slider("Ref Sayısı", 3, 30, 5)
            df_exp = df.assign(R=df['Taniyanlar'].str.split(',')).explode('R'); df_exp['R'] = df_exp['R'].str.strip(); df_exp = df_exp[df_exp['R'].str.len()>1]
            top_refs = df_exp['R'].value_counts().head(n_ref).index.tolist(); G = nx.Graph()
            for r in top_refs: G.add_node(r, type='ref', size=30, color='red')
            filt = df_exp[df_exp['R'].isin(top_refs)]
            for _,row in filt.iterrows():
                if not G.has_node(str(row['Sicil_No'])): G.add_node(str(row['Sicil_No']), type='mem', size=5, color='blue')
                G.add_edge(row['R'], str(row['Sicil_No']))
            pos = nx.spring_layout(G, k=0.5, seed=42); edge_x=[]; edge_y=[]
            for e in G.edges(): x0,y0=pos[e[0]]; x1,y1=pos[e[1]]; edge_x.extend([x0,x1,None]); edge_y.extend([y0,y1,None])
            fig = go.Figure(data=[go.Scatter(x=edge_x, y=edge_y, mode='lines', line=dict(width=0.3, color='#ccc')), go.Scatter(x=[pos[n][0] for n in G.nodes() if G.nodes[n]['type']=='ref'], y=[pos[n][1] for n in G.nodes() if G.nodes[n]['type']=='ref'], mode='markers+text', text=[n for n in G.nodes() if G.nodes[n]['type']=='ref'], marker=dict(size=20, color='red'))])
            st.plotly_chart(fig, use_container_width=True)
        except: st.error("Kütüphane eksik")

    elif menu == "🎓 DEMOGRAFİK & HEDEFLEME":
        st.title("🎓 Akademik Hedefleme & Boşluk Analizi")
        t1, t2 = st.tabs(["📊 GENEL", "🎯 OKUL DETAY & BOŞLUK"])
        
        with t1:
            c1,c2 = st.columns(2)
            c1.plotly_chart(px.pie(df, names='Yas_Grubu', title="Yaş Dağılımı"), use_container_width=True)
            c2.plotly_chart(px.bar(df['Universite'].value_counts().head(10), title="En Çok Mezun Veren Top 10 Okul"), use_container_width=True)
            
        with t2:
            st.subheader("🎯 Üniversite Bazlı Hedefleme")
            uni_list = sorted([u for u in df['Universite'].unique() if len(str(u))>2])
            selected_uni = st.selectbox("🏫 Üniversite Seç:", uni_list)
            
            show_only_empty = st.checkbox("🔴 Sadece Kimsenin Tanımadığı (Kör Nokta) Üyeleri Göster")
            
            if selected_uni:
                df_uni = df[df['Universite'] == selected_uni]
                
                if show_only_empty:
                    df_uni = df_uni[df_uni['Taninma_Durumu'].str.contains("Kör")]
                    st.warning(f"⚠️ **{selected_uni}** mezunu olup REFERANSI OLMAYAN **{len(df_uni)}** kişi var. (Yüklenilmesi gereken liste!)")
                else:
                    st.info(f"ℹ️ **{selected_uni}** mezunu toplam **{len(df_uni)}** kişi var.")
                
                # İstenilen sütunlar: Ad, Yas, Dogum, TANIYANLAR (Yeni)
                cols_show = ['Sicil_No', 'Ad_Soyad', 'Taniyanlar', 'Yas', 'Dogum_Tarihi', 'Telefon', 'Temsilcilik']
                event = st.dataframe(df_uni[cols_show], use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row", height=600)
                
                if len(event.selection.rows)>0:
                    idx = event.selection.rows[0]; sicil = df_uni.iloc[idx]['Sicil_No']; g_idx = df[df['Sicil_No']==sicil].index[0]
                    admin_card(df.iloc[g_idx], g_idx+2, sicil, user, df.columns.tolist(), ws, ws_log, unique_refs)

    elif menu == "📝 YÖNETİCİ GİRİŞİ":
        st.header("📋 Detaylı Arama")
        s = st.text_input("Ara")
        d = df[df['Ad_Soyad'].str.contains(s, case=False, na=False)] if s else df.head(50)
        ev = st.dataframe(d[['Sicil_No','Ad_Soyad','Taniyanlar']], on_select="rerun", selection_mode="single-row", use_container_width=True)
        if len(ev.selection.rows)>0:
            idx = ev.selection.rows[0]; admin_card(d.iloc[idx], df[df['Sicil_No']==d.iloc[idx]['Sicil_No']].index[0]+2, d.iloc[idx]['Sicil_No'], user, df.columns.tolist(), ws, ws_log, unique_refs)
