# generatelink_dragon

Custom Open Graph News Link Generator — Flask + SQLite (lokal) / MongoDB Atlas (Vercel).

## Jalankan lokal

```bash
pip install -r requirements.txt
python3 app.py
```

Buka http://localhost:5000. Database lokal dibuat otomatis di `data/links.db`.
Tanpa `MONGODB_URI`, aplikasi selalu memakai SQLite lokal.

## Deploy ke Vercel

Filesystem serverless bersifat ephemeral, jadi data permanen disimpan di
**MongoDB Atlas**. `vercel.json` sudah menangani build `@vercel/python`, routing
dinamis `/<path:custom_path>`, dan file static.

1. Buat cluster gratis di https://mongodb.com/atlas (login dengan GitHub bisa).
2. Buat database user, lalu whitelist IP `0.0.0.0/0` (diperlukan Vercel).
3. Salin connection string `mongodb+srv://...`.
4. Di Vercel → Project → Settings → Environment Variables, tambahkan:

   | Key | Value |
   |---|---|
   | `MONGODB_URI` | connection string Atlas |
   | `MONGODB_DB` | `generatelink_dragon` |
   | `SECRET_KEY` | string acak untuk session Flask |

5. Deploy lewat import repo GitHub atau `vercel --prod`.

Index unik pada `custom_path` dan counter ID dibuat otomatis. Untuk memindahkan
link lama dari SQLite lokal:

```bash
MONGODB_URI=... python3 migrate_to_mongo.py
```

## Environment variable

| Nama | Wajib | Keterangan |
|---|---|---|
| `MONGODB_URI` | untuk Vercel | Kosongkan untuk memakai SQLite lokal |
| `MONGODB_DB` | opsional | Default: `generatelink_dragon` |
| `SECRET_KEY` | disarankan | Kunci session Flask |
