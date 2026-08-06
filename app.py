import time
import threading
import copy
import re
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

# ==================== FUNGSI PENGURUTAN NATURAL ====================
def natural_sort_key(s):
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', str(s))]

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

if "input_version" not in st.session_state:
    st.session_state.input_version = 0

if "displayed_search_query" not in st.session_state:
    st.session_state.displayed_search_query = ""
    
if "pending_hapus" not in st.session_state:
    st.session_state.pending_hapus = None

# ==================== CALLBACK TAMBAH RAK ====================
def on_enter_tambah_rak():
    v = st.session_state.input_version
    raw_val = st.session_state.get(f"input_rak_baru_scan_{v}", "").strip()
    
    if not raw_val: return
    
    now = time.time()
    clean_val = raw_val
    
    if "last_raw_tambah_rak" in st.session_state and "last_raw_tambah_rak_time" in st.session_state:
        prev_raw = st.session_state.last_raw_tambah_rak
        prev_time = st.session_state.last_raw_tambah_rak_time
        
        if now - prev_time < 4.0:
            if prev_raw and raw_val.startswith(prev_raw):
                potential_clean = raw_val[len(prev_raw):].strip()
                if len(potential_clean) >= 2:
                    clean_val = potential_clean

    st.session_state.last_raw_tambah_rak = raw_val
    st.session_state.last_raw_tambah_rak_time = now
    
    if not clean_val:
        st.session_state.input_version += 1
        return
        
    if clean_val not in st.session_state.rak_gudang_tanpa_posisi:
        st.session_state.rak_gudang_tanpa_posisi[clean_val] = []
        save_data_to_sheets()
        st.session_state.global_notif = {"tab": "rak", "type": "success", "text": f"✅ Rak '{clean_val}' berhasil ditambahkan!", "timestamp": time.time()}
    else:
        st.session_state.global_notif = {"tab": "rak", "type": "error", "text": f"❌ Rak '{clean_val}' sudah ada.", "timestamp": time.time()}
        
    st.session_state.input_version += 1
    st.session_state.focus_rak_after_save = True 

# ==================== CALLBACK DATABASE RAK ====================
def proses_perubahan_tabel_rak():
    changes = st.session_state.editor_tabel_rak
    rak_sorted = sorted(list(st.session_state.rak_gudang_tanpa_posisi.keys()), key=natural_sort_key)
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
                            st.session_state.global_notif = {"tab": "rak", "type": "error", "text": f"❌ Gagal! Nama rak '{new_name}' sudah ada.", "timestamp": time.time()}
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
        st.session_state.global_notif = {"tab": "rak", "type": "success", "text": "✅ Perubahan pada database rak berhasil disimpan!", "timestamp": time.time()}
        
# ==================== CALLBACK TAB CARI ====================
def on_enter_search():
    v = st.session_state.input_version
    query = st.session_state.get(f"main_search_input_{v}", "").strip()
    
    if not query:
        return
        
    now = time.time()
    if "last_search_time" in st.session_state:
        if now - st.session_state.last_search_time < 4.0:
            if st.session_state.get("last_search_val") == query:
                return
                
    st.session_state.last_search_time = now
    st.session_state.last_search_val = query
        
    st.session_state.displayed_search_query = query
    st.session_state.input_version += 1
    st.session_state.focus_search_after_save = True

