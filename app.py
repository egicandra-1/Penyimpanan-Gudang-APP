import time
import threading
import copy
from google.oauth2.service_account import Credentials
import gspread
import streamlit as st
import json
import streamlit.components.v1 as components

st.set_page_config(page_title="Sistem Manajemen Rak Gudang", page_icon="📦", layout="wide")

SCOPE = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

placeholders = {}

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

# ==================== PENYIMPANAN SILUMAN (LOADING NOL DETIK) ====================
save_lock = threading.Lock()

def _background_save(data_dict):
    with save_lock:
        data_rak = [["nama_rak"]]
        data_isi = [["nama_rak", "sku", "stok"]]
        
        for r_nama, daftar_item in data_dict.items():
            data_rak.append([r_nama])
            for item in daftar_item:
                data_isi.append([r_nama, item["sku"], item["stok"]])
                
        max_retries = 2
        for attempt in range(max_retries):
            try:
                sheet_rak.clear()
                sheet_isi.clear()
                try:
                    sheet_rak.update(values=data_rak, range_name="A1")
                    sheet_isi.update(values=data_isi, range_name="A1")
                except TypeError:
                    sheet_rak.update("A1", data_rak)
                    sheet_isi.update("A1", data_isi)
                break
            except Exception:
                if attempt < max_retries - 1:
                    time.sleep(1.0)
                else:
                    pass

def save_data_to_sheets():
    current_data = copy.deepcopy(st.session_state.rak_gudang_tanpa_posisi)
    threading.Thread(target=_background_save, args=(current_data,)).start()

# =================================================================================

if "rak_gudang_tanpa_posisi" not in st.session_state:
    st.session_state.rak_gudang_tanpa_posisi = load_data_from_sheets()

if "mode_aplikasi" not in st.session_state:
    st.session_state.mode_aplikasi = None

if "cari_results" not in st.session_state:
    st.session_state.cari_results = None

if "focus_target" not in st.session_state:
    st.session_state.focus_target = None


# ==================== CALLBACK TAMBAH RAK (KOTAK BAJA / STATIC) ====================
def on_enter_tambah_rak():
    clean_val = st.session_state.input_rak_baru_scan.strip()
    if not clean_val: return
    
    if clean_val not in st.session_state.rak_gudang_tanpa_posisi:
        st.session_state.rak_gudang_tanpa_posisi[clean_val] = []
        save_data_to_sheets()
        st.session_state.global_notif = {"tab": "rak", "type": "success", "text": f"✅ Rak '{clean_val}' berhasil ditambahkan!"}
    else:
        st.session_state.global_notif = {"tab": "rak", "type": "error", "text": f"❌ Rak '{clean_val}' sudah ada."}
        
    st.session_state.input_rak_baru_scan = "" # Bersihkan tanpa merusak kotak DOM
    st.session_state.focus_target = "Nama Rak Baru:"

# ==================== CALLBACK DATABASE RAK ====================
def proses_perubahan_tabel_rak():
    changes = st.session_state.editor_tabel_rak
    rak_sorted = sorted(list(st.session_state.rak_gudang_tanpa_posisi.keys()))
    needs_save = False
    ada_error = False
    
    if changes.get("deleted_rows"):
        for idx in sorted(changes["deleted_rows"], reverse=True):
            if idx < len(rak_sorted):
                old_name = rak_sorted[idx]
                if old_name in st.session_state.rak_gudang_tanpa_posisi:
                    del st.session_state.rak_gudang_tanpa_posisi[old_name]
                    needs_save = True

    if changes.get("edited_rows"):
        for idx, edit_data in changes["edited_rows"].items():
            if "Nama Rak" in edit_data:
                if idx < len(rak_sorted):
                    old_name = rak_sorted[idx]
                    new_name = edit_data["Nama Rak"].strip()
                    if old_name in st.session_state.rak_gudang_tanpa_posisi and new_name and new_name != old_name:
                        if new_name not in st.session_state.rak_gudang_tanpa_posisi:
                            st.session_state.rak_gudang_tanpa_posisi[new_name] = st.session_state.rak_gudang_tanpa_posisi.pop(old_name)
                            needs_save = True
                        else:
                            st.session_state.global_notif = {"tab": "rak", "type": "error", "text": f"❌ Gagal! Nama rak '{new_name}' sudah ada."}
                            ada_error = True

    if changes.get("added_rows"):
        for row in changes["added_rows"]:
            if "Nama Rak" in row and row["Nama Rak"]:
                new_name = row["Nama Rak"].strip()
                if new_name and new_name not in st.session_state.rak_gudang_tanpa_posisi:
                    st.session_state.rak_gudang_tanpa_posisi[new_name] = []
                    needs_save = True

    if needs_save and not ada_error:
        save_data_to_sheets()
        st.session_state.global_notif = {"tab": "rak", "type": "success", "text": "✅ Perubahan pada database rak berhasil disimpan!"}

