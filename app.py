import streamlit as st

st.set_page_config(page_title="Sistem Slotting Rak Sederhana", layout="wide")

# --- 1. INISIALISASI DATA (SESSION STATE) ---
if "rak_gudang_tanpa_posisi" not in st.session_state:
    st.session_state.rak_gudang_tanpa_posisi = {
        "a12": [],
        "a3": [],
        "a2": [{"sku": "mj459", "stok": 500}, {"sku": "mj459", "stok": 500}]
    }

# ==========================================
# HEADER UTAMA (DIBUAT KETENGAH RAPI)
# ==========================================
st.markdown("<h1 style='text-align: center;'>📦 Sistem Manajemen Rak Gudang</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; font-size: 16px; font-style: italic; margin-bottom: 0px;'>\"Dibalik Bisnis Yang Besar, Ada Manajemen Yang Teratur\"</p>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; font-size: 12px; color: gray; margin-top: 2px;'>By. Egi</p>", unsafe_allow_html=True)
st.divider()

# --- TATA LETAK UTAMA (3 KOLOM BESAR) ---
col_kiri, col_tengah, col_kanan = st.columns([1.2, 2.0, 1.3], gap="large")

# ==========================================
# [KIRI] PANEL MANAJEMEN RAK SAJA
# ==========================================
with col_kiri:
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
                    st.success(f"Rak '{t_rak}' berhasil ditambahkan!")
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
                    st.success("Nama rak diubah!")
                    st.rerun()
                else:
                    st.error("Nama rak sudah ada.")
        with c_r2:
            if st.button(f"🗑️ Hapus {rak_terpilih_mgt}"):
                st.session_state.rak_gudang_tanpa_posisi.pop(rak_terpilih_mgt)
                st.warning(f"'{rak_terpilih_mgt}' dihapus!")
                st.rerun()


# ==========================================
# [TENGAH] SEARCH BAR + VISUALISASI
# ==========================================
with col_tengah:
    st.markdown("### 🔍 Pencarian Barang")
    search_query = st.text_input(
        "Masukkan Kode SKU (Bisa Ketik Sebagian / Huruf Besar Kecil Bebas):", 
        placeholder="Contoh: ketik 'mj' atau '459'...",
        key="main_search_input"
    ).strip()
    
    if search_query:
        hasil_cari = []
        for nama_rak, daftar_item in st.session_state.rak_gudang_tanpa_posisi.items():
            for item in daftar_item:
                if search_query.lower() in item["sku"].lower():
                    hasil_cari.append({"rak": nama_rak, "sku_penuh": item["sku"], "stok": item["stok"]})
        
        if hasil_cari:
            st.success(f"📌 Ditemukan {len(hasil_cari)} kecocokan barang:")
            for hasil in hasil_cari:
                st.info(f"📦 SKU: **`{hasil['sku_penuh']}`** 📍 Rak: **{hasil['rak']}** (Jumlah Stok: {hasil['stok']})")
        else:
            st.error(f"❌ Tidak ada SKU yang mengandung kata '{search_query}' di rak manapun.")

    st.markdown("---")

    st.markdown("### 📊 Visualisasi Isi Seluruh Rak")
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


