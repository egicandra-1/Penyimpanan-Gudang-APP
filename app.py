from google.oauth2.service_account import Credentials
import gspread
import streamlit as st
import json

st.set_page_config(page_title="Sistem Slotting Rak Sederhana", layout="wide")

SCOPE = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

@st.cache_resource
def init_connection_v3():
    if "gcp_json_teks" not in st.secrets:
        st.error("❌ Secrets 'gcp_json_teks' tidak ditemukan!")
        st.stop()
        
    json_text = st.secrets["gcp_json_teks"]
    
    try:
        creds_dict = json.loads(json_text)
    except Exception as e:
        st.error(f"❌ Format JSON di Secrets rusak: {e}")
        st.stop()
    
    if "private_key" not in creds_dict:
        st.error("❌ File JSON tidak memiliki 'private_key'.")
        st.stop()
        
    pk = creds_dict["private_key"]
    pk = pk.replace("\\n", "\n").replace("\r", "")
    
    if "-----BEGIN PRIVATE KEY-----" not in pk or "-----END PRIVATE KEY-----" not in pk:
        st.error("❌ Kunci privat tidak lengkap terpotong!")
        st.stop()
        
    lines = [line.strip() for line in pk.split("\n") if line.strip()]
    creds_dict["private_key"] = "\n".join(lines)
            
    try:
        creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPE)
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"❌ Kunci privat ditolak Google: {e}")
        st.stop()

@st.cache_resource
def get_sheets_connection():
    client = init_connection_v3()
    sheet_file = client.open("Database_Gudang")
    return sheet_file.worksheet("RAK"), sheet_file.worksheet("Isi_Gudang")

sheet_rak, sheet_isi = get_sheets_connection()

def load_data_from_sheets():
    try:
        data_rak = sheet_rak.get_all_records()
        data_isi = sheet_isi.get_all_records()
    except Exception:
        return {}

    struktur = {}
    for r in data_rak:
        nama = r.get("nama_rak")
        if nama:
            struktur[str(nama)] = []

    for item in data_isi:
        r_nama = str(item.get("nama_rak"))
        sku = item.get("sku")
        stok = item.get("stok")
        if r_nama in struktur:
            struktur[r_nama].append({"sku": str(sku), "stok": int(stok) if str(stok).isdigit() else 0})
    return struktur

def save_data_to_sheets():
    sheet_rak.clear()
    sheet_isi.clear()
    sheet_rak.append_row(["nama_rak"])
    sheet_isi.append_row(["nama_rak", "sku", "stok"])
    rows_rak = []
    rows_isi = []
    for r_nama, daftar_item in st.session_state.rak_gudang_tanpa_posisi.items():
        rows_rak.append([r_nama])
        for item in daftar_item:
            rows_isi.append([r_nama, item["sku"], item["stok"]])
    if rows_rak:
        sheet_rak.append_rows(rows_rak)
    if rows_isi:
        sheet_isi.append_rows(rows_isi)

if "rak_gudang_tanpa_posisi" not in st.session_state:
    st.session_state.rak_gudang_tanpa_posisi = load_data_from_sheets()

# ==================== FUNGSI TAMPILAN ====================

def ui_manajemen_rak():
    st.markdown("### 🛠️ Manajemen Struktur")
    st.markdown("#### 🗄️ Kelola Rak")
    opsi_rak = ["[+ Tambah Rak Baru]"] + list(st.session_state.rak_gudang_tanpa_posisi.keys())
    rak_terpilih_mgt = st.selectbox("Pilih Tindakan / Nama Rak:", opsi_rak, key="rak_action_select")

    if rak_terpilih_mgt == "[+ Tambah Rak Baru]":
        with st.form("tambah_rak_menyatu", clear_on_submit=True):
            t_rak = st.text_input("Nama Rak Baru:").strip()
            if st.form_submit_button("Tambah Rak") and t_rak:
                if t_rak not in st.session_state.rak_gudang_tanpa_posisi:
                    st.session_state.rak_gudang_tanpa_posisi[t_rak] = []
                    save_data_to_sheets()
                    st.success(f"Rak '{t_rak}' ditambahkan!")
                    st.rerun()
                else:
                    st.error("Nama rak sudah ada.")
    else:
        nama_rak_baru = st.text_input(f"Ubah Nama '{rak_terpilih_mgt}' Menjadi:", key="edit_rak_name_input").strip()
        c_r1, c_r2 = st.columns(2)
        with c_r1:
            if st.button("Ubah Nama Rak") and nama_rak_baru:
                if nama_rak_baru not in st.session_state.rak_gudang_tanpa_posisi:
                    st.session_state.rak_gudang_tanpa_posisi[nama_rak_baru] = st.session_state.rak_gudang_tanpa_posisi.pop(rak_terpilih_mgt)
                    save_data_to_sheets()
                    st.success("Nama rak diubah!")
                    st.rerun()
                else:
                    st.error("Nama rak sudah ada.")
        with c_r2:
            if st.button(f"🗑️ Hapus {rak_terpilih_mgt}"):
                st.session_state.rak_gudang_tanpa_posisi.pop(rak_terpilih_mgt)
                save_data_to_sheets()
                st.warning(f"'{rak_terpilih_mgt}' dihapus!")
                st.rerun()