# ==================== CALLBACK TAB CARI ====================
def proses_cari():
    query = st.session_state.search_input.strip()
    if not query:
        st.session_state.cari_results = None
        return
        
    hasil_cari = []
    for nama_rak, daftar_item in st.session_state.rak_gudang_tanpa_posisi.items():
        rak_cocok = query.lower() in nama_rak.lower()
        for item in daftar_item:
            sku_cocok = query.lower() in item["sku"].lower()
            if rak_cocok or sku_cocok:
                hasil_cari.append({"rak": nama_rak, "sku_penuh": item["sku"], "stok": item["stok"]})
    
    st.session_state.cari_results = {"query": query, "hasil": hasil_cari}
    
    if hasil_cari:
        st.session_state.global_notif = {"tab": "cari", "type": "success", "text": f"📌 Ditemukan {len(hasil_cari)} kecocokan untuk '{query}'"}
    else:
        st.session_state.global_notif = {"tab": "cari", "type": "error", "text": f"❌ Tidak ada hasil untuk '{query}' pada SKU maupun Nama Rak."}
        
    st.session_state.search_input = ""
    st.session_state.focus_target = "Masukkan Kode SKU atau Nama Rak:"

# ==================== CALLBACK TAB INPUT ====================
def on_enter_input_barang():
    sku = st.session_state.input_sku_field.strip()
    stok_raw = st.session_state.input_stok_field.strip()
    rak = st.session_state.input_rak_field.strip()
    
    if not sku and not stok_raw and not rak: return
        
    if not sku or not stok_raw or not rak:
        st.session_state.global_notif = {"tab": "input", "type": "error", "text": "❌ Semua kolom harus diisi!"}
        return
        
    if not stok_raw.isdigit():
        st.session_state.global_notif = {"tab": "input", "type": "error", "text": "❌ Stok harus angka!"}
        return
        
    if rak not in st.session_state.rak_gudang_tanpa_posisi:
        st.session_state.global_notif = {"tab": "input", "type": "error", "text": f"❌ Rak '{rak}' tidak terdaftar."}
        return
        
    stok = int(stok_raw)
    st.session_state.rak_gudang_tanpa_posisi[rak].append({"sku": sku, "stok": stok})
    
    save_data_to_sheets()
    st.session_state.global_notif = {"tab": "input", "type": "success", "text": f"✅ SKU '{sku}' (Stok: {stok}) berhasil ditambahkan ke '{rak}'."}
    
    st.session_state.input_sku_field = ""
    st.session_state.input_stok_field = ""
    st.session_state.input_rak_field = ""
    st.session_state.focus_target = "Masukkan Kode SKU:"

# ==================== CALLBACK TAB HAPUS ====================
def on_enter_hapus_barang():
    sku_clean = st.session_state.hapus_sku_field.strip()
    rak_clean = st.session_state.hapus_rak_field.strip()
    
    if not sku_clean and not rak_clean: return
        
    if not sku_clean or not rak_clean:
        st.session_state.global_notif = {"tab": "hapus", "type": "error", "text": "❌ Kode SKU dan Nama Rak Asal harus diisi!"}
        return
        
    if rak_clean in st.session_state.rak_gudang_tanpa_posisi:
        rak_lama = st.session_state.rak_gudang_tanpa_posisi[rak_clean]
        filtered_rak = [item for item in rak_lama if item["sku"].lower() != sku_clean.lower()]
        if len(filtered_rak) < len(rak_lama):
            st.session_state.rak_gudang_tanpa_posisi[rak_clean] = filtered_rak
            save_data_to_sheets()
            st.session_state.global_notif = {"tab": "hapus", "type": "success", "text": f"✅ SKU '{sku_clean}' dihapus dari '{rak_clean}'!"}
            
            st.session_state.hapus_sku_field = ""
            st.session_state.hapus_rak_field = ""
            st.session_state.focus_target = "Masukkan Kode SKU yang akan dihapus:"
        else:
            st.session_state.global_notif = {"tab": "hapus", "type": "error", "text": f"❌ SKU '{sku_clean}' tidak ditemukan di rak '{rak_clean}'."}
    else:
        st.session_state.global_notif = {"tab": "hapus", "type": "error", "text": f"❌ Rak '{rak_clean}' tidak ditemukan."}

