import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from oauth2client.service_account import ServiceAccountCredentials

st.set_page_config(page_title="İMO Van 2026", layout="wide", page_icon="🏗️")

# --- BAĞLANTI AYARLARI ---
@st.cache_resource
def get_connection():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    return client

def get_data():
    client = get_connection()
    try:
        sheet = client.open("Van_IMO_Secim_2026")
        ws = sheet.worksheet("secmenler")
        data = ws.get_all_records()
        df = pd.DataFrame(data)
        
        # Sütun isimlerindeki olası boşlukları temizle (Hata önleyici)
        df.columns = df.columns.str.strip()
        
        # Tüm veriyi metne çevir (Hata önleyici)
        df = df.astype(str)
        return df, ws
    except Exception as e:
        st.error(f"Excel Bağlantı Hatası: {e}")
        return pd.DataFrame(), None

# --- GİRİŞ EKRANI ---
if 'user' not in st.session_state:
    st.session_state.user = None

if st.session_state.user is None:
    st.title("🏗️ İMO VAN 2026 - GİRİŞ")
    with st.form("giris"):
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
                    st.error("Hatalı Kullanıcı Adı veya Şifre!")
            except Exception as e:
                st.error(f"Giriş Hatası: {e}")
    st.stop()

# --- ANA PROGRAM ---
user = st.session_state.user
st.sidebar.info(f"👤 {user['Kullanici_Adi']} | Yetki: {user['Rol']}")

if st.sidebar.button("Çıkış"):
    st.session_state.user = None
    st.rerun()

df, ws = get_data()

# Eğer veri çekilemediyse dur
if df.empty:
    st.warning("Veri bulunamadı veya sütun isimlerinde sorun var.")
    st.stop()

menu = st.sidebar.radio("Menü", ["📝 Seçmen Listesi (Tümü)", "📊 Genel Durum (Analiz)"])

