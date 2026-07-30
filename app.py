from google.oauth2.service_account import Credentials
import gspread
import streamlit as st
import json

st.set_page_config(page_title="Sistem Manajemen Rak Gudang", page_icon="📦", layout="wide")

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

if "mode_aplikasi" not in st.session_state:
    st.session_state.mode_aplikasi = None


# ==================== FUNGSI TAMPILAN (UI) ====================

def ui_manajemen_rak():
    st.markdown("### 🛠️ Manajemen Struktur")
    
    if "pesan_sukses_rak" not in st.session_state:
        st.session_state.pesan_sukses_rak = ""
        
    if st.session_state.pesan_sukses_rak:
        st.success(st.session_state.pesan_sukses_rak)
        st.session_state.pesan_sukses_rak = "" 

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
                    st.session_state.pesan_sukses_rak = f"Rak '{t_rak}' berhasil ditambahkan!"
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
                    st.session_state.pesan_sukses_rak = f"Nama rak berhasil diubah menjadi '{nama_rak_baru}'!"
                    st.rerun()
                else:
                    st.error("Nama rak sudah ada.")
        with c_r2:
            if st.button(f"🗑️ Hapus {rak_terpilih_mgt}"):
                st.session_state.rak_gudang_tanpa_posisi.pop(rak_terpilih_mgt)
                save_data_to_sheets()
                st.session_state.pesan_sukses_rak = f"Rak '{rak_terpilih_mgt}' berhasil dihapus!"
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

def ui_input_barang():
    st.markdown("### 📝 Input / Update ke Rak")
    
    if "error_input_pesan" not in st.session_state:
        st.session_state.error_input_pesan = ""

    if st.session_state.error_input_pesan:
        st.error(st.session_state.error_input_pesan)
        st.session_state.error_input_pesan = ""

    edit_sku = st.text_input("Masukkan Kode SKU:", key="input_sku_field").strip()
    edit_stok_raw = st.text_input("Jumlah Stok:", key="input_stok_field").strip()
    edit_rak = st.text_input("Ketik Nama Rak Tujuan:", key="input_rak_field").strip()

    c_b1, c_b2 = st.columns(2)
    with c_b1:
        btn_simpan = st.button("Simpan ke Rak", use_container_width=True)
    with c_b2:
        btn_hapus = st.button("Hapus SKU", use_container_width=True)

    if btn_simpan:
        if not edit_sku:
            st.session_state.error_input_pesan = "❌ Kode SKU harus diisi!"
            st.rerun()
        elif not edit_stok_raw.isdigit():
            st.session_state.error_input_pesan = "❌ Stok harus angka!"
            st.rerun()
        elif edit_rak not in st.session_state.rak_gudang_tanpa_posisi:
            st.session_state.error_input_pesan = f"❌ Rak '{edit_rak}' tidak terdaftar."
            st.rerun()
        else:
            edit_stok = int(edit_stok_raw)
            rak_items = st.session_state.rak_gudang_tanpa_posisi[edit_rak]
            rak_items.append({"sku": edit_sku, "stok": edit_stok})
            save_data_to_sheets()
            st.success(f"SKU '{edit_sku}' (Stok: {edit_stok}) berhasil ditambahkan ke '{edit_rak}'.")
            st.rerun()

    if btn_hapus:
        if not edit_sku:
            st.session_state.error_input_pesan = "❌ Masukkan Kode SKU yang ingin dihapus!"
            st.rerun()
        elif edit_rak in st.session_state.rak_gudang_tanpa_posisi:
            rak_lama = st.session_state.rak_gudang_tanpa_posisi[edit_rak]
            filtered_rak = [item for item in rak_lama if item["sku"].lower() != edit_sku.lower()]
            if len(filtered_rak) < len(rak_lama):
                st.session_state.rak_gudang_tanpa_posisi[edit_rak] = filtered_rak
                save_data_to_sheets()
                st.warning(f"SKU '{edit_sku}' dihapus dari '{edit_rak}'!")
                st.rerun()
            else:
                st.session_state.error_input_pesan = f"❌ SKU '{edit_sku}' tidak ditemukan di rak '{edit_rak}'."
                st.rerun()
        else:
            st.session_state.error_input_pesan = f"❌ Rak '{edit_rak}' tidak ditemukan."
            st.rerun()