# ==================== CALLBACK TAB AMBIL ====================
def process_scanned_sku():
    raw_val = st.session_state.quick_scan_input.strip()
    if not raw_val: return

    rak_terpilih = st.session_state.ambil_rak_field.strip()
    if not rak_terpilih:
        st.session_state.global_notif = {"tab": "ambil", "type": "error", "text": "❌ Ketik Nama Rak Asal terlebih dahulu sebelum scan!"}
        st.session_state.quick_scan_input = ""
        st.session_state.focus_target = "Ketik Nama Rak Asal:"
        return
        
    if rak_terpilih not in st.session_state.rak_gudang_tanpa_posisi:
        st.session_state.global_notif = {"tab": "ambil", "type": "error", "text": f"❌ Rak '{rak_terpilih}' tidak ditemukan!"}
        st.session_state.quick_scan_input = ""
        st.session_state.focus_target = "Ketik Nama Rak Asal:"
        return

    sku_terdeteksi = None
    daftar_sku_rak = [item["sku"] for item in st.session_state.rak_gudang_tanpa_posisi[rak_terpilih]]
    
    for real_sku in daftar_sku_rak:
        if raw_val.lower().endswith(real_sku.lower()):
            sku_terdeteksi = real_sku
            break
    
    if not sku_terdeteksi:
        for real_sku in daftar_sku_rak:
            if real_sku.lower() in raw_val.lower():
                sku_terdeteksi = real_sku
                break
    
    if not sku_terdeteksi:
        st.session_state.global_notif = {"tab": "ambil", "type": "error", "text": f"❌ DITOLAK! SKU '{raw_val}' tidak dikenali di rak '{rak_terpilih}'!"}
        st.session_state.quick_scan_input = ""
        st.session_state.focus_target = "Scan Kode SKU (Otomatis mendeteksi SKU & menambah jumlah):"
        return

    st.session_state.scan_cart[sku_terdeteksi] = st.session_state.scan_cart.get(sku_terdeteksi, 0) + 1
    st.session_state[f"qty_num_{sku_terdeteksi}"] = st.session_state.scan_cart[sku_terdeteksi]
    
    st.session_state.quick_scan_input = ""
    st.session_state.focus_target = "Scan Kode SKU (Otomatis mendeteksi SKU & menambah jumlah):"