# ==========================================
# [KANAN] OPERASI BARANG, AMBIL BARANG & MUTASI
# ==========================================
with col_kanan:
    # 1. Panel Input / Update Barang ke Rak
    st.markdown("### 📝 Input / Update Barang ke Rak")
    with st.form("form_edit_slot"):
        edit_sku = st.text_input("Masukkan Kode SKU:").strip()
        edit_stok_raw = st.text_input("Jumlah Stok:", placeholder="Contoh: 500").strip()
        edit_rak = st.text_input("Ketik Nama Rak Tujuan:", placeholder="Contoh: a2, a3").strip()
        
        c_b1, c_b2 = st.columns(2)
        with c_b1:
            btn_simpan = st.form_submit_button("Simpan ke Rak")
        with c_b2:
            btn_hapus = st.form_submit_button("Hapus SKU dari Rak")
            
        if btn_simpan and edit_sku:
            if not edit_stok_raw.isdigit():
                st.error("❌ Jumlah Stok harus diisi menggunakan angka saja!")
            elif edit_rak not in st.session_state.rak_gudang_tanpa_posisi:
                st.error(f"❌ Gagal! Rak '{edit_rak}' tidak terdaftar.")
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
                st.success(f"Berhasil sinkron! Data disimpan di '{edit_rak}'.")
                st.rerun()
            
        if btn_hapus and edit_sku:
            if edit_rak in st.session_state.rak_gudang_tanpa_posisi:
                st.session_state.rak_gudang_tanpa_posisi[edit_rak] = [
                    item for item in st.session_state.rak_gudang_tanpa_posisi[edit_rak] if item["sku"].lower() != edit_sku.lower()
                ]
                st.warning(f"Semua SKU '{edit_sku}' dihapus dari '{edit_rak}'!")
                st.rerun()
            else:
                st.error(f"❌ Rak '{edit_rak}' tidak ditemukan.")

    st.markdown("---")

    # 2. PANEL BARU: AMBIL BARANG (PENGURANGAN STOK)
    st.markdown("### 📤 Ambil Barang (Kurangi Stok)")
    with st.form("form_ambil_barang"):
        ambil_sku = st.text_input("Ketik Kode SKU yang Diambil:", placeholder="Contoh: mj459").strip()
        ambil_jumlah_raw = st.text_input("Jumlah yang Diambil:", placeholder="Contoh: 100").strip()
        ambil_rak = st.text_input("Ketik Nama Rak Asal Barang:", placeholder="Contoh: a2").strip()
        
        btn_ambil = st.form_submit_button("Proses Ambil Barang")
        
        if btn_ambil and ambil_sku:
            if not ambil_jumlah_raw.isdigit():
                st.error("❌ Jumlah ambil harus berupa angka saja!")
            elif ambil_rak not in st.session_state.rak_gudang_tanpa_posisi:
                st.error(f"❌ Gagal! Rak '{ambil_rak}' tidak ditemukan.")
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
                        # Jika jumlah ambil sama atau melebihi stok, hapus item dari rak
                        rak_items.remove(item_ditemukan)
                        st.warning(f"⚠️ Stok habis/lebih! SKU '{ambil_sku}' otomatis dihapus dari rak '{ambil_rak}'.")
                        st.rerun()
                    else:
                        # Jika ambil sebagian, kurangi stok saja
                        item_ditemukan["stok"] -= jumlah_ambil
                        st.success(f"Berhasil! Mengambil {jumlah_ambil} pcs. Sisa stok di '{ambil_rak}' menjadi {item_ditemukan['stok']}.")
                        st.rerun()
                else:
                    st.error(f"❌ Gagal! SKU '{ambil_sku}' tidak ditemukan di rak '{ambil_rak}'.")

    st.markdown("---")

    # 3. Panel Mutasi / Pindah Rak
    st.markdown("### 🔄 Mutasi (Pindah Rak)")
    with st.form("form_mutasi_direct"):
        mutasi_sku = st.text_input("Ketik Kode SKU yang Akan Dipindah:", placeholder="Contoh: mj459").strip()
        mutasi_asal = st.text_input("Ketik Nama Rak Asal Barang:", placeholder="Contoh: a3").strip()
        tujuan_rak = st.text_input("Ketik Nama Rak Tujuan Mutasi:", placeholder="Contoh: a2").strip()
        
        if st.form_submit_button("Eksekusi Pindah Rak"):
            if mutasi_asal not in st.session_state.rak_gudang_tanpa_posisi:
                st.error(f"❌ Gagal! Rak Asal '{mutasi_asal}' tidak ada.")
            elif tujuan_rak not in st.session_state.rak_gudang_tanpa_posisi:
                st.error(f"❌ Gagal! Rak Tujuan '{tujuan_rak}' tidak ada.")
            elif mutasi_asal == tujuan_rak:
                st.error("❌ Gagal! Rak tujuan tidak boleh sama dengan rak asal.")
            else:
                rak_asal_items = st.session_state.rak_gudang_tanpa_posisi[mutasi_asal]
                item_ditemukan = None
                
                for item in rak_asal_items:
                    if item["sku"] == mutasi_sku: 
                        item_ditemukan = item
                        break
                
                if item_ditemukan:
                    stok_yang_ikut = item_ditemukan["stok"]
                    st.session_state.rak_gudang_tanpa_posisi[mutasi_asal].remove(item_ditemukan)
                    st.session_state.rak_gudang_tanpa_posisi[tujuan_rak].append({"sku": mutasi_sku, "stok": stok_yang_ikut})
                    st.success(f"Sukses! Kotak '{mutasi_sku}' dimutasi ke '{tujuan_rak}' secara terpisah.")
                    st.rerun()
                else:
                    st.error(f"❌ Gagal! SKU '{mutasi_sku}' tidak ditemukan di '{mutasi_asal}'.")