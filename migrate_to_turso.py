"""Salin link dari SQLite lokal (data/links.db) ke Turso.

Jalankan setelah TURSO_DATABASE_URL dan TURSO_AUTH_TOKEN diset:
    python3 migrate_to_turso.py
"""

import os

from app import LINK_FIELDS, LibSQLStore, SQLiteStore

URL = os.environ.get("TURSO_DATABASE_URL")
TOKEN = os.environ.get("TURSO_AUTH_TOKEN")
LOCAL_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "links.db")

if not URL or not TOKEN:
    raise SystemExit("TURSO_DATABASE_URL dan TURSO_AUTH_TOKEN wajib diset.")

source = SQLiteStore(LOCAL_DB)
destination = LibSQLStore(URL, TOKEN)
destination.init()

copied = 0
for row in source.list_links():
    if destination.path_exists(row["custom_path"]):
        continue
    destination.insert({field: row.get(field) for field in LINK_FIELDS})
    copied += 1

destination.close()
print("Berhasil menyalin {} link ke Turso.".format(copied))