def proses_konfirmasi_ambil():
    ambil_rak = st.session_state.ambil_rak_field.strip()
    if not ambil_rak:
        st.session_state.global_notif = {"tab": "ambil", "type": "error", "text": "❌ Nama Rak Asal harus diisi!"}
        return
        
    if ambil_rak not in st.session_state.rak_gudang_tanpa_posisi:
        st.session_state.global_notif = {"tab": "ambil", "type": "error", "text": f"❌ Rak '{ambil_rak}' tidak terdaftar."}
        return
        
    rak_items = st.session_state.rak_gudang_tanpa_posisi[ambil_rak]
    berhasil = True
    pesan_hasil = []

    for sku_to_reduce, qty_to_reduce in st.session_state.scan_cart.items():
        matching_items_cek = [item for item in rak_items if sku_to_reduce.lower() == item["sku"].lower()]
        item_ditemukan = None
        
        if len(matching_items_cek) > 1:
            target_str = st.session_state.get(f"target_batch_{sku_to_reduce}")
            if target_str:
                target_stok = int(target_str.replace("Stok Asal: ", ""))
                item_ditemukan = next((item for item in matching_items_cek if item["stok"] == target_stok), None)
        elif len(matching_items_cek) == 1:
            item_ditemukan = matching_items_cek[0]
        
        if item_ditemukan:
            if qty_to_reduce > item_ditemukan["stok"]:
                st.session_state.global_notif = {"tab": "ambil", "type": "error", "text": f"❌ Gagal! Stok '{sku_to_reduce}' tidak cukup."}
                berhasil = False
                break
            elif qty_to_reduce == item_ditemukan["stok"]:
                rak_items.remove(item_ditemukan)
                pesan_hasil.append(f"SKU '{item_ditemukan['sku']}' habis.")
            else:
                item_ditemukan["stok"] -= qty_to_reduce
                pesan_hasil.append(f"SKU '{item_ditemukan['sku']}' dikurangi {qty_to_reduce} pcs.")
        else:
            berhasil = False
            st.session_state.global_notif = {"tab": "ambil", "type": "error", "text": f"❌ SKU '{sku_to_reduce}' tidak ada di rak."}
            break

    if berhasil:
        save_data_to_sheets()
        st.session_state.global_notif = {"tab": "ambil", "type": "success", "text": "Berhasil! " + " | ".join(pesan_hasil)}
        for sku_item in list(st.session_state.scan_cart.keys()):
            if f"qty_num_{sku_item}" in st.session_state: del st.session_state[f"qty_num_{sku_item}"]
            if f"target_batch_{sku_item}" in st.session_state: del st.session_state[f"target_batch_{sku_item}"]
        st.session_state.scan_cart = {}
        st.session_state.trigger_confirm_ambil = ""
        st.session_state.focus_target = "Ketik Nama Rak Asal:"

# ==================== CALLBACK TAB MUTASI ====================
def proses_mutasi():
    mutasi_asal = st.session_state.mutasi_asal.strip()
    mutasi_sku = st.session_state.mutasi_sku.strip()
    tujuan_rak = st.session_state.mutasi_tujuan.strip()
    
    if not mutasi_asal and not mutasi_sku and not tujuan_rak: return
        
    if not mutasi_sku or not mutasi_asal or not tujuan_rak:
        st.session_state.global_notif = {"tab": "mutasi", "type": "error", "text": "❌ SKU, Rak Asal, dan Rak Tujuan wajib diisi."}
        return
    if tujuan_rak not in st.session_state.rak_gudang_tanpa_posisi:
        st.session_state.global_notif = {"tab": "mutasi", "type": "error", "text": "❌ Rak Tujuan tidak valid/belum dibuat."}
        return
    if mutasi_asal == tujuan_rak:
        st.session_state.global_notif = {"tab": "mutasi", "type": "error", "text": "❌ Rak tujuan tidak boleh sama dengan rak asal."}
        return
        
    items_di_rak = st.session_state.rak_gudang_tanpa_posisi.get(mutasi_asal, [])
    matching_items = [item for item in items_di_rak if item["sku"].lower() == mutasi_sku.lower()]
    
    item_terpilih = None
    if len(matching_items) > 1:
        opsi_kembar = st.session_state.get("mutasi_dropdown_kembar")
        if opsi_kembar:
            target_stok = int(opsi_kembar.replace("Stok Asal: ", ""))
            item_terpilih = next((item for item in matching_items if item["stok"] == target_stok), None)
    elif len(matching_items) == 1:
        item_terpilih = matching_items[0]

    if item_terpilih:
        rak_asal_items = st.session_state.rak_gudang_tanpa_posisi[mutasi_asal]
        stok_yang_ikut = item_terpilih["stok"]
        sku_asli = item_terpilih["sku"]
        
        rak_asal_items.remove(item_terpilih)
        st.session_state.rak_gudang_tanpa_posisi[tujuan_rak].append({"sku": sku_asli, "stok": stok_yang_ikut})
        save_data_to_sheets()
        
        st.session_state.global_notif = {"tab": "mutasi", "type": "success", "text": f"Berhasil memindah '{sku_asli}' ke '{tujuan_rak}'."}
        
        st.session_state.mutasi_asal = ""
        st.session_state.mutasi_sku = ""
        st.session_state.mutasi_tujuan = ""
        st.session_state.focus_target = "Nama Rak Asal:"
    else:
        st.session_state.global_notif = {"tab": "mutasi", "type": "error", "text": "❌ Proses dibatalkan. Pastikan SKU dan Rak Asal sudah benar."}

# ==================== FUNGSI TAMPILAN (UI) ====================