def ui_ambil_barang():
    st.markdown("### 📤 Pengurangan Stok (Deteksi Otomatis)")

    if "scan_cart" not in st.session_state:
        st.session_state.scan_cart = {} 
    if "error_ambil_pesan" not in st.session_state:
        st.session_state.error_ambil_pesan = ""
    if "success_ambil_pesan" not in st.session_state:
        st.session_state.success_ambil_pesan = ""

    if st.session_state.error_ambil_pesan:
        st.error(st.session_state.error_ambil_pesan)
        st.session_state.error_ambil_pesan = ""

    if st.session_state.success_ambil_pesan:
        st.success(st.session_state.success_ambil_pesan)
        st.session_state.success_ambil_pesan = ""

    ambil_rak = st.text_input("Ketik Nama Rak Asal:", key="ambil_rak_field").strip()

    def process_scanned_sku():
        raw_val = st.session_state.quick_scan_input.strip()
        if not raw_val:
            return

        rak_terpilih = st.session_state.ambil_rak_field.strip()
        
        if not rak_terpilih:
            st.session_state.error_ambil_pesan = "❌ Ketik Nama Rak Asal terlebih dahulu sebelum scan!"
            st.session_state.quick_scan_input = ""
            return
            
        if rak_terpilih not in st.session_state.rak_gudang_tanpa_posisi:
            st.session_state.error_ambil_pesan = f"❌ Rak '{rak_terpilih}' tidak ditemukan!"
            st.session_state.quick_scan_input = ""
            return

        sku_terdeteksi = None
        daftar_sku_rak = [item["sku"] for item in st.session_state.rak_gudang_tanpa_posisi[rak_terpilih]]
        
        for real_sku in daftar_sku_rak:
            if real_sku.lower() in raw_val.lower():
                sku_terdeteksi = real_sku
                break
        
        if not sku_terdeteksi:
            sku_salah = raw_val.split()[0] if " " in raw_val else raw_val[:10]
            st.session_state.error_ambil_pesan = f"❌ DITOLAK! SKU '{sku_salah}' tidak ada di rak '{rak_terpilih}'!"
            st.session_state.quick_scan_input = ""
            return

        st.session_state.error_ambil_pesan = ""

        jumlah_scan = 1
        if sku_terdeteksi.lower() in raw_val.lower():
            hitung_kemunculan = raw_val.lower().count(sku_terdeteksi.lower())
            if hitung_kemunculan > 0:
                jumlah_scan = hitung_kemunculan

        if sku_terdeteksi in st.session_state.scan_cart:
            st.session_state.scan_cart[sku_terdeteksi] += jumlah_scan
        else:
            st.session_state.scan_cart[sku_terdeteksi] = jumlah_scan
            
        st.session_state[f"qty_num_{sku_terdeteksi}"] = st.session_state.scan_cart[sku_terdeteksi]
        
        st.session_state.quick_scan_input = ""

    st.text_input(
        "Scan Kode SKU (Otomatis mendeteksi SKU & menambah jumlah):", 
        key="quick_scan_input", 
        on_change=process_scanned_sku,
        placeholder="Arahkan scanner ke barcode..."
    )

    if st.session_state.scan_cart:
        st.markdown("#### 🛒 Daftar Barang yang Akan Dikurangi:")
        total_items = 0
        for sku_item, qty in list(st.session_state.scan_cart.items()):
            col1, col2, col3 = st.columns([2, 2, 1])
            with col1:
                st.write(f"📦 **{sku_item}**")
            with col2:
                new_qty = st.number_input(
                    f"Jumlah {sku_item}", 
                    min_value=1, 
                    key=f"qty_num_{sku_item}", 
                    label_visibility="collapsed"
                )
                st.session_state.scan_cart[sku_item] = new_qty
            with col3:
                if st.button("❌", key=f"del_{sku_item}"):
                    del st.session_state.scan_cart[sku_item]
                    if f"qty_num_{sku_item}" in st.session_state:
                        del st.session_state[f"qty_num_{sku_item}"]
                    st.rerun()
            total_items += st.session_state.scan_cart[sku_item]

        st.markdown(f"**Total Keseluruhan Stok yang Dikurangi:** {total_items} pcs")

        c_b1, c_b2 = st.columns(2)
        with c_b1:
            if st.button("✅ Konfirmasi Pengurangan Stok", use_container_width=True, type="primary"):
                if not ambil_rak:
                    st.session_state.error_ambil_pesan = "❌ Nama Rak Asal harus diisi!"
                    st.rerun()
                elif ambil_rak not in st.session_state.rak_gudang_tanpa_posisi:
                    st.session_state.error_ambil_pesan = f"❌ Rak '{ambil_rak}' tidak terdaftar."
                    st.rerun()
                else:
                    rak_items = st.session_state.rak_gudang_tanpa_posisi[ambil_rak]
                    berhasil = True
                    pesan_hasil = []

                    for sku_to_reduce, qty_to_reduce in st.session_state.scan_cart.items():
                        item_ditemukan = None
                        for item in rak_items:
                            if sku_to_reduce.lower() == item["sku"].lower():
                                item_ditemukan = item
                                break
                        
                        if item_ditemukan:
                            if qty_to_reduce >= item_ditemukan["stok"]:
                                rak_items.remove(item_ditemukan)
                                pesan_hasil.append(f"SKU '{item_ditemukan['sku']}' habis & dihapus.")
                            else:
                                item_ditemukan["stok"] -= qty_to_reduce
                                pesan_hasil.append(f"SKU '{item_ditemukan['sku']}' dikurangi {qty_to_reduce} pcs.")
                        else:
                            berhasil = False
                            st.session_state.error_ambil_pesan = f"❌ SKU '{sku_to_reduce}' tidak ditemukan di rak '{ambil_rak}'."
                            st.rerun()

                    if berhasil:
                        save_data_to_sheets()
                        st.session_state.success_ambil_pesan = "Berhasil! " + " | ".join(pesan_hasil)
                        for sku_item in list(st.session_state.scan_cart.keys()):
                            if f"qty_num_{sku_item}" in st.session_state:
                                del st.session_state[f"qty_num_{sku_item}"]
                        st.session_state.scan_cart = {}
                        st.rerun()

        with c_b2:
            if st.button("🗑️ Reset Daftar", use_container_width=True):
                for sku_item in list(st.session_state.scan_cart.keys()):
                    if f"qty_num_{sku_item}" in st.session_state:
                        del st.session_state[f"qty_num_{sku_item}"]
                st.session_state.scan_cart = {}
                st.rerun()
    else:
        st.info("💡 Ketik nama rak dulu, lalu scan barcode Anda berulang kali di kotak atas.")