def ui_pencarian_visual():
    st.markdown("### 🔍 Pencarian Barang")
    search_query = st.text_input("Masukkan Kode SKU:", placeholder="Contoh: ketik 'mj' atau '459'...", key="main_search_input").strip()

    if search_query:
        hasil_cari = []
        for nama_rak, daftar_item in st.session_state.rak_gudang_tanpa_posisi.items():
            for item in daftar_item:
                if search_query.lower() in item["sku"].lower():
                    hasil_cari.append({"rak": nama_rak, "sku_penuh": item["sku"], "stok": item["stok"]})

        if hasil_cari:
            st.success(f"📌 Ditemukan {len(hasil_cari)} kecocokan:")
            for hasil in hasil_cari:
                st.info(f"📦 SKU: **`{hasil['sku_penuh']}`** 📍 Rak: **{hasil['rak']}** (Stok: {hasil['stok']})")
        else:
            st.error(f"❌ Tidak ada SKU '{search_query}' di rak manapun.")

    st.markdown("---")
    st.markdown("### 📊 Visualisasi Isi Rak")
    if not st.session_state.rak_gudang_tanpa_posisi:
        st.info("Belum ada rak yang terdaftar.")
    else:
        for r_nama, daftar_item in st.session_state.rak_gudang_tanpa_posisi.items():
            st.markdown(f"#### 📁 {r_nama}")
            if not daftar_item:
                st.error("⬜ *RAK KOSONG*")
            else:
                cols = st.columns(min(len(daftar_item), 4) if len(daftar_item) > 0 else 1)
                for idx, item in enumerate(daftar_item):
                    with cols[idx % 4]:
                        st.info(f"📦 **`{item['sku']}`**\n\n🔢 Stok: {item['stok']}")