def ui_manajemen_rak():
    st.markdown("### 🛠️ Manajemen Struktur")
    placeholders["rak"] = st.empty() 

    st.markdown("#### 🗄️ Kelola Rak")
    opsi_rak = ["[+ Tambah Rak Baru]"] + list(st.session_state.rak_gudang_tanpa_posisi.keys())
    rak_terpilih_mgt = st.selectbox("Pilih Tindakan / Nama Rak:", opsi_rak, key="rak_action_select")

    if rak_terpilih_mgt == "[+ Tambah Rak Baru]":
        st.text_input("Nama Rak Baru:", key="input_rak_baru_scan", on_change=on_enter_tambah_rak, placeholder="Scan Barcode / Ketik lalu tekan Enter...")
        st.button("Tambah Rak Manual", on_click=on_enter_tambah_rak)
    else:
        nama_rak_baru = st.text_input(f"Ubah Nama '{rak_terpilih_mgt}' Menjadi:", key="edit_rak_name_input").strip()
        c_r1, c_r2 = st.columns(2)
        with c_r1:
            if st.button("Ubah Nama Rak") and nama_rak_baru:
                if nama_rak_baru not in st.session_state.rak_gudang_tanpa_posisi:
                    st.session_state.rak_gudang_tanpa_posisi[nama_rak_baru] = st.session_state.rak_gudang_tanpa_posisi.pop(rak_terpilih_mgt)
                    save_data_to_sheets()
                    st.session_state.global_notif = {"tab": "rak", "type": "success", "text": f"Nama rak berhasil diubah menjadi '{nama_rak_baru}'!"}
                    st.rerun()
                else:
                    st.session_state.global_notif = {"tab": "rak", "type": "error", "text": "❌ Nama rak sudah ada."}
                    st.rerun()
        with c_r2:
            if st.button(f"🗑️ Hapus {rak_terpilih_mgt}"):
                st.session_state.rak_gudang_tanpa_posisi.pop(rak_terpilih_mgt)
                save_data_to_sheets()
                st.session_state.global_notif = {"tab": "rak", "type": "warning", "text": f"Rak '{rak_terpilih_mgt}' berhasil dihapus!"}
                st.rerun()

    st.markdown("---")
    st.markdown("#### 📋 Database Rak")
    st.caption("💡 **Tips:** Untuk mengubah nama, klik 2x pada nama rak di tabel lalu tekan **Enter**. Untuk menghapus, centang kotak di sisi paling kiri lalu tekan **Delete** di keyboard atau klik ikon tong sampah di kanan atas tabel.")
    
    if not st.session_state.rak_gudang_tanpa_posisi:
        st.info("Belum ada rak yang terdaftar.")
    else:
        rak_sorted = sorted(list(st.session_state.rak_gudang_tanpa_posisi.keys()))
        df_rak = []
        for r in rak_sorted:
            items = st.session_state.rak_gudang_tanpa_posisi[r]
            sku_count = len(items)
            total_stok = sum(item["stok"] for item in items)
            df_rak.append({"Nama Rak": r, "Total Item Berbeda": sku_count, "Total Stok Fisik": total_stok})
            
        st.data_editor(
            df_rak,
            column_config={
                "Nama Rak": st.column_config.TextColumn("Nama Rak", required=True),
                "Total Item Berbeda": st.column_config.NumberColumn("Total Item Berbeda", disabled=True),
                "Total Stok Fisik": st.column_config.NumberColumn("Total Stok Fisik", disabled=True)
            },
            use_container_width=True,
            num_rows="dynamic",
            key="editor_tabel_rak",
            on_change=proses_perubahan_tabel_rak
        )

