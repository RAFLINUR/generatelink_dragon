# generatelink_dragon

[![Deploy with Vercel](https://vercel.com/button)](https://vercel.com/new/clone?repository-url=https%3A%2F%2Fgithub.com%2FRAFLINUR%2Fgeneratelink_dragon&project-name=pos-indonesia&repository-name=generatelink_dragon&env=TURSO_DATABASE_URL,TURSO_AUTH_TOKEN,SECRET_KEY&envDescription=Turso%20database%20URL%2C%20Turso%20auth%20token%2C%20dan%20kunci%20session%20Flask&envLink=https%3A%2F%2Fgithub.com%2FRAFLINUR%2Fgeneratelink_dragon%23environment-variable)

Custom Open Graph News Link Generator — Flask + SQLite (lokal) / Turso libSQL (Vercel).

## Jalankan lokal

```bash
pip install -r requirements.txt
python3 app.py
```

Buka http://localhost:5000. Database lokal dibuat otomatis di `data/links.db`.
Tanpa `TURSO_DATABASE_URL`, aplikasi selalu memakai SQLite lokal.

## Deploy ke Vercel

Filesystem serverless bersifat ephemeral, jadi data permanen disimpan di
**Turso**. Primary region database: Singapore (`aws-ap-southeast-1`) agar dekat
dengan audiens Indonesia. `vercel.json` juga memakai region `sin1` supaya
function dan database satu region.

```bash
turso group create --location aws-ap-southeast-1 dragon-group
turso db create --group dragon-group generatelink_dragon
```

Environment variable di Vercel:

| Key | Value |
|---|---|
| `TURSO_DATABASE_URL` | `libsql://dragonsx-dragons.aws-ap-southeast-1.turso.io` |
| `TURSO_AUTH_TOKEN` | token database dari Turso |
| `SECRET_KEY` | string acak untuk session Flask |

Deploy lewat import repo GitHub atau `vercel --prod`. Schema dan index unik
`custom_path` dibuat otomatis. Adapter otomatis mengubah `libsql://` menjadi
`https://` karena transport WebSocket bisa ditolak 400.

Salin 3 link lokal ke Turso:

```bash
TURSO_DATABASE_URL=... TURSO_AUTH_TOKEN=... python3 migrate_to_turso.py
```

## Environment variable

| Nama | Wajib | Keterangan |
|---|---|---|
| `TURSO_DATABASE_URL` | untuk Vercel | Kosongkan untuk memakai SQLite lokal |
| `TURSO_AUTH_TOKEN` | untuk Vercel | Token akses Turso |
| `SECRET_KEY` | disarankan | Kunci session Flask |
