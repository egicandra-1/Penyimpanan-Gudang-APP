from google.oauth2.service_account import Credentials
import gspread
import streamlit as st
import json
import streamlit.components.v1 as components

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

if "mode_aplikasi" not in st.session_state:
    st.session_state.mode_aplikasi = None


# --- FUNGSI JAVASCRIPT AGAR KURSOR OTOMATIS FOKUS TANPA KLIK ---
def auto_focus_input_trick():
    js_code = """
    <script>
    setTimeout(function() {
        const doc = window.parent.document;
        const inputs = doc.querySelectorAll('input[type="text"]');
        if (inputs.length > 0) {
            // Ambil kotak input aktif terakhir di layar
            const targetInput = inputs[inputs.length - 1];
            targetInput.focus();
            targetInput.click();
        }
    }, 100);
    </script>
    """
    components.html(js_code, height=0, width=0)


# ==================== FUNGSI TAMPILAN (UI) ====================

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

def ui_input_barang(prefix_key=""):
    st.markdown("### 📝 Input / Update ke Rak")
    
    if f"step_{prefix_key}" not in st.session_state:
        st.session_state[f"step_{prefix_key}"] = 1
        st.session_state[f"val_sku_{prefix_key}"] = ""
        st.session_state[f"val_stok_{prefix_key}"] = ""
        st.session_state[f"val_rak_{prefix_key}"] = ""

    current_step = st.session_state[f"step_{prefix_key}"]

    if current_step == 1:
        with st.form(f"form_sku_{prefix_key}"):
            sku_input = st.text_input("1️⃣ Masukkan / Scan Kode SKU:", value=st.session_state[f"val_sku_{prefix_key}"], placeholder="Ketik atau scan SKU lalu Enter...").strip()
            submitted_sku = st.form_submit_button("Lanjut ke Stok ➡️")
            
            if submitted_sku and sku_input:
                st.session_state[f"val_sku_{prefix_key}"] = sku_input
                st.session_state[f"step_{prefix_key}"] = 2
                st.rerun()

    elif current_step == 2:
        with st.form(f"form_stok_{prefix_key}"):
            st.info(f"📌 SKU Terpilih: **`{st.session_state[f'val_sku_{prefix_key}']}`**")
            stok_input = st.text_input("2️⃣ Masukkan Jumlah Stok:", value=st.session_state[f"val_stok_{prefix_key}"], placeholder="Contoh: 500 lalu Enter...").strip()
            c_s1, c_s2 = st.columns(2)
            with c_s1:
                submitted_stok = st.form_submit_button("Lanjut ke Rak ➡️")
            with c_s2:
                btn_reset = st.form_submit_button("🔄 Reset / Ganti SKU")
            
            if btn_reset:
                st.session_state[f"step_{prefix_key}"] = 1
                st.session_state[f"val_sku_{prefix_key}"] = ""
                st.session_state[f"val_stok_{prefix_key}"] = ""
                st.session_state[f"val_rak_{prefix_key}"] = ""
                st.rerun()

            if submitted_stok:
                if not stok_input.isdigit():
                    st.error("❌ Jumlah stok harus berupa angka!")
                else:
                    st.session_state[f"val_stok_{prefix_key}"] = stok_input
                    st.session_state[f"step_{prefix_key}"] = 3
                    st.rerun()

    elif current_step == 3:
        with st.form(f"form_rak_{prefix_key}"):
            st.info(f"📌 SKU: **`{st.session_state[f'val_sku_{prefix_key}']}`** | Stok: **{st.session_state[f'val_stok_{prefix_key}']}**")
            rak_input = st.text_input("3️⃣ Ketik Nama Rak Tujuan:", value=st.session_state[f'val_rak_{prefix_key}'], placeholder="Contoh: Rak A1...").strip()
            
            c_r1, c_r2 = st.columns(2)
            with c_r1:
                btn_konfirmasi = st.form_submit_button("Konfirmasi Input SKU", type="primary")
            with c_r2:
                btn_back = st.form_submit_button("⬅️ Kembali ke Stok")

            if btn_back:
                st.session_state[f"step_{prefix_key}"] = 2
                st.rerun()

            if btn_konfirmasi and rak_input:
                sku_val = st.session_state[f"val_sku_{prefix_key}"]
                stok_val = int(st.session_state[f"val_stok_{prefix_key}"])
                
                if rak_input not in st.session_state.rak_gudang_tanpa_posisi:
                    st.error(f"❌ Rak '{rak_input}' tidak terdaftar di sistem!")
                else:
                    rak_items = st.session_state.rak_gudang_tanpa_posisi[rak_input]
                    found = False
                    for item in rak_items:
                        if item["sku"].lower() == sku_val.lower():
                            item["stok"] = stok_val
                            found = True
                            break
                    if not found:
                        rak_items.append({"sku": sku_val, "stok": stok_val})
                    
                    save_data_to_sheets()
                    
                    st.session_state[f"step_{prefix_key}"] = 1
                    st.session_state[f"val_sku_{prefix_key}"] = ""
                    st.session_state[f"val_stok_{prefix_key}"] = ""
                    st.session_state[f"val_rak_{prefix_key}"] = ""
                    
                    st.success(f"🎉 Berhasil! SKU '{sku_val}' (Stok: {stok_val}) tersimpan di '{rak_input}'.")
                    st.rerun()

    with st.expander("🗑️ Hapus SKU dari Rak"):
        with st.form(f"form_hapus_sku_{prefix_key}"):
            h_sku = st.text_input("Kode SKU yang akan dihapus:").strip()
            h_rak = st.text_input("Nama Rak asal SKU tersebut:").strip()
            if st.form_submit_button("Hapus SKU Ini") and h_sku and h_rak:
                if h_rak in st.session_state.rak_gudang_tanpa_posisi:
                    st.session_state.rak_gudang_tanpa_posisi[h_rak] = [
                        item for item in st.session_state.rak_gudang_tanpa_posisi[h_rak]
                        if item["sku"].lower() != h_sku.lower()
                    ]
                    save_data_to_sheets()
                    st.warning(f"⚠️ SKU '{h_sku}' berhasil dihapus dari '{h_rak}'!")
                    st.rerun()
                else:
                    st.error(f"❌ Rak '{h_rak}' tidak ditemukan.")

    auto_focus_input_trick()