def ui_pencarian_visual():
    st.markdown("### 🔍 Pencarian Barang / Rak")
    placeholders["cari"] = st.empty()
    
    st.text_input("Masukkan Kode SKU atau Nama Rak:", key="search_input", on_change=proses_cari)
    st.button("🔍 Cari", use_container_width=True, on_click=proses_cari)

    if st.session_state.cari_results:
        res = st.session_state.cari_results
        st.markdown(f"**Hasil pencarian terakhir untuk:** `{res['query']}`")
        if res["hasil"]:
            for hasil in res["hasil"]:
                st.info(f"📦 SKU: **`{hasil['sku_penuh']}`** 📍 Rak: **{hasil['rak']}** (Stok: {hasil['stok']})")
        else:
            st.warning("Pencarian tidak menemukan hasil.")

    st.markdown("---")
    st.markdown("### 📊 Visualisasi Isi Rak")
    if not st.session_state.rak_gudang_tanpa_posisi:
        st.info("Belum ada rak yang terdaftar.")
    else:
        rak_sorted_visual = sorted(list(st.session_state.rak_gudang_tanpa_posisi.keys()))
        for r_nama in rak_sorted_visual:
            daftar_item = st.session_state.rak_gudang_tanpa_posisi[r_nama]
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
    placeholders["input"] = st.empty() 

    st.text_input("Masukkan Kode SKU:", key="input_sku_field")
    st.text_input("Jumlah Stok:", key="input_stok_field")
    st.text_input("Ketik Nama Rak Tujuan (Enter untuk Simpan Cepat):", key="input_rak_field", on_change=on_enter_input_barang)

    st.button("Simpan ke Rak", use_container_width=True, on_click=on_enter_input_barang)

def ui_hapus_barang():
    st.markdown("### ❌ Hapus Barang dari Rak")
    placeholders["hapus"] = st.empty() 

    st.text_input("Masukkan Kode SKU yang akan dihapus:", key="hapus_sku_field")
    st.text_input("Ketik Nama Rak Asal (Enter untuk Hapus Cepat):", key="hapus_rak_field", on_change=on_enter_hapus_barang)

    st.button("Hapus SKU", use_container_width=True, on_click=on_enter_hapus_barang)

def ui_ambil_barang():
    st.markdown("### 📤 Pengurangan Stok (Deteksi Otomatis)")
    placeholders["ambil"] = st.empty() 

    if "scan_cart" not in st.session_state:
        st.session_state.scan_cart = {} 

    st.text_input("Ketik Nama Rak Asal:", key="ambil_rak_field")
    st.text_input("Scan Kode SKU (Otomatis mendeteksi SKU & menambah jumlah):", key="quick_scan_input", on_change=process_scanned_sku, placeholder="Arahkan scanner ke barcode...")

    if st.session_state.scan_cart:
        st.markdown("#### 🛒 Daftar Barang yang Akan Dikurangi:")
        total_items = 0
        rak_aktif = st.session_state.get("ambil_rak_field", "").strip()
        items_di_rak = st.session_state.rak_gudang_tanpa_posisi.get(rak_aktif, [])

        for sku_item, qty in list(st.session_state.scan_cart.items()):
            matching_items = [item for item in items_di_rak if item["sku"].lower() == sku_item.lower()]
            if len(matching_items) > 1:
                col1, col2, col3, col4 = st.columns([1.5, 2.5, 1.5, 1])
                with col1: st.write(f"📦 **{sku_item}**")
                with col2:
                    opsi_stok = [f"Stok Asal: {item['stok']}" for item in matching_items]
                    st.selectbox("Pilih Target", opsi_stok, key=f"target_batch_{sku_item}", label_visibility="collapsed")
                with col3:
                    new_qty = st.number_input(f"Jumlah {sku_item}", min_value=1, key=f"qty_num_{sku_item}", label_visibility="collapsed")
                    st.session_state.scan_cart[sku_item] = new_qty
                with col4:
                    if st.button("❌", key=f"del_{sku_item}"):
                        del st.session_state.scan_cart[sku_item]
                        st.rerun()
            else:
                col1, col2, col3 = st.columns([2, 2, 1])
                with col1: st.write(f"📦 **{sku_item}**")
                with col2:
                    new_qty = st.number_input(f"Jumlah {sku_item}", min_value=1, key=f"qty_num_{sku_item}", label_visibility="collapsed")
                    st.session_state.scan_cart[sku_item] = new_qty
                with col3:
                    if st.button("❌", key=f"del_{sku_item}"):
                        del st.session_state.scan_cart[sku_item]
                        st.rerun()
            total_items += st.session_state.scan_cart.get(sku_item, 0)

        st.markdown(f"**Total Keseluruhan Stok yang Dikurangi:** {total_items} pcs")
        
        st.text_input("Konfirmasi Eksekusi (Enter di sini):", key="trigger_confirm_ambil", on_change=proses_konfirmasi_ambil)
        
        c_b1, c_b2 = st.columns(2)
        with c_b1:
            st.button("✅ Konfirmasi Pengurangan Stok", use_container_width=True, on_click=proses_konfirmasi_ambil)
        with c_b2:
            if st.button("🗑️ Reset Daftar", use_container_width=True):
                st.session_state.scan_cart = {}
                st.rerun()
    else:
        st.info("💡 Ketik nama rak dulu, lalu scan barcode Anda berulang kali di kotak atas.")