# ==================== CALLBACK TAB INPUT ====================
def on_enter_input_barang():
    v = st.session_state.input_version
    sku = st.session_state.get(f"input_sku_field_{v}", "").strip()
    stok_raw = st.session_state.get(f"input_stok_field_{v}", "").strip()
    rak = st.session_state.get(f"input_rak_field_{v}", "").strip()
    
    if not sku and not stok_raw and not rak:
        return
        
    now = time.time()
    if "last_input_time" in st.session_state:
        if now - st.session_state.last_input_time < 4.0:
            if st.session_state.get("last_input_sku") == sku and st.session_state.get("last_input_rak") == rak:
                return
                
    st.session_state.last_input_time = now
    st.session_state.last_input_sku = sku
    st.session_state.last_input_rak = rak
        
    if not sku or not stok_raw or not rak:
        st.session_state.global_notif = {"tab": "input", "type": "error", "text": "❌ Semua kolom harus diisi!", "timestamp": time.time()}
        st.session_state.input_version += 1
        return
        
    if not stok_raw.isdigit():
        st.session_state.global_notif = {"tab": "input", "type": "error", "text": "❌ Stok harus angka!", "timestamp": time.time()}
        st.session_state.input_version += 1
        return
        
    if rak not in st.session_state.rak_gudang_tanpa_posisi:
        st.session_state.global_notif = {"tab": "input", "type": "error", "text": f"❌ Rak '{rak}' tidak terdaftar.", "timestamp": time.time()}
        st.session_state.input_version += 1
        return
        
    stok = int(stok_raw)
    st.session_state.rak_gudang_tanpa_posisi[rak].append({"sku": sku, "stok": stok})
    
    save_data_to_sheets()
    
    st.session_state.global_notif = {"tab": "input", "type": "success", "text": f"✅ SKU '{sku}' (Stok: {stok}) berhasil ditambahkan ke '{rak}'.", "timestamp": time.time()}
    st.session_state.input_version += 1
    st.session_state.focus_sku_after_save = True

# ==================== CALLBACK TAB HAPUS (TUMPUKAN GRAVITASI) ====================
def on_enter_hapus_barang():
    # Cegah input baru jika pop up konfirmasi sedang menyala
    if st.session_state.pending_hapus is not None:
        return

    v = st.session_state.input_version
    sku_clean = st.session_state.get(f"hapus_sku_field_{v}", "").strip()
    rak_clean = st.session_state.get(f"hapus_rak_field_{v}", "").strip()
    
    if not sku_clean and not rak_clean:
        return
        
    now = time.time()
    if "last_hapus_time" in st.session_state:
        if now - st.session_state.last_hapus_time < 4.0:
            if st.session_state.get("last_hapus_sku") == sku_clean and st.session_state.get("last_hapus_rak") == rak_clean:
                return
                
    st.session_state.last_hapus_time = now
    st.session_state.last_hapus_sku = sku_clean
    st.session_state.last_hapus_rak = rak_clean
        
    if not sku_clean or not rak_clean:
        st.session_state.global_notif = {"tab": "hapus", "type": "error", "text": "❌ Kode SKU dan Nama Rak Asal harus diisi!", "timestamp": time.time()}
        st.session_state.input_version += 1
        return
        
    if rak_clean in st.session_state.rak_gudang_tanpa_posisi:
        rak_lama = st.session_state.rak_gudang_tanpa_posisi[rak_clean]
        filtered_rak = [item for item in rak_lama if item["sku"].lower() != sku_clean.lower()]
        
        if len(filtered_rak) < len(rak_lama):
            parts = rak_clean.rsplit("-", 1)
            
            # --- CEK APAKAH INI AKAN MEMICU GRAVITASI? ---
            if len(filtered_rak) == 0 and len(parts) == 2 and parts[1].isdigit():
                # MENYALAKAN POP-UP KONFIRMASI! Hapus ditunda.
                st.session_state.pending_hapus = {
                    "sku": sku_clean,
                    "rak": rak_clean
                }
                st.session_state.input_version += 1
                return 
            else:
                # NORMAL HAPUS (Tidak memicu gravitasi)
                st.session_state.rak_gudang_tanpa_posisi[rak_clean] = filtered_rak
                save_data_to_sheets()
                st.session_state.global_notif = {"tab": "hapus", "type": "success", "text": f"✅ SKU '{sku_clean}' dihapus dari '{rak_clean}'!", "timestamp": time.time()}
                st.session_state.input_version += 1
        else:
            st.session_state.global_notif = {"tab": "hapus", "type": "error", "text": f"❌ SKU '{sku_clean}' tidak ditemukan di rak '{rak_clean}'.", "timestamp": time.time()}
            st.session_state.input_version += 1
    else:
        st.session_state.global_notif = {"tab": "hapus", "type": "error", "text": f"❌ Rak '{rak_clean}' tidak ditemukan.", "timestamp": time.time()}
        st.session_state.input_version += 1
        
    st.session_state.focus_hapus_sku_after_save = True

