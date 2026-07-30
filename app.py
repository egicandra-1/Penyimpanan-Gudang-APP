def ui_ambil_barang():
    st.markdown("### 📤 Pengurangan Stok (Mode Scan Kasir)")

    if "scan_cart" not in st.session_state:
        st.session_state.scan_cart = {} # Format: {sku: jumlah}
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

    # Fungsi untuk memproses teks yang masuk dari scanner
    def process_scanned_sku():
        raw_val = st.session_state.quick_scan_input.strip()
        if raw_val:
            # Mengambil string bersih (mengambil kata pertama jika ada spasi)
            sku_terdeteksi = raw_val.split()[0] if " " in raw_val else raw_val
            
            # Jika scanner mengirim string panjang gabungan (misal MJ423MJ423), 
            # kita hitung berapa kali SKU tersebut muncul di dalam teks mentah tersebut!
            if ambil_rak and ambil_rak in st.session_state.rak_gudang_tanpa_posisi:
                daftar_sku_rak = [item["sku"] for item in st.session_state.rak_gudang_tanpa_posisi[ambil_rak]]
                for real_sku in daftar_sku_rak:
                    if real_sku.lower() in raw_val.lower():
                        sku_terdeteksi = real_sku
                        break

            # Hitung jumlah kemunculan teks SKU dalam scan cepat
            jumlah_kemunculan = raw_val.lower().count(sku_terdeteksi.lower())
            if jumlah_kemunculan < 1:
                jumlah_kemunculan = 1

            # Masukkan atau tambahkan ke keranjang sesuai jumlah kemunculannya
            if sku_terdeteksi in st.session_state.scan_cart:
                st.session_state.scan_cart[sku_terdeteksi] += jumlah_kemunculan
            else:
                st.session_state.scan_cart[sku_terdeteksi] = jumlah_kemunculan
            
            # Reset kotak input
            st.session_state.quick_scan_input = ""

    st.text_input(
        "Scan Kode SKU (Scan beruntun otomatis menghitung jumlahnya):", 
        key="quick_scan_input", 
        on_change=process_scanned_sku,
        placeholder="Arahkan scanner ke barcode..."
    )

    if st.session_state.scan_cart:
        st.markdown("#### 🛒 Daftar Barang yang Akan Dikurangi:")
        total_items = 0
        for sku_item, qty in list(st.session_state.scan_cart.items()):
            c1, c2, c3 = st.columns([2, 2, 1])
            with c1:
                st.write(f"📦 **{sku_item}**")
            with c2:
                # Anda juga bisa mengetik atau mengubah jumlahnya secara manual di sini
                new_qty = st.number_input(f"Jumlah {sku_item}", min_value=1, value=int(qty), key=f"qty_num_{sku_item}", label_visibility="collapsed")
                st.session_state.scan_cart[sku_item] = new_qty
            with c3:
                if st.button("❌", key=f"del_{sku_item}"):
                    del st.session_state.scan_cart[sku_item]
                    st.rerun()
            total_items += st.session_state.scan_cart[sku_item]

        st.markdown(f"**Total Keseluruhan Stok yang Dikurangi:** {total_items} pcs")

        col_b1, col_b2 = st.columns(2)
        with col_b1:
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
                        st.session_state.scan_cart = {}
                        st.rerun()

        with col_b2:
            if st.button("🗑️ Reset Keranjang", use_container_width=True):
                st.session_state.scan_cart = {}
                st.rerun()
    else:
        st.info("💡 Ketik nama rak dulu di atas, lalu scan barcode produk Anda secara berurutan.")