def ui_mutasi_barang():
    st.markdown("### 🔄 Mutasi (Pindah Rak)")
    placeholders["mutasi"] = st.empty() 
    
    mutasi_asal = st.text_input("Nama Rak Asal:", key="mutasi_asal").strip()
    mutasi_sku = st.text_input("Kode SKU yang Dipindah:", key="mutasi_sku").strip()
    
    if mutasi_asal and mutasi_sku:
        items_di_rak = st.session_state.rak_gudang_tanpa_posisi.get(mutasi_asal, [])
        matching_items = [item for item in items_di_rak if item["sku"].lower() == mutasi_sku.lower()]
        if len(matching_items) > 1:
            opsi_stok = [f"Stok Asal: {item['stok']}" for item in matching_items]
            st.selectbox("⚠️ Ditemukan SKU Kembar! Pilih kelompok mana yang mau dipindah:", opsi_stok, key="mutasi_dropdown_kembar")
        elif len(matching_items) == 1:
            st.info(f"✅ SKU ditemukan! (Satu tumpukan dengan stok: {matching_items[0]['stok']}) siap dipindah.")
        else:
            st.error(f"❌ SKU '{mutasi_sku}' tidak ada di rak '{mutasi_asal}'.")

    st.text_input("Nama Rak Tujuan (Enter untuk Pindah):", key="mutasi_tujuan", on_change=proses_mutasi)
    st.button("🔄 Pindah Rak", use_container_width=True, on_click=proses_mutasi)


# ==================== RENDER APLIKASI UTAMA ====================