def ui_mutasi_barang():
    st.markdown("### 🔄 Mutasi (Pindah Rak)")
    with st.form("form_mutasi_direct"):
        mutasi_sku = st.text_input("Kode SKU yang Dipindah:").strip()
        
        # TAB TAMBAHAN: Untuk membedakan barang yang kodenya sama persis tapi stoknya beda
        mutasi_jumlah = st.text_input("Jumlah Stok (Ketik angka stok untuk memilih item spesifik, cth: 5):", placeholder="Kosongkan jika hanya ada 1 jenis SKU").strip()
        
        mutasi_asal = st.text_input("Nama Rak Asal:").strip()
        tujuan_rak = st.text_input("Nama Rak Tujuan:").strip()

        if st.form_submit_button("Pindah Rak"):
            if not mutasi_sku or not mutasi_asal or not tujuan_rak:
                st.error("❌ SKU, Rak Asal, dan Rak Tujuan wajib diisi.")
            elif mutasi_asal not in st.session_state.rak_gudang_tanpa_posisi or tujuan_rak not in st.session_state.rak_gudang_tanpa_posisi:
                st.error("❌ Rak Asal / Tujuan tidak valid.")
            elif mutasi_asal == tujuan_rak:
                st.error("❌ Rak tujuan tidak boleh sama.")
            else:
                rak_asal_items = st.session_state.rak_gudang_tanpa_posisi[mutasi_asal]
                item_ditemukan = None
                
                # 1. Cari spesifik berdasarkan angka stok jika diisi (untuk membedakan barang kembar)
                if mutasi_jumlah.isdigit():
                    target_stok = int(mutasi_jumlah)
                    item_ditemukan = next((item for item in rak_asal_items if item["sku"].lower() == mutasi_sku.lower() and item["stok"] == target_stok), None)
                
                # 2. Jika kolom dikosongkan atau tidak ketemu stoknya, cari berdasarkan SKU saja (yang pertama ketemu)
                if not item_ditemukan:
                    item_ditemukan = next((item for item in rak_asal_items if item["sku"].lower() == mutasi_sku.lower()), None)

                if item_ditemukan:
                    stok_yang_ikut = item_ditemukan["stok"]
                    sku_asli = item_ditemukan["sku"]
                    rak_asal_items.remove(item_ditemukan)
                    st.session_state.rak_gudang_tanpa_posisi[tujuan_rak].append({"sku": sku_asli, "stok": stok_yang_ikut})
                    save_data_to_sheets()
                    st.success(f"Berhasil memindah SKU '{sku_asli}' (Stok: {stok_yang_ikut}) ke '{tujuan_rak}'.")
                    st.rerun()
                else:
                    if mutasi_jumlah.isdigit():
                        st.error(f"❌ SKU '{mutasi_sku}' dengan stok '{mutasi_jumlah}' tidak ditemukan di '{mutasi_asal}'.")
                    else:
                        st.error(f"❌ SKU '{mutasi_sku}' tidak ditemukan di '{mutasi_asal}'.")


# ==================== RENDER APLIKASI UTAMA ====================

if st.session_state.mode_aplikasi is None:
    st.markdown("<br><br><h1 style='text-align: center;'>📦 Selamat Datang di Sistem Gudang</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; font-size: 16px; font-style: italic; margin-bottom: 0px;'>\"Dibalik Bisnis Yang Besar, Ada Manajemen Yang Teratur\"</p>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; font-size: 12px; color: gray; margin-top: 2px;'>By. Egi</p>", unsafe_allow_html=True)
    
    st.markdown("<br><h3 style='text-align: center;'>Pilih Perangkat Anda:</h3>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 1.5, 1])
    with col2:
        if st.button("💻 BUKA MODE KOMPUTER", use_container_width=True, type="primary"):
            st.session_state.mode_aplikasi = "komputer"
            st.rerun()
            
        st.write("") 
        
        if st.button("📱 BUKA MODE HP", use_container_width=True, type="primary"):
            st.session_state.mode_aplikasi = "hp"
            st.rerun()

else:
    col_judul, col_tombol = st.columns([4, 1])
    
    with col_judul:
        st.markdown("<h1>📦 Sistem Manajemen Rak Gudang</h1>", unsafe_allow_html=True)
        
    with col_tombol:
        st.write("") 
        if st.button("🔄 Ganti Perangkat", use_container_width=True):
            st.session_state.mode_aplikasi = None
            st.rerun()
            
    st.divider()

    if st.session_state.mode_aplikasi == "komputer":
        col_kiri, col_tengah, col_kanan = st.columns([1.2, 2.0, 1.3], gap="large")
        with col_kiri:
            ui_manajemen_rak()
        with col_tengah:
            ui_pencarian_visual()
        with col_kanan:
            ui_input_barang()
            st.markdown("---")
            ui_ambil_barang()
            st.markdown("---")
            ui_mutasi_barang()
    else:
        tab1, tab2, tab3, tab4, tab5 = st.tabs(["🗄️ Rak", "🔍 Cari", "📝 Input", "📤 Ambil", "🔄 Mutasi"])
        
        with tab1:
            ui_manajemen_rak()
        with tab2:
            ui_pencarian_visual()
        with tab3:
            ui_input_barang()
        with tab4:
            ui_ambil_barang()
        with tab5:
            ui_mutasi_barang()
