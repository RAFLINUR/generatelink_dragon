# generatelink_dragon

Custom Open Graph News Link Generator — Flask + SQLite (lokal) / Turso libSQL / MongoDB Atlas.

## Jalankan lokal

```bash
pip install -r requirements.txt
python3 app.py
```

Buka http://localhost:5000. Database lokal dibuat otomatis di `data/links.db`.
Tanpa env var database, aplikasi selalu memakai SQLite lokal.

## Deploy ke Vercel

Filesystem serverless bersifat ephemeral, jadi data permanen disimpan di database
eksternal. Prioritas otomatis: **Turso → MongoDB → SQLite lokal**.

### Turso (dipakai sekarang)

Database dibuat di primary region Singapore (`aws-ap-southeast-1`) agar dekat
dengan audiens Indonesia. `vercel.json` juga memakai region `sin1` agar
function dan database satu region.

```bash
turso group create --location aws-ap-southeast-1 dragon-group
turso db create --group dragon-group generatelink_dragon
```

Environment variable di Vercel:

| Key | Value |
|---|---|
| `TURSO_DATABASE_URL` | `libsql://<db>.aws-ap-southeast-1.turso.io` |
| `TURSO_AUTH_TOKEN` | token database dari Turso |
| `SECRET_KEY` | string acak untuk session Flask |

Salin 3 link lokal ke Turso:

```bash
TURSO_DATABASE_URL=... TURSO_AUTH_TOKEN=... python3 migrate_to_turso.py
```

### Alternatif MongoDB Atlas

Kosongkan `TURSO_DATABASE_URL`, lalu isi:

| Key | Value |
|---|---|
| `MONGODB_URI` | `mongodb+srv://...` |
| `MONGODB_DB` | `generatelink_dragon` |

Migrasi: `MONGODB_URI=... python3 migrate_to_mongo.py`

## Environment variable

| Nama | Wajib | Keterangan |
|---|---|---|
| `TURSO_DATABASE_URL` | untuk Vercel | Kosongkan untuk memakai SQLite/MongoDB |
| `TURSO_AUTH_TOKEN` | untuk Vercel | Token akses Turso |
| `MONGODB_URI` | opsional | Dipakai jika Turso tidak diset |
| `MONGODB_DB` | opsional | Default: `generatelink_dragon` |
| `SECRET_KEY` | disarankan | Kunci session Flask |