if st.session_state.mode_aplikasi is None:
    st.markdown("<br><br><h1 style='text-align: center;'>📦 Sistem Manajemen Rak Gudang</h1>", unsafe_allow_html=True)
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
    # --- JAVASCRIPT GLOBAL (KURSOR ANTI GAGAL & PENAHAN TAB) ---
    components.html("""
        <script>
        const doc = window.parent.document;

        // Bersihkan memori usang agar tidak bentrok
        if (doc.gudang_keydown) doc.removeEventListener('keydown', doc.gudang_keydown, true);
        if (doc.gudang_click) doc.removeEventListener('click', doc.gudang_click, true);

        function focusByLabelText(labelText) {
            setTimeout(() => {
                const labels = Array.from(doc.querySelectorAll('label'));
                const targetLabel = labels.find(l => l.innerText.trim() === labelText);
                if (targetLabel) {
                    const inputId = targetLabel.getAttribute('for');
                    const input = doc.getElementById(inputId);
                    if (input) input.focus();
                }
            }, 150); 
        }

        // 1. KONTROL LOMPAT KURSOR SAAT MENEKAN ENTER
        doc.gudang_keydown = function(e) {
            if (e.key === 'Enter') {
                const active = doc.activeElement;
                if (!active || active.tagName !== 'INPUT') return;

                const activeId = active.id;
                const labelEl = doc.querySelector('label[for="' + activeId + '"]');
                if (!labelEl) return;

                const text = labelEl.innerText.trim();

                if (text === 'Masukkan Kode SKU:') focusByLabelText('Jumlah Stok:');
                else if (text === 'Jumlah Stok:') focusByLabelText('Ketik Nama Rak Tujuan (Enter untuk Simpan Cepat):');
                else if (text === 'Masukkan Kode SKU yang akan dihapus:') focusByLabelText('Ketik Nama Rak Asal (Enter untuk Hapus Cepat):');
                else if (text === 'Ketik Nama Rak Asal:') focusByLabelText('Scan Kode SKU (Otomatis mendeteksi SKU & menambah jumlah):');
                else if (text === 'Konfirmasi Eksekusi (Enter di sini):') focusByLabelText('Ketik Nama Rak Asal:');
                else if (text === 'Nama Rak Asal:') focusByLabelText('Kode SKU yang Dipindah:');
                else if (text === 'Kode SKU yang Dipindah:') focusByLabelText('Nama Rak Tujuan (Enter untuk Pindah):');
            }
        };

        // 2. KONTROL MEMORI TAB & FOKUS SAAT TAB DIKLIK
        doc.gudang_click = function(e) {
            let tabBtn = e.target.closest('[role="tab"]');
            if (tabBtn) {
                // Simpan indeks tab ke memori HP
                let tabs = Array.from(doc.querySelectorAll('[role="tab"]'));
                let idx = tabs.indexOf(tabBtn);
                if (idx !== -1) sessionStorage.setItem('gudangActiveTab', idx);

                // Langsung aktifkan kursor
                const tabText = tabBtn.innerText.trim();
                if (tabText.includes('Rak')) focusByLabelText('Nama Rak Baru:');
                else if (tabText.includes('Cari')) focusByLabelText('Masukkan Kode SKU atau Nama Rak:');
                else if (tabText.includes('Input')) focusByLabelText('Masukkan Kode SKU:');
                else if (tabText.includes('Hapus')) focusByLabelText('Masukkan Kode SKU yang akan dihapus:');
                else if (tabText.includes('Ambil')) focusByLabelText('Ketik Nama Rak Asal:');
                else if (tabText.includes('Mutasi')) focusByLabelText('Nama Rak Asal:');
            }
        };

        doc.addEventListener('keydown', doc.gudang_keydown, true);
        doc.addEventListener('click', doc.gudang_click, true);

        // 3. PEMULIHAN TAB SAAT BROWSER REFRESH / SCAN CEPAT
        function restoreTab() {
            let savedTabIdx = sessionStorage.getItem('gudangActiveTab');
            if (savedTabIdx !== null) {
                let tabs = Array.from(doc.querySelectorAll('[role="tab"]'));
                if (tabs.length > savedTabIdx) {
                    if (tabs[savedTabIdx].getAttribute('aria-selected') !== 'true') {
                        tabs[savedTabIdx].click();
                    }
                }
            }
        }
        
        // Panggil beberapa kali untuk memastikan menangkap momen Streamlit selesai loading
        setTimeout(restoreTab, 50);
        setTimeout(restoreTab, 300);
        setTimeout(restoreTab, 800);
        
        </script>
    """, height=0, width=0)

    # --- PEMBERI PERINTAH FOKUS DARI PYTHON (Setelah Eksekusi Selesai) ---
    if "focus_target" in st.session_state and st.session_state.focus_target:
        target_label = st.session_state.focus_target
        components.html(f"""
            <script>
            const doc = window.parent.document;
            setTimeout(() => {{
                const labels = Array.from(doc.querySelectorAll('label'));
                const targetLabel = labels.find(l => l.innerText.trim() === '{target_label}');
                if (targetLabel) {{
                    const inputId = targetLabel.getAttribute('for');
                    const input = doc.getElementById(inputId);
                    if (input) input.focus();
                }}
            }}, 200);
            </script>
        """, height=0, width=0)
        st.session_state.focus_target = None

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
            ui_hapus_barang()
            st.markdown("---")
            ui_ambil_barang()
            st.markdown("---")
            ui_mutasi_barang()
    else:
        tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["🗄️ Rak", "🔍 Cari", "📝 Input", "❌ Hapus", "📤 Ambil", "🔄 Mutasi"])
        
        with tab1: ui_manajemen_rak()
        with tab2: ui_pencarian_visual()
        with tab3: ui_input_barang()
        with tab4: ui_hapus_barang()
        with tab5: ui_ambil_barang()
        with tab6: ui_mutasi_barang()


# ==================== GLOBAL NOTIFICATION HANDLER (INSTAN) ====================
if "global_notif" in st.session_state and st.session_state.global_notif:
    notif = st.session_state.global_notif
    tab_aktif = notif["tab"]
    
    if tab_aktif in placeholders:
        if notif["type"] == "success":
            placeholders[tab_aktif].success(notif["text"])
        elif notif["type"] == "error":
            placeholders[tab_aktif].error(notif["text"])
        elif notif["type"] == "warning":
            placeholders[tab_aktif].warning(notif["text"])
    
    st.session_state.global_notif = None