# ==================== CALLBACK TOMBOL POP-UP KONFIRMASI ====================
def konfirmasi_ya():
    pending = st.session_state.pending_hapus
    sku = pending["sku"]
    rak = pending["rak"]
    
    parts = rak.rsplit("-", 1)
    group = parts[0]
    deleted_floor = int(parts[1])
    
    current_floor = deleted_floor + 1
    while True:
        next_rak = f"{group}-{current_floor}"
        curr_rak = f"{group}-{current_floor - 1}"
        
        if next_rak in st.session_state.rak_gudang_tanpa_posisi:
            st.session_state.rak_gudang_tanpa_posisi[curr_rak] = st.session_state.rak_gudang_tanpa_posisi[next_rak]
            current_floor += 1
        else:
            top_rak = f"{group}-{current_floor - 1}"
            if top_rak in st.session_state.rak_gudang_tanpa_posisi:
                st.session_state.rak_gudang_tanpa_posisi[top_rak] = []
            break
            
    save_data_to_sheets()
    st.session_state.global_notif = {"tab": "hapus", "type": "success", "text": f"✅ SKU '{sku}' dihapus. (Rak '{rak}' kosong, tumpukan atasnya otomatis turun!).", "timestamp": time.time()}
    
    st.session_state.pending_hapus = None
    st.session_state.input_version += 1
    st.session_state.focus_hapus_sku_after_save = True

def konfirmasi_tidak():
    st.session_state.pending_hapus = None
    st.session_state.global_notif = {"tab": "hapus", "type": "warning", "text": "🛑 Penghapusan dan proses gravitasi DIBATALKAN.", "timestamp": time.time()}
    st.session_state.input_version += 1
    st.session_state.focus_hapus_sku_after_save = True

# ==================== FUNGSI TAMPILAN (UI) ====================

