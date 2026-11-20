"""Salin link dari SQLite lokal (data/links.db) ke MongoDB Atlas.

Jalankan setelah MONGODB_URI diset:
    python3 migrate_to_mongo.py
"""

import os

from app import LINK_FIELDS, MongoStore, SQLiteStore

URI = os.environ.get("MONGODB_URI") or os.environ.get("MONGODB_URL")
DB_NAME = os.environ.get("MONGODB_DB") or "generatelink_dragon"
LOCAL_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "links.db")

if not URI:
    raise SystemExit("MONGODB_URI wajib diset.")

source = SQLiteStore(LOCAL_DB)
destination = MongoStore(URI, DB_NAME)
destination.init()

copied = 0
for row in source.list_links():
    if destination.path_exists(row["custom_path"]):
        continue
    destination.insert({field: row.get(field) for field in LINK_FIELDS})
    copied += 1

print("Berhasil menyalin {} link ke MongoDB.".format(copied))