def ui_ambil_barang(prefix_key=""):
    st.markdown("### 📤 Ambil Barang (Kurangi Stok)")
    
    if f"step_ambil_{prefix_key}" not in st.session_state:
        st.session_state[f"step_ambil_{prefix_key}"] = 1
        st.session_state[f"val_ambil_sku_{prefix_key}"] = ""
        st.session_state[f"val_ambil_stok_{prefix_key}"] = ""
        st.session_state[f"val_ambil_rak_{prefix_key}"] = ""

    current_step = st.session_state[f"step_ambil_{prefix_key}"]

    if current_step == 1:
        with st.form(f"form_ambil_sku_{prefix_key}"):
            sku_input = st.text_input("1️⃣ Ketik Kode SKU yang Diambil:", value=st.session_state[f"val_ambil_sku_{prefix_key}"], placeholder="Ketik atau scan SKU lalu Enter...").strip()
            submitted_sku = st.form_submit_button("Lanjut ke Jumlah ➡️")
            
            if submitted_sku and sku_input:
                st.session_state[f"val_ambil_sku_{prefix_key}"] = sku_input
                st.session_state[f"val_ambil_stok_{prefix_key}"] = ""
                st.session_state[f"step_ambil_{prefix_key}"] = 2
                st.rerun()

    elif current_step == 2:
        with st.form(f"form_ambil_stok_{prefix_key}"):
            st.info(f"📌 SKU Terpilih: **`{st.session_state[f'val_ambil_sku_{prefix_key}']}`**")
            stok_input = st.text_input("2️⃣ Jumlah yang Diambil:", value=st.session_state[f"val_ambil_stok_{prefix_key}"], placeholder="Ketik angka atau biarkan kosong untuk scan +1...").strip()
            c_s1, c_s2 = st.columns(2)
            with c_s1:
                submitted_stok = st.form_submit_button("Lanjut ke Rak Asal ➡️")
            with c_s2:
                btn_reset = st.form_submit_button("🔄 Reset / Ganti SKU")
            
            if btn_reset:
                st.session_state[f"step_ambil_{prefix_key}"] = 1
                st.session_state[f"val_ambil_sku_{prefix_key}"] = ""
                st.session_state[f"val_ambil_stok_{prefix_key}"] = ""
                st.session_state[f"val_ambil_rak_{prefix_key}"] = ""
                st.rerun()

            if submitted_stok:
                if not stok_input:
                    current_count = int(st.session_state.get(f"count_scan_{prefix_key}", 0)) + 1
                    st.session_state[f"count_scan_{prefix_key}"] = current_count
                    st.session_state[f"val_ambil_stok_{prefix_key}"] = str(current_count)
                    st.session_state[f"step_ambil_{prefix_key}"] = 3
                    st.rerun()
                elif not stok_input.isdigit():
                    st.error("❌ Jumlah ambil harus berupa angka!")
                else:
                    st.session_state[f"count_scan_{prefix_key}"] = int(stok_input)
                    st.session_state[f"val_ambil_stok_{prefix_key}"] = stok_input
                    st.session_state[f"step_ambil_{prefix_key}"] = 3
                    st.rerun()

    elif current_step == 3:
        with st.form(f"form_ambil_rak_{prefix_key}"):
            st.info(f"📌 SKU: **`{st.session_state[f'val_ambil_sku_{prefix_key}']}`** | Jumlah Ambil: **{st.session_state[f'val_ambil_stok_{prefix_key}']}**")
            rak_input = st.text_input("3️⃣ Ketik Nama Rak Asal:", value=st.session_state[f'val_ambil_rak_{prefix_key}'], placeholder="Contoh: Rak A1...").strip()
            
            c_r1, c_r2 = st.columns(2)
            with c_r1:
                btn_konfirmasi = st.form_submit_button("Konfirmasi Ambil Barang", type="primary")
            with c_r2:
                btn_back = st.form_submit_button("⬅️ Kembali ke Jumlah")

            if btn_back:
                st.session_state[f"step_ambil_{prefix_key}"] = 2
                st.rerun()

            if btn_konfirmasi and rak_input:
                sku_val = st.session_state[f"val_ambil_sku_{prefix_key}"]
                jumlah_ambil = int(st.session_state[f"val_ambil_stok_{prefix_key}"])
                
                if rak_input not in st.session_state.rak_gudang_tanpa_posisi:
                    st.error(f"❌ Rak '{rak_input}' tidak ditemukan.")
                else:
                    rak_items = st.session_state.rak_gudang_tanpa_posisi[rak_input]
                    item_ditemukan = None
                    for item in rak_items:
                        if item["sku"].lower() == sku_val.lower():
                            item_ditemukan = item
                            break
                    
                    if item_ditemukan:
                        stok_sekarang = item_ditemukan["stok"]
                        if jumlah_ambil >= stok_sekarang:
                            rak_items.remove(item_ditemukan)
                            save_data_to_sheets()
                            st.warning(f"⚠️ Stok habis! '{sku_val}' dihapus dari rak '{rak_input}'.")
                        else:
                            item_ditemukan["stok"] -= jumlah_ambil
                            save_data_to_sheets()
                            st.success(f"🎉 Berhasil! Mengambil {jumlah_ambil} pcs SKU '{sku_val}' dari rak '{rak_input}'.")
                        
                        st.session_state[f"step_ambil_{prefix_key}"] = 1
                        st.session_state[f"val_ambil_sku_{prefix_key}"] = ""
                        st.session_state[f"val_ambil_stok_{prefix_key}"] = ""
                        st.session_state[f"val_ambil_rak_{prefix_key}"] = ""
                        st.session_state[f"count_scan_{prefix_key}"] = 0
                        st.rerun()
                    else:
                        st.error(f"❌ SKU '{sku_val}' tidak ditemukan di rak '{rak_input}'.")

    auto_focus_input_trick()

