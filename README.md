# generatelink_dragon

Custom Open Graph News Link Generator — Flask + SQLite (lokal) / Turso libSQL (Vercel).

## Jalankan lokal

```bash
pip install -r requirements.txt
python3 app.py
```

Buka http://localhost:5000. Database lokal dibuat otomatis di `data/links.db`.

## Deploy ke Vercel

Aplikasi memakai filesystem serverless yang ephemeral, jadi database permanen
disimpan di **Turso (libSQL)**. `vercel.json` sudah menangani routing dinamis
`/<path:custom_path>` dan file static.

1. Buat database gratis di https://turso.tech (bisa login dengan GitHub).
2. Dapatkan `libsql://...` URL dan auth token database tersebut.
3. Di Vercel → Project → Settings → Environment Variables, tambahkan:

   | Key | Value |
   |---|---|
   | `TURSO_DATABASE_URL` | `libsql://<db>.turso.io` |
   | `TURSO_AUTH_TOKEN` | token dari Turso |
   | `SECRET_KEY` | string acak untuk session Flask |

4. Deploy (`vercel --prod` atau import repo GitHub di dashboard Vercel).

Schema tabel dibuat otomatis saat first request. Untuk memindahkan 3 link lama
dari SQLite lokal:

```bash
TURSO_DATABASE_URL=... TURSO_AUTH_TOKEN=... python3 migrate_to_turso.py
```

## Environment variable

| Nama | Wajib | Keterangan |
|---|---|---|
| `TURSO_DATABASE_URL` | untuk Vercel | Kosongkan untuk memakai SQLite lokal |
| `TURSO_AUTH_TOKEN` | untuk Vercel | Token akses Turso |
| `SECRET_KEY` | disarankan | Kunci session Flask |