def ui_input_mutasi():
    st.markdown("### 📝 Input / Update ke Rak")
    with st.form("form_edit_slot"):
        edit_sku = st.text_input("Masukkan Kode SKU:").strip()
        edit_stok_raw = st.text_input("Jumlah Stok:").strip()
        edit_rak = st.text_input("Ketik Nama Rak Tujuan:").strip()

        c_b1, c_b2 = st.columns(2)
        with c_b1:
            btn_simpan = st.form_submit_button("Simpan ke Rak")
        with c_b2:
            btn_hapus = st.form_submit_button("Hapus SKU")

        if btn_simpan and edit_sku:
            if not edit_stok_raw.isdigit():
                st.error("❌ Stok harus angka!")
            elif edit_rak not in st.session_state.rak_gudang_tanpa_posisi:
                st.error(f"❌ Rak '{edit_rak}' tidak terdaftar.")
            else:
                edit_stok = int(edit_stok_raw)
                rak_items = st.session_state.rak_gudang_tanpa_posisi[edit_rak]
                found = False
                for item in rak_items:
                    if item["sku"].lower() == edit_sku.lower():
                        item["stok"] = edit_stok
                        found = True
                        break
                if not found:
                    rak_items.append({"sku": edit_sku, "stok": edit_stok})
                save_data_to_sheets()
                st.success(f"Disimpan di '{edit_rak}'.")
                st.rerun()

        if btn_hapus and edit_sku:
            if edit_rak in st.session_state.rak_gudang_tanpa_posisi:
                st.session_state.rak_gudang_tanpa_posisi[edit_rak] = [
                    item for item in st.session_state.rak_gudang_tanpa_posisi[edit_rak]
                    if item["sku"].lower() != edit_sku.lower()
                ]
                save_data_to_sheets()
                st.warning(f"SKU '{edit_sku}' dihapus dari '{edit_rak}'!")
                st.rerun()
            else:
                st.error(f"❌ Rak '{edit_rak}' tidak ditemukan.")

    st.markdown("---")
    st.markdown("### 📤 Ambil Barang (Kurangi Stok)")
    with st.form("form_ambil_barang"):
        ambil_sku = st.text_input("Ketik Kode SKU yang Diambil:").strip()
        ambil_jumlah_raw = st.text_input("Jumlah yang Diambil:").strip()
        ambil_rak = st.text_input("Ketik Nama Rak Asal:").strip()

        if st.form_submit_button("Proses Ambil Barang") and ambil_sku:
            if not ambil_jumlah_raw.isdigit():
                st.error("❌ Jumlah ambil harus angka!")
            elif ambil_rak not in st.session_state.rak_gudang_tanpa_posisi:
                st.error(f"❌ Rak '{ambil_rak}' tidak ditemukan.")
            else:
                jumlah_ambil = int(ambil_jumlah_raw)
                rak_items = st.session_state.rak_gudang_tanpa_posisi[ambil_rak]
                item_ditemukan = None
                for item in rak_items:
                    if item["sku"].lower() == ambil_sku.lower():
                        item_ditemukan = item
                        break
                if item_ditemukan:
                    stok_sekarang = item_ditemukan["stok"]
                    if jumlah_ambil >= stok_sekarang:
                        rak_items.remove(item_ditemukan)
                        save_data_to_sheets()
                        st.warning(f"⚠️ Stok habis! '{ambil_sku}' dihapus.")
                        st.rerun()
                    else:
                        item_ditemukan["stok"] -= jumlah_ambil
                        save_data_to_sheets()
                        st.success(f"Berhasil ambil {jumlah_ambil} pcs.")
                        st.rerun()
                else:
                    st.error(f"❌ SKU tidak ditemukan.")

    st.markdown("---")
    st.markdown("### 🔄 Mutasi (Pindah Rak)")
    with st.form("form_mutasi_direct"):
        mutasi_sku = st.text_input("Kode SKU yang Dipindah:").strip()
        mutasi_asal = st.text_input("Nama Rak Asal:").strip()
        tujuan_rak = st.text_input("Nama Rak Tujuan:").strip()

        if st.form_submit_button("Pindah Rak"):
            if mutasi_asal not in st.session_state.rak_gudang_tanpa_posisi or tujuan_rak not in st.session_state.rak_gudang_tanpa_posisi:
                st.error("❌ Rak Asal / Tujuan tidak valid.")
            elif mutasi_asal == tujuan_rak:
                st.error("❌ Rak tujuan tidak boleh sama.")
            else:
                rak_asal_items = st.session_state.rak_gudang_tanpa_posisi[mutasi_asal]
                item_ditemukan = next((item for item in rak_asal_items if item["sku"] == mutasi_sku), None)
                if item_ditemukan:
                    stok_yang_ikut = item_ditemukan["stok"]
                    rak_asal_items.remove(item_ditemukan)
                    st.session_state.rak_gudang_tanpa_posisi[tujuan_rak].append({"sku": mutasi_sku, "stok": stok_yang_ikut})
                    save_data_to_sheets()
                    st.success(f"Dipindah ke '{tujuan_rak}'.")
                    st.rerun()
                else:
                    st.error(f"❌ SKU tidak ditemukan di '{mutasi_asal}'.")

# ==================== RENDER APLIKASI UTAMA ====================

st.markdown("<h1 style='text-align: center;'>📦 Sistem Manajemen Rak Gudang</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; font-size: 16px; font-style: italic; margin-bottom: 0px;'>\"Dibalik Bisnis Yang Besar, Ada Manajemen Yang Teratur\"</p>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; font-size: 12px; color: gray; margin-top: 2px;'>By. Egi</p>", unsafe_allow_html=True)

# Tombol Pintar untuk memilih layar (Data akan tersimpan walau layar direfresh)
mode_tampilan = st.radio(
    "Pilih Tampilan Layar (Sesuaikan dengan perangkat Anda):",
    ["💻 Mode Komputer (3 Kolom)", "📱 Mode HP (Tab Menu)"],
    horizontal=True,
    key="penyimpanan_mode_layar"
)
st.divider()

if mode_tampilan == "💻 Mode Komputer (3 Kolom)":
    # Tampilan Komputer: 3 Kolom sejajar
    col_kiri, col_tengah, col_kanan = st.columns([1.2, 2.0, 1.3], gap="large")
    with col_kiri:
        ui_manajemen_rak()
    with col_tengah:
        ui_pencarian_visual()
    with col_kanan:
        ui_input_mutasi()
else:
    # Tampilan HP: 3 Tab Menu yang ringkas
    tab1, tab2, tab3 = st.tabs(["🛠️ Kelola Rak", "🔍 Cari Barang", "📝 Update & Mutasi"])
    with tab1:
        ui_manajemen_rak()
    with tab2:
        ui_pencarian_visual()
    with tab3:
        ui_input_mutasi()
