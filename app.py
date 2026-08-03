import time
from google.oauth2.service_account import Credentials
import gspread
import streamlit as st
import json

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

# ==================== OPTIMASI PENYIMPANAN & PERISAI LIMIT GOOGLE ====================
def save_data_to_sheets():
    data_rak = [["nama_rak"]]
    data_isi = [["nama_rak", "sku", "stok"]]
    
    for r_nama, daftar_item in st.session_state.rak_gudang_tanpa_posisi.items():
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
                time.sleep(1.0) # Jeda sejenak jika server Google kepanasan
            else:
                # Gagal diam-diam (Silent Fail). Data lokal sudah aman, 
                # akan terkirim otomatis di scan berikutnya tanpa menampilkan error merah!
                pass

if "rak_gudang_tanpa_posisi" not in st.session_state:
    st.session_state.rak_gudang_tanpa_posisi = load_data_from_sheets()

if "mode_aplikasi" not in st.session_state:
    st.session_state.mode_aplikasi = None


# ==================== CALLBACK TAMBAH RAK (ANTI TUMPANG TINDIH) ====================
def on_enter_tambah_rak():
    raw_val = st.session_state.input_rak_baru_scan.strip()
    if not raw_val: return
    
    now = time.time()
    clean_val = raw_val
    
    # 1. PERISAI ANTI-BOLA SALJU (SNOWBALL PREVENTION)
    if "last_raw_tambah_rak" in st.session_state and "last_raw_tambah_rak_time" in st.session_state:
        prev_raw = st.session_state.last_raw_tambah_rak
        prev_time = st.session_state.last_raw_tambah_rak_time
        
        # Jika rentang waktu scan sangat cepat (browser lag)
        if now - prev_time < 3.0:
            if prev_raw and raw_val.startswith(prev_raw):
                potential_clean = raw_val[len(prev_raw):].strip()
                # Jika hasil potongannya valid (minimal 2 karakter), kita ambil!
                if len(potential_clean) >= 2:
                    clean_val = potential_clean

    st.session_state.last_raw_tambah_rak = raw_val
    st.session_state.last_raw_tambah_rak_time = now
    
    if not clean_val:
        st.session_state.input_rak_baru_scan = ""
        return
        
    # Eksekusi simpan
    if clean_val not in st.session_state.rak_gudang_tanpa_posisi:
        st.session_state.rak_gudang_tanpa_posisi[clean_val] = []
        save_data_to_sheets()
        st.session_state.global_notif = {"tab": "rak", "type": "success", "text": f"✅ Rak '{clean_val}' berhasil ditambahkan!"}
    else:
        st.session_state.global_notif = {"tab": "rak", "type": "error", "text": f"❌ Rak '{clean_val}' sudah ada."}
        
    # 2. CLEAR INSTAN TANPA DELAY
    st.session_state.input_rak_baru_scan = ""

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

# ==================== CALLBACK TAB INPUT ====================
def on_enter_input_barang():
    sku = st.session_state.input_sku_field.strip()
    stok_raw = st.session_state.input_stok_field.strip()
    rak = st.session_state.input_rak_field.strip()
    
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
    
    # Kosongkan kolom secara instan
    st.session_state.input_sku_field = ""
    st.session_state.input_stok_field = ""
    st.session_state.input_rak_field = ""

def btn_hapus_input_click():
    sku_clean = st.session_state.input_sku_field.strip()
    rak_clean = st.session_state.input_rak_field.strip()
    
    if not sku_clean:
        st.session_state.global_notif = {"tab": "input", "type": "error", "text": "❌ Masukkan Kode SKU yang ingin dihapus!"}
        return
        
    if rak_clean in st.session_state.rak_gudang_tanpa_posisi:
        rak_lama = st.session_state.rak_gudang_tanpa_posisi[rak_clean]
        filtered_rak = [item for item in rak_lama if item["sku"].lower() != sku_clean.lower()]
        if len(filtered_rak) < len(rak_lama):
            st.session_state.rak_gudang_tanpa_posisi[rak_clean] = filtered_rak
            save_data_to_sheets()
            st.session_state.global_notif = {"tab": "input", "type": "warning", "text": f"✅ SKU '{sku_clean}' dihapus dari '{rak_clean}'!"}
            
            st.session_state.input_sku_field = ""
            st.session_state.input_stok_field = ""
            st.session_state.input_rak_field = ""
        else:
            st.session_state.global_notif = {"tab": "input", "type": "error", "text": f"❌ SKU '{sku_clean}' tidak ditemukan di rak '{rak_clean}'."}
    else:
        st.session_state.global_notif = {"tab": "input", "type": "error", "text": f"❌ Rak '{rak_clean}' tidak ditemukan."}