def ui_mutasi_barang(prefix_key=""):
    st.markdown("### 🔄 Mutasi (Pindah Rak)")
    
    if f"step_mutasi_{prefix_key}" not in st.session_state:
        st.session_state[f"step_mutasi_{prefix_key}"] = 1
        st.session_state[f"val_mutasi_sku_{prefix_key}"] = ""
        st.session_state[f"val_mutasi_asal_{prefix_key}"] = ""
        st.session_state[f"val_mutasi_tujuan_{prefix_key}"] = ""

    current_step = st.session_state[f"step_mutasi_{prefix_key}"]

    if current_step == 1:
        with st.form(f"form_mutasi_sku_{prefix_key}"):
            sku_input = st.text_input("1️⃣ Kode SKU yang Dipindah:", value=st.session_state[f"val_mutasi_sku_{prefix_key}"], placeholder="Ketik atau scan SKU lalu Enter...").strip()
            submitted_sku = st.form_submit_button("Lanjut ke Rak Asal ➡️")
            
            if submitted_sku and sku_input:
                st.session_state[f"val_mutasi_sku_{prefix_key}"] = sku_input
                st.session_state[f"step_mutasi_{prefix_key}"] = 2
                st.rerun()

    elif current_step == 2:
        with st.form(f"form_mutasi_asal_{prefix_key}"):
            st.info(f"📌 SKU Dipindah: **`{st.session_state[f'val_mutasi_sku_{prefix_key}']}`**")
            asal_input = st.text_input("2️⃣ Nama Rak Asal:", value=st.session_state[f"val_mutasi_asal_{prefix_key}"], placeholder="Ketik atau scan Rak Asal lalu Enter...").strip()
            c_m1, c_m2 = st.columns(2)
            with c_m1:
                submitted_asal = st.form_submit_button("Lanjut ke Rak Tujuan ➡️")
            with c_m2:
                btn_reset = st.form_submit_button("🔄 Reset / Ganti SKU")
            
            if btn_reset:
                st.session_state[f"step_mutasi_{prefix_key}"] = 1
                st.session_state[f"val_mutasi_sku_{prefix_key}"] = ""
                st.session_state[f"val_mutasi_asal_{prefix_key}"] = ""
                st.session_state[f"val_mutasi_tujuan_{prefix_key}"] = ""
                st.rerun()

            if submitted_asal and asal_input:
                st.session_state[f"val_mutasi_asal_{prefix_key}"] = asal_input
                st.session_state[f"step_mutasi_{prefix_key}"] = 3
                st.rerun()

    elif current_step == 3:
        with st.form(f"form_mutasi_tujuan_{prefix_key}"):
            st.info(f"📌 SKU: **`{st.session_state[f'val_mutasi_sku_{prefix_key}']}`** | Dari Rak: **{st.session_state[f'val_mutasi_asal_{prefix_key}']}**")
            tujuan_input = st.text_input("3️⃣ Nama Rak Tujuan:", value=st.session_state[f'val_mutasi_tujuan_{prefix_key}'], placeholder="Ketik atau scan Rak Tujuan...").strip()
            
            c_r1, c_r2 = st.columns(2)
            with c_r1:
                btn_konfirmasi = st.form_submit_button("Konfirmasi Mutasi SKU", type="primary")
            with c_r2:
                btn_back = st.form_submit_button("⬅️ Kembali ke Rak Asal")

            if btn_back:
                st.session_state[f"step_mutasi_{prefix_key}"] = 2
                st.rerun()

            if btn_konfirmasi and tujuan_input:
                sku_val = st.session_state[f"val_mutasi_sku_{prefix_key}"]
                asal_val = st.session_state[f"val_mutasi_asal_{prefix_key}"]
                tujuan_val = tujuan_input
                
                if asal_val not in st.session_state.rak_gudang_tanpa_posisi or tujuan_val not in st.session_state.rak_gudang_tanpa_posisi:
                    st.error("❌ Rak Asal atau Rak Tujuan tidak terdaftar di sistem!")
                elif asal_val == tujuan_val:
                    st.error("❌ Rak tujuan tidak boleh sama dengan rak asal.")
                else:
                    rak_asal_items = st.session_state.rak_gudang_tanpa_posisi[asal_val]
                    item_ditemukan = next((item for item in rak_asal_items if item["sku"].lower() == sku_val.lower()), None)
                    
                    if item_ditemukan:
                        stok_yang_ikut = item_ditemukan["stok"]
                        rak_asal_items.remove(item_ditemukan)
                        st.session_state.rak_gudang_tanpa_posisi[tujuan_val].append({"sku": sku_val, "stok": stok_yang_ikut})
                        save_data_to_sheets()
                        
                        st.session_state[f"step_mutasi_{prefix_key}"] = 1
                        st.session_state[f"val_mutasi_sku_{prefix_key}"] = ""
                        st.session_state[f"val_mutasi_asal_{prefix_key}"] = ""
                        st.session_state[f"val_mutasi_tujuan_{prefix_key}"] = ""
                        
                        st.success(f"🎉 Berhasil! SKU '{sku_val}' dipindah dari '{asal_val}' ke '{tujuan_val}'.")
                        st.rerun()
                    else:
                        st.error(f"❌ SKU '{sku_val}' tidak ditemukan di rak '{asal_val}'.")

    auto_focus_input_trick()


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
            ui_input_barang(prefix_key="pc")
            st.markdown("---")
            ui_ambil_barang(prefix_key="pc")
            st.markdown("---")
            ui_mutasi_barang(prefix_key="pc")
    else:
        tab1, tab2, tab3, tab4, tab5 = st.tabs(["🗄️ Rak", "🔍 Cari", "📝 Input", "📤 Ambil", "🔄 Mutasi"])
        
        with tab1:
            ui_manajemen_rak()
        with tab2:
            ui_pencarian_visual()
        with tab3:
            ui_input_barang(prefix_key="hp")
        with tab4:
            ui_ambil_barang(prefix_key="hp")
        with tab5:
            ui_mutasi_barang(prefix_key="hp")