# --- 1. VERİ GİRİŞ EKRANI (LİSTE DİREKT AÇILIR) ---
if menu == "📝 Seçmen Listesi (Tümü)":
    st.header("📝 Seçmen Bilgi Kartı")
    st.caption("👇 Aşağıdaki listeden isme tıklayın, formu doldurun ve kaydedin.")

    # İsteğe bağlı filtreleme kutusu (Arama zorunluluğu yok!)
    filter_text = st.text_input("🔍 İsim Filtrele (İsteğe Bağlı)", placeholder="Listeyi daraltmak istersen buraya yaz...")
    
    # Tabloda gösterilecek ana sütunlar
    cols_to_show = ['Sicil_No', 'Ad_Soyad', 'Kurum', 'Egilim', 'Son_Guncelleyen']
    
    # Filtreleme mantığı
    if filter_text:
        df_show = df[df['Ad_Soyad'].str.contains(filter_text, case=False, na=False)]
    else:
        df_show = df  # Arama yoksa TÜM LİSTEYİ GÖSTER

    # Tıklanabilir Tablo
    event = st.dataframe(
        df_show[cols_to_show], 
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row"
    )

    # LİSTEDEN BİRİ SEÇİLDİYSE FORM AÇILSIN
    if len(event.selection.rows) > 0:
        selected_row_idx = event.selection.rows[0]
        
        # Seçilen kişinin Sicil Numarasını al
        sicil_no = df_show.iloc[selected_row_idx]['Sicil_No']
        
        # Ana listeden (df) o kişiyi bul (Excel sırasını kaybetmemek için)
        gercek_index = df[df['Sicil_No'] == sicil_no].index[0]
        row_num = gercek_index + 2 # Excel satır numarası
        kisi = df.iloc[gercek_index]

        st.divider()
        st.markdown(f"### 👷‍♂️ **{kisi['Ad_Soyad']}** (Sicil: {kisi['Sicil_No']})")

        # --- FORM BAŞLANGICI ---
        with st.form("veri_giris_formu", border=True):
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("##### 🏢 Kurum ve Geçmiş")
                
                # KURUM
                opt_kurum = ["", "Özel Sektör", "Dsi", "Karayolları", "Büyükşehir", "Vaski", "Projeci", "Yapı Denetimci", "İlçe Belediyeleri", "Müteahhit", "Yapsat", "Diğer"]
                curr_kurum = kisi.get('Kurum', "")
                idx_kurum = opt_kurum.index(curr_kurum) if curr_kurum in opt_kurum else 0
                yeni_kurum = st.selectbox("Kurum", opt_kurum, index=idx_kurum)
                
                # 2024 GEÇMİŞ
                opt_24 = ["", "Sarı Liste", "Mavi Liste"]
                curr_24 = kisi.get('Gecmis_2024', "")
                idx_24 = opt_24.index(curr_24) if curr_24 in opt_24 else 0
                yeni_24 = st.selectbox("2024 Tercihi", opt_24, index=idx_24)

                # 2022 GEÇMİŞ
                opt_22 = ["", "Sarı Liste", "Mavi Liste", "Beyaz Liste"]
                curr_22 = kisi.get('Gecmis_2022', "")
                idx_22 = opt_22.index(curr_22) if curr_22 in opt_22 else 0
                yeni_22 = st.selectbox("2022 Tercihi", opt_22, index=idx_22)

                # REFERANS
                yeni_referans = st.text_input("Referans / İlgilenen", value=kisi.get('Referans', ""))

            with col2:
                st.markdown("##### 🗳️ 2026 Durumu ve Detaylar")
                
                # EĞİLİM
                opt_egilim = ["", "Tüm Listemizi Yazar", "Büyük Kısmı Yazar", "Kısmen Yazar", "Karşı Tarafı Destekler", "Kararsızım"]
                curr_egilim = kisi.get('Egilim', "")
                idx_egilim = opt_egilim.index(curr_egilim) if curr_egilim in opt_egilim else 0
                yeni_egilim = st.selectbox("2026 Eğilimi", opt_egilim, index=idx_egilim)

                # ULAŞIM
                opt_ulasim = ["", "Kendi Gelir", "Araç Gerekir", "İlçeden Gelecek", "Temsilcilikten Gelecek"]
                curr_ulasim = kisi.get('Ulasim', "")
                idx_ulasim = opt_ulasim.index(curr_ulasim) if curr_ulasim in opt_ulasim else 0
                yeni_ulasim = st.selectbox("Ulaşım İhtiyacı", opt_ulasim, index=idx_ulasim)

                # RAKİP EKLEME
                yeni_rakip = st.text_input("Rakip Ekleme (Varsa)", value=kisi.get('Rakip_Ekleme', ""))
                
                # ÇİZİKLER
                yeni_cizik = st.text_input("Çizikler / Notlar", value=kisi.get('Cizikler', ""))

            kaydet_btn = st.form_submit_button("✅ BİLGİLERİ KAYDET")

            if kaydet_btn:
                try:
                    headers = df.columns.tolist()
                    
                    # Güncellenecek veriler (Excel Başlığı : Yeni Değer)
                    updates = [
                        ("Kurum", yeni_kurum),
                        ("Gecmis_2024", yeni_24),
                        ("Gecmis_2022", yeni_22),
                        ("Referans", yeni_referans),
                        ("Egilim", yeni_egilim),
                        ("Ulasim", yeni_ulasim),
                        ("Rakip_Ekleme", yeni_rakip),
                        ("Cizikler", yeni_cizik),
                        ("Son_Guncelleyen", user['Kullanici_Adi'])
                    ]
                    
                    for col_name, value in updates:
                        if col_name in headers:
                            col_idx = headers.index(col_name) + 1
                            ws.update_cell(row_num, col_idx, value)
                    
                    st.success(f"✅ {kisi['Ad_Soyad']} güncellendi!")
                    
                except Exception as e:
                    st.error(f"Kayıt Hatası: {e}")

# --- 2. ANALİZ EKRANI ---
elif menu == "📊 Genel Durum (Analiz)":
    st.title("📊 Seçim Komuta Merkezi")
    
    toplam = len(df)
    # Eğilimi boş olmayanlar
    ulasilan = len(df[df['Egilim'].str.len() > 1])
    bizimkiler = len(df[df['Egilim'].isin(["Tüm Listemizi Yazar", "Büyük Kısmı Yazar"])])

    c1, c2, c3 = st.columns(3)
    c1.metric("Toplam Seçmen", toplam)
    c2.metric("Veri Girilen", ulasilan, f"%{int(ulasilan/toplam*100) if toplam else 0}")
    c3.metric("🎯 Potansiyel Oyumuz", bizimkiler)
    
    st.divider()

    if ulasilan > 0:
        tab1, tab2 = st.tabs(["Genel Dağılım", "Kurum Analizi"])
        
        with tab1:
            fig_pie = px.pie(df[df['Egilim'].str.len() > 1], names='Egilim', title='Oy Tercih Dağılımı')
            st.plotly_chart(fig_pie, use_container_width=True)
            
        with tab2:
            df_bizim = df[df['Egilim'].isin(["Tüm Listemizi Yazar", "Büyük Kısmı Yazar"])]
            if not df_bizim.empty:
                fig_kurum = px.bar(df_bizim, x='Kurum', title="Bize Oy Vereceklerin Kurum Dağılımı")
                st.plotly_chart(fig_kurum, use_container_width=True)
    else:
        st.info("Henüz yeterli veri girişi yapılmadı.")