# ==================== FUNGSI TAMPILAN (UI) ====================

def ui_manajemen_rak():
    st.markdown("### 🛠️ Manajemen Struktur")
    placeholders["rak"] = st.empty() 

    st.markdown("#### ➕ Tambah Rak Baru")
    
    # Form khusus scanner - Tekan Enter langsung jalan!
    st.text_input(
        "Nama Rak Baru:", 
        key="input_rak_baru_scan", 
        on_change=on_enter_tambah_rak,
        placeholder="Scan Barcode / Ketik lalu tekan Enter..."
    )
    st.button("Tambah Rak Manual", on_click=on_enter_tambah_rak)

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
    search_query = st.text_input("Masukkan Kode SKU atau Nama Rak:", placeholder="Contoh: ketik 'mj', '459', atau 'A-1'...", key="main_search_input").strip()

    if search_query:
        hasil_cari = []
        for nama_rak, daftar_item in st.session_state.rak_gudang_tanpa_posisi.items():
            rak_cocok = search_query.lower() in nama_rak.lower()
            for item in daftar_item:
                sku_cocok = search_query.lower() in item["sku"].lower()
                if rak_cocok or sku_cocok:
                    hasil_cari.append({"rak": nama_rak, "sku_penuh": item["sku"], "stok": item["stok"]})

        if hasil_cari:
            st.success(f"📌 Ditemukan {len(hasil_cari)} kecocokan:")
            for hasil in hasil_cari:
                st.info(f"📦 SKU: **`{hasil['sku_penuh']}`** 📍 Rak: **{hasil['rak']}** (Stok: {hasil['stok']})")
        else:
            st.error(f"❌ Tidak ada hasil untuk '{search_query}' pada SKU maupun Nama Rak manapun.")

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
    
    # Cukup tekan Enter di bagian nama rak, otomatis tersimpan instan!
    st.text_input(
        "Ketik Nama Rak Tujuan (Enter untuk Simpan Cepat):", 
        key="input_rak_field", 
        on_change=on_enter_input_barang
    )

    c_b1, c_b2 = st.columns(2)
    with c_b1:
        st.button("Simpan ke Rak", use_container_width=True, on_click=on_enter_input_barang)
    with c_b2:
        st.button("Hapus SKU", use_container_width=True, on_click=btn_hapus_input_click)

