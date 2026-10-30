# Google Play Billing — Setup & Alur

Panduan singkat mengaktifkan langganan lewat **Google Play Billing** (Android).
Kode sudah selesai; dokumen ini untuk konfigurasi Play Console + service account.

## 1. Produk yang dipakai

| Product ID (Play Console)     | Plan internal | Tipe            | Harga acuan      |
|-------------------------------|---------------|-----------------|------------------|
| `titisanku_pro_yearly`        | `pro`         | Langganan tahunan | Rp149.000/tahun |
| `titisanku_family_yearly`     | `family`      | Langganan tahunan | Rp199.000/tahun |

Pemetaan ID ↔ plan ada di `backend/server.py` (`PLAY_PRODUCTS`) dan
`frontend/src/billing.ts` (`PRODUCTS`). Ubah di kedua tempat bila ID berbeda.

## 2. Buat produk di Play Console
1. Play Console → app → **Monetize → Products → Subscriptions → Create subscription**.
2. Buat 2 langganan di atas, masing-masing dengan **1 base plan** ("Tahunan", periode 1 tahun).
3. Aktifkan base plan. Catat Product ID (harus persis sama).

## 3. Verifikasi server-side (Play Developer API)
Backend memverifikasi `purchaseToken` lewat Google Play Developer API memakai
**service account** yang sama dengan Firebase (`FIREBASE_SERVICE_ACCOUNT_JSON`).

1. Ambil `client_email` service account dari file JSON kredensial Firebase.
2. Play Console → **Users and permissions → Invite new users** → masukkan email itu,
   beri izin **View financial data** + **Manage orders/subscriptions** (atau full).
3. Set env backend:
   ```
   PLAY_PACKAGE_NAME=com.titisanku.app   # harus sama dengan android.package di app.json
   ```
4. (Opsional) Cek status: endpoint `/health` menampilkan `integrations.play_billing: true`.

> Service account butuh scope `androidpublisher` — backend menandatangani JWT sendiri
> (`backend/integrations.py`), tidak perlu `google-auth`.

## 4. Alur di aplikasi
```
User tekan "Upgrade" (Android)
   → expo-iap requestPurchase (langganan)        frontend/src/billing.ts
   → dapat purchaseToken
   → POST /payments/play/verify                  backend/verify → Play Developer API
        • validasi product_id & paymentState
        • buat payment_orders (status paid) + set plan + expires_at +365 hari
        • acknowledge pembelian (best-effort)
   → finishTransaction (tandai transaksi selesai)
   → refresh pohon, tampil "Pembayaran Berhasil"
```
Web tetap memakai Midtrans (`POST /payments/snap`) karena Play Billing hanya berlaku
untuk aplikasi Android yang didistribusikan lewat Play.

## 5. Endpoint
- `GET  /api/payments/play/products` — daftar product ID + plan (untuk frontend).
- `POST /api/payments/play/verify` — body `{ product_id, purchase_token, tree_id? }`.
  Idempoten berdasarkan `orderId` dari Play.

## 6. Uji
- Unit test (tanpa jaringan/DB): `cd backend; python -m pytest tests/test_play_billing.py -q`.
- Sandbox: unggah build ke **Internal testing** (lisensi akun tester), lakukan pembelian,
  pastikan plan aktif dan pembelian ter-acknowledge di Play Console → Orders.