def ui_manajemen_rak():
    st.markdown("### 🛠️ Manajemen Struktur")
    placeholders["rak"] = st.empty() 

    v = st.session_state.input_version
    
    target_focus = None
    if st.session_state.get("focus_rak_after_save", False):
        target_focus = "Nama Rak Baru:"
        st.session_state.focus_rak_after_save = False

    st.markdown("#### ➕ Tambah Rak Baru")
    st.text_input(
        "Nama Rak Baru:", 
        key=f"input_rak_baru_scan_{v}", 
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
        rak_sorted = sorted(list(st.session_state.rak_gudang_tanpa_posisi.keys()), key=natural_sort_key)
        df_rak = []
        for r in rak_sorted:
            items = st.session_state.rak_gudang_tanpa_posisi[r]
            sku_list = ", ".join([str(item["sku"]) for item in items]) if items else "-"
            sku_count = len(items)
            total_stok = sum(item["stok"] for item in items)
            
            df_rak.append({
                "Nama Rak": r, 
                "KODE SKU": sku_list, 
                "Stok": total_stok,
                "Total Item Berbeda": sku_count
            })
            
        st.data_editor(
            df_rak,
            column_config={
                "Nama Rak": st.column_config.TextColumn("Nama Rak", required=True),
                "KODE SKU": st.column_config.TextColumn("KODE SKU", disabled=True),
                "Stok": st.column_config.NumberColumn("Stok", disabled=True),
                "Total Item Berbeda": st.column_config.NumberColumn("Total Item Berbeda", disabled=True)
            },
            use_container_width=True,
            num_rows="dynamic",
            key="editor_tabel_rak",
            on_change=proses_perubahan_tabel_rak
        )
        
    if target_focus:
        components.html(f"""
            <script id="focus-rak-{time.time()}">
            const doc = window.parent.document;
            function tryFocus(label, attempts) {{
                if (attempts <= 0) return;
                const inputs = Array.from(doc.querySelectorAll('input[type="text"]'));
                const inputToFocus = inputs.find(el => el.getAttribute('aria-label') === label);
                if (inputToFocus) {{
                    setTimeout(() => inputToFocus.focus(), 50);
                }} else {{
                    setTimeout(() => tryFocus(label, attempts - 1), 100);
                }}
            }}
            tryFocus('{target_focus}', 15);
            </script>
        """, height=0, width=0)

def ui_pencarian_visual():
    st.markdown("### 🔍 Pencarian Barang / Rak")
    
    v = st.session_state.input_version
    target_focus = None
    if st.session_state.get("focus_search_after_save", False):
        target_focus = "Masukkan Kode SKU atau Nama Rak:"
        st.session_state.focus_search_after_save = False

    st.text_input(
        "Masukkan Kode SKU atau Nama Rak:", 
        placeholder="Contoh: ketik 'mj', '459', atau 'A-1'...", 
        key=f"main_search_input_{v}",
        on_change=on_enter_search
    )

    query = st.session_state.get("displayed_search_query", "")
    
    if query:
        hasil_cari = []
        for nama_rak, daftar_item in st.session_state.rak_gudang_tanpa_posisi.items():
            rak_cocok = query.lower() in nama_rak.lower()
            for item in daftar_item:
                sku_cocok = query.lower() in item["sku"].lower()
                if rak_cocok or sku_cocok:
                    hasil_cari.append({"rak": nama_rak, "sku_penuh": item["sku"], "stok": item["stok"]})

        if hasil_cari:
            st.success(f"📌 Ditemukan {len(hasil_cari)} kecocokan untuk pencarian '{query}':")
            for hasil in hasil_cari:
                st.markdown(f"📦 SKU: **`{hasil['sku_penuh']}`** &nbsp;&nbsp;|&nbsp;&nbsp; 📍 Rak: **{hasil['rak']}** &nbsp;&nbsp;|&nbsp;&nbsp; 🔢 Stok: **{hasil['stok']}**")
        else:
            st.error(f"❌ Tidak ada hasil untuk '{query}' pada SKU maupun Nama Rak manapun.")

    st.markdown("---")
    st.markdown("### 📊 Visualisasi Isi Rak")
    if not st.session_state.rak_gudang_tanpa_posisi:
        st.info("Belum ada rak yang terdaftar.")
    else:
        rak_sorted_visual = sorted(list(st.session_state.rak_gudang_tanpa_posisi.keys()), key=natural_sort_key)
        
        html_vis = ""
        for r_nama in rak_sorted_visual:
            daftar_item = st.session_state.rak_gudang_tanpa_posisi[r_nama]
            html_vis += f"<div style='margin-top: 15px; font-size: 18px; font-weight: bold;'>📁 {r_nama}</div>"
            if not daftar_item:
                html_vis += "<div style='margin-top: 5px; padding: 10px; background-color: #ffeeba; color: #856404; border-radius: 8px;'>⬜ <i>RAK KOSONG</i></div>"
            else:
                html_vis += "<div style='display: flex; flex-wrap: wrap; gap: 10px; margin-top: 5px;'>"
                for item in daftar_item:
                    html_vis += f"<div style='background-color: #f8f9fa; padding: 10px 15px; border-radius: 8px; border: 1px solid #dee2e6; font-size: 14px; box-shadow: 0px 2px 4px rgba(0,0,0,0.05);'>📦 <b>{item['sku']}</b><br><span style='font-size: 12px; color: #555;'>🔢 Stok: {item['stok']}</span></div>"
                html_vis += "</div>"
        
        st.markdown(html_vis, unsafe_allow_html=True)
                        
    if target_focus:
        components.html(f"""
            <script id="focus-cari-{time.time()}">
            const doc = window.parent.document;
            function tryFocus(label, attempts) {{
                if (attempts <= 0) return;
                const inputs = Array.from(doc.querySelectorAll('input[type="text"]'));
                const inputToFocus = inputs.find(el => el.getAttribute('aria-label') === label);
                if (inputToFocus) {{
                    setTimeout(() => inputToFocus.focus(), 50);
                }} else {{
                    setTimeout(() => tryFocus(label, attempts - 1), 100);
                }}
            }}
            tryFocus('{target_focus}', 15);
            </script>
        """, height=0, width=0)

def ui_input_barang():
    st.markdown("### 📝 Input / Update ke Rak")
    placeholders["input"] = st.empty() 

    v = st.session_state.input_version
    
    target_focus = None
    if st.session_state.get("focus_sku_after_save", False):
        target_focus = "Masukkan Kode SKU:"
        st.session_state.focus_sku_after_save = False

    st.text_input("Masukkan Kode SKU:", key=f"input_sku_field_{v}")
    st.text_input("Jumlah Stok:", key=f"input_stok_field_{v}")
    st.text_input(
        "Ketik Nama Rak Tujuan (Enter untuk Simpan Cepat):", 
        key=f"input_rak_field_{v}", 
        on_change=on_enter_input_barang
    )

    st.button("Simpan ke Rak", use_container_width=True, on_click=on_enter_input_barang)

    if target_focus:
        components.html(f"""
            <script id="focus-input-{time.time()}">
            const doc = window.parent.document;
            function tryFocus(label, attempts) {{
                if (attempts <= 0) return;
                const inputs = Array.from(doc.querySelectorAll('input[type="text"]'));
                const inputToFocus = inputs.find(el => el.getAttribute('aria-label') === label);
                if (inputToFocus) {{
                    setTimeout(() => inputToFocus.focus(), 50);
                }} else {{
                    setTimeout(() => tryFocus(label, attempts - 1), 100);
                }}
            }}
            tryFocus('{target_focus}', 15);
            </script>
        """, height=0, width=0)

def ui_hapus_barang():
    st.markdown("### ❌ Hapus Barang dari Rak")
    placeholders["hapus"] = st.empty() 
    
    # === POP UP KONFIRMASI GRAVITASI ===
    if st.session_state.pending_hapus is not None:
        pending = st.session_state.pending_hapus
        st.error(f"⚠️ **PERINGATAN SISTEM GRAVITASI!**\n\nMenghapus SKU **{pending['sku']}** akan membuat **Rak {pending['rak']}** menjadi KOSONG TOTAL.\n\nApakah Anda yakin ingin menghapus barang ini dan **menurunkan rak di atasnya**?")
        
        col1, col2 = st.columns(2)
        with col1:
            st.button("✅ YA, LANJUTKAN", use_container_width=True, type="primary", on_click=konfirmasi_ya)
        with col2:
            st.button("❌ TIDAK, BATAL", use_container_width=True, on_click=konfirmasi_tidak)
    else:
        # === INPUT NORMAL JIKA TIDAK ADA POP UP ===
        v = st.session_state.input_version
        target_focus = None
        if st.session_state.get("focus_hapus_sku_after_save", False):
            target_focus = "Masukkan Kode SKU yang akan dihapus:"
            st.session_state.focus_hapus_sku_after_save = False

        st.text_input("Masukkan Kode SKU yang akan dihapus:", key=f"hapus_sku_field_{v}")
        st.text_input(
            "Ketik Nama Rak Asal (Enter untuk Hapus Cepat):", 
            key=f"hapus_rak_field_{v}", 
            on_change=on_enter_hapus_barang
        )

        st.button("Hapus SKU", use_container_width=True, on_click=on_enter_hapus_barang)

        if target_focus:
            components.html(f"""
                <script id="focus-hapus-{time.time()}">
                const doc = window.parent.document;
                function tryFocus(label, attempts) {{
                    if (attempts <= 0) return;
                    const inputs = Array.from(doc.querySelectorAll('input[type="text"]'));
                    const inputToFocus = inputs.find(el => el.getAttribute('aria-label') === label);
                    if (inputToFocus) {{
                        setTimeout(() => inputToFocus.focus(), 50);
                    }} else {{
                        setTimeout(() => tryFocus(label, attempts - 1), 100);
                    }}
                }}
                tryFocus('{target_focus}', 15);
                </script>
            """, height=0, width=0)

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
    components.html("""
        <script>
        const doc = window.parent.document;
        if (!doc.getElementById('smart-focus-script')) {
            const script = doc.createElement('script');
            script.id = 'smart-focus-script';
            script.innerHTML = `
                document.addEventListener('keydown', function(e) {
                    if (e.key === 'Enter') {
                        const active = document.activeElement;
                        if (!active || active.tagName !== 'INPUT') return;
                        
                        const label = active.getAttribute('aria-label');
                        
                        if (label === 'Masukkan Kode SKU:') {
                            setTimeout(() => {
                                const next = document.querySelector('input[aria-label="Jumlah Stok:"]');
                                if (next) next.focus();
                            }, 50);
                        }
                        else if (label === 'Jumlah Stok:') {
                            setTimeout(() => {
                                const next = document.querySelector('input[aria-label="Ketik Nama Rak Tujuan (Enter untuk Simpan Cepat):"]');
                                if (next) next.focus();
                            }, 50);
                        }
                        else if (label === 'Masukkan Kode SKU yang akan dihapus:') {
                            setTimeout(() => {
                                const next = document.querySelector('input[aria-label="Ketik Nama Rak Asal (Enter untuk Hapus Cepat):"]');
                                if (next) next.focus();
                            }, 50);
                        }
                    }
                }, true);

                document.addEventListener('click', function(e) {
                    const tabNode = e.target.closest('button[data-baseweb="tab"]') || e.target.closest('[role="tab"]');
                    if (tabNode) {
                        setTimeout(() => {
                            const inputs = Array.from(document.querySelectorAll('input[type="text"], input[type="number"]'));
                            const visibleInput = inputs.find(el => el.offsetParent !== null && !el.disabled);
                            if (visibleInput) {
                                visibleInput.focus();
                            }
                        }, 150);
                    }
                }, true);
            `;
            doc.head.appendChild(script);
        }
        </script>
    """, height=0, width=0)

    col_judul, col_tombol = st.columns([4, 1])
    
    with col_judul:
        st.markdown("<h1>📦 Sistem Manajemen Rak Gudang</h1>", unsafe_allow_html=True)
        
    with col_tombol:
        st.write("") 
        if st.button("🔄 Ganti Perangkat", use_container_width=True):
            st.session_state.mode_aplikasi = None
            st.rerun()
            
    st.divider()

    with st.sidebar:
        st.markdown("### ⚙️ Kontrol Sistem")
        if st.button("🔁 Sinkronisasi Data", use_container_width=True, type="primary"):
            with st.spinner("Menarik data terbaru..."):
                st.session_state.rak_gudang_tanpa_posisi = load_data_from_sheets()
            st.toast("✅ Data berhasil disinkronkan!", icon="🔄")
            st.rerun()
        st.caption("Gunakan tombol ini untuk menarik data terbaru jika ada input dari perangkat lain.")

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
    else:
        tab1, tab2, tab3, tab4 = st.tabs(["🗄️ Rak", "🔍 Cari", "📝 Input", "❌ Hapus"])
        
        with tab1:
            ui_manajemen_rak()
        with tab2:
            ui_pencarian_visual()
        with tab3:
            ui_input_barang()
        with tab4:
            ui_hapus_barang()


# ==================== GLOBAL NOTIFICATION HANDLER (TANPA SLEEP BEKU) ====================
if "global_notif" in st.session_state and st.session_state.global_notif:
    notif = st.session_state.global_notif
    
    if time.time() - notif.get("timestamp", time.time()) < 3.5:
        tab_aktif = notif["tab"]
        if tab_aktif in placeholders:
            with placeholders[tab_aktif]:
                if notif["type"] == "success":
                    st.success(notif["text"])
                elif notif["type"] == "error":
                    st.error(notif["text"])
                elif notif["type"] == "warning":
                    st.warning(notif["text"])
    else:
        st.session_state.global_notif = None