def ui_ambil_barang():
    st.markdown("### 📤 Pengurangan Stok (Deteksi Otomatis)")
    placeholders["ambil"] = st.empty() 

    if "scan_cart" not in st.session_state:
        st.session_state.scan_cart = {} 

    ambil_rak = st.text_input("Ketik Nama Rak Asal:", key="ambil_rak_field").strip()

    def process_scanned_sku():
        raw_val = st.session_state.quick_scan_input.strip()
        if not raw_val:
            return

        rak_terpilih = st.session_state.ambil_rak_field.strip()
        
        if not rak_terpilih:
            st.session_state.global_notif = {"tab": "ambil", "type": "error", "text": "❌ Ketik Nama Rak Asal terlebih dahulu sebelum scan!"}
            st.session_state.quick_scan_input = ""
            return
            
        if rak_terpilih not in st.session_state.rak_gudang_tanpa_posisi:
            st.session_state.global_notif = {"tab": "ambil", "type": "error", "text": f"❌ Rak '{rak_terpilih}' tidak ditemukan!"}
            st.session_state.quick_scan_input = ""
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
            st.session_state.global_notif = {"tab": "ambil", "type": "error", "text": f"❌ DITOLAK! SKU tidak dikenali di rak '{rak_terpilih}'!"}
            st.session_state.quick_scan_input = ""
            return

        jumlah_scan = 1

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
        
        rak_aktif = st.session_state.ambil_rak_field.strip()
        items_di_rak = st.session_state.rak_gudang_tanpa_posisi.get(rak_aktif, [])

        for sku_item, qty in list(st.session_state.scan_cart.items()):
            matching_items = [item for item in items_di_rak if item["sku"].lower() == sku_item.lower()]
            
            if len(matching_items) > 1:
                col1, col2, col3, col4 = st.columns([1.5, 2.5, 1.5, 1])
                with col1:
                    st.write(f"📦 **{sku_item}**")
                with col2:
                    opsi_stok = [f"Stok Asal: {item['stok']}" for item in matching_items]
                    st.selectbox(
                        "Pilih Target", 
                        opsi_stok, 
                        key=f"target_batch_{sku_item}", 
                        label_visibility="collapsed"
                    )
                with col3:
                    new_qty = st.number_input(
                        f"Jumlah {sku_item}", 
                        min_value=1, 
                        key=f"qty_num_{sku_item}", 
                        label_visibility="collapsed"
                    )
                    st.session_state.scan_cart[sku_item] = new_qty
                with col4:
                    if st.button("❌", key=f"del_{sku_item}"):
                        del st.session_state.scan_cart[sku_item]
                        if f"qty_num_{sku_item}" in st.session_state:
                            del st.session_state[f"qty_num_{sku_item}"]
                        if f"target_batch_{sku_item}" in st.session_state:
                            del st.session_state[f"target_batch_{sku_item}"]
                        st.rerun()
            else:
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
            
            total_items += st.session_state.scan_cart.get(sku_item, 0)

        st.markdown(f"**Total Keseluruhan Stok yang Dikurangi:** {total_items} pcs")

        c_b1, c_b2 = st.columns(2)
        with c_b1:
            if st.button("✅ Konfirmasi Pengurangan Stok", use_container_width=True, type="primary"):
                if not ambil_rak:
                    st.session_state.global_notif = {"tab": "ambil", "type": "error", "text": "❌ Nama Rak Asal harus diisi!"}
                    st.rerun()
                elif ambil_rak not in st.session_state.rak_gudang_tanpa_posisi:
                    st.session_state.global_notif = {"tab": "ambil", "type": "error", "text": f"❌ Rak '{ambil_rak}' tidak terdaftar."}
                    st.rerun()
                else:
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
                                st.session_state.global_notif = {"tab": "ambil", "type": "error", "text": f"❌ Gagal! Stok untuk SKU '{sku_to_reduce}' (Sisa: {item_ditemukan['stok']}) tidak cukup."}
                                berhasil = False
                                break
                            elif qty_to_reduce == item_ditemukan["stok"]:
                                rak_items.remove(item_ditemukan)
                                pesan_hasil.append(f"SKU '{item_ditemukan['sku']}' (Isi {qty_to_reduce}) habis dihapus.")
                            else:
                                item_ditemukan["stok"] -= qty_to_reduce
                                pesan_hasil.append(f"SKU '{item_ditemukan['sku']}' dikurangi {qty_to_reduce} pcs.")
                        else:
                            berhasil = False
                            st.session_state.global_notif = {"tab": "ambil", "type": "error", "text": f"❌ SKU '{sku_to_reduce}' tidak ditemukan di rak '{ambil_rak}'."}
                            break

                    if berhasil:
                        save_data_to_sheets()
                        st.session_state.global_notif = {"tab": "ambil", "type": "success", "text": "Berhasil! " + " | ".join(pesan_hasil)}
                        for sku_item in list(st.session_state.scan_cart.keys()):
                            if f"qty_num_{sku_item}" in st.session_state:
                                del st.session_state[f"qty_num_{sku_item}"]
                            if f"target_batch_{sku_item}" in st.session_state:
                                del st.session_state[f"target_batch_{sku_item}"]
                        st.session_state.scan_cart = {}
                        st.rerun()

        with c_b2:
            if st.button("🗑️ Reset Daftar", use_container_width=True):
                for sku_item in list(st.session_state.scan_cart.keys()):
                    if f"qty_num_{sku_item}" in st.session_state:
                        del st.session_state[f"qty_num_{sku_item}"]
                    if f"target_batch_{sku_item}" in st.session_state:
                        del st.session_state[f"target_batch_{sku_item}"]
                st.session_state.scan_cart = {}
                st.rerun()
    else:
        st.info("💡 Ketik nama rak dulu, lalu scan barcode Anda berulang kali di kotak atas.")

def ui_mutasi_barang():
    st.markdown("### 🔄 Mutasi (Pindah Rak)")
    placeholders["mutasi"] = st.empty() 
    
    mutasi_asal = st.text_input("Nama Rak Asal:", key="mutasi_asal_input").strip()
    mutasi_sku = st.text_input("Kode SKU yang Dipindah:", key="mutasi_sku_input").strip()
    
    item_terpilih = None
    
    if mutasi_asal and mutasi_sku:
        if mutasi_asal in st.session_state.rak_gudang_tanpa_posisi:
            items_di_rak = st.session_state.rak_gudang_tanpa_posisi[mutasi_asal]
            matching_items = [item for item in items_di_rak if item["sku"].lower() == mutasi_sku.lower()]
            
            if len(matching_items) > 1:
                opsi_stok = [f"Stok Asal: {item['stok']}" for item in matching_items]
                pilihan = st.selectbox("⚠️ Ditemukan SKU Kembar! Pilih kelompok mana yang mau dipindah:", opsi_stok, key="mutasi_dropdown_kembar")
                target_stok = int(pilihan.replace("Stok Asal: ", ""))
                item_terpilih = next((item for item in matching_items if item["stok"] == target_stok), None)
                
            elif len(matching_items) == 1:
                item_terpilih = matching_items[0]
                st.info(f"✅ SKU ditemukan! (Satu tumpukan dengan stok: {item_terpilih['stok']}) siap dipindah.")
                
            else:
                st.error(f"❌ SKU '{mutasi_sku}' tidak ada di rak '{mutasi_asal}'.")
        else:
            st.error(f"❌ Rak Asal '{mutasi_asal}' tidak valid atau belum dibuat.")

    tujuan_rak = st.text_input("Nama Rak Tujuan:", key="mutasi_tujuan_input").strip()

    if st.button("🔄 Pindah Rak", use_container_width=True, type="primary"):
        if not mutasi_sku or not mutasi_asal or not tujuan_rak:
            st.session_state.global_notif = {"tab": "mutasi", "type": "error", "text": "❌ SKU, Rak Asal, dan Rak Tujuan wajib diisi."}
            st.rerun()
        elif tujuan_rak not in st.session_state.rak_gudang_tanpa_posisi:
            st.session_state.global_notif = {"tab": "mutasi", "type": "error", "text": "❌ Rak Tujuan tidak valid/belum dibuat."}
            st.rerun()
        elif mutasi_asal == tujuan_rak:
            st.session_state.global_notif = {"tab": "mutasi", "type": "error", "text": "❌ Rak tujuan tidak boleh sama dengan rak asal."}
            st.rerun()
        elif item_terpilih:
            rak_asal_items = st.session_state.rak_gudang_tanpa_posisi[mutasi_asal]
            stok_yang_ikut = item_terpilih["stok"]
            sku_asli = item_terpilih["sku"]
            
            rak_asal_items.remove(item_terpilih)
            st.session_state.rak_gudang_tanpa_posisi[tujuan_rak].append({"sku": sku_asli, "stok": stok_yang_ikut})
            save_data_to_sheets()
            
            st.session_state.global_notif = {"tab": "mutasi", "type": "success", "text": f"Berhasil memindah SKU '{sku_asli}' (Stok: {stok_yang_ikut}) ke '{tujuan_rak}'."}
            st.rerun()
        else:
            st.session_state.global_notif = {"tab": "mutasi", "type": "error", "text": "❌ Proses dibatalkan. Pastikan SKU dan Rak Asal sudah benar."}
            st.rerun()


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
