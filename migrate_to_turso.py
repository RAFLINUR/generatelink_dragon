"""Salin data SQLite lokal (data/links.db) ke database Turso.

Jalankan setelah TURSO_DATABASE_URL dan TURSO_AUTH_TOKEN diset:
    python3 migrate_to_turso.py
"""

import os
import sqlite3

import libsql_client

from app import SCHEMA_SQL

URL = os.environ.get("TURSO_DATABASE_URL")
TOKEN = os.environ.get("TURSO_AUTH_TOKEN")
LOCAL_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "links.db")

if not URL or not TOKEN:
    raise SystemExit("TURSO_DATABASE_URL dan TURSO_AUTH_TOKEN wajib diset.")

client = libsql_client.create_client_sync(url=URL, auth_token=TOKEN)
client.execute(SCHEMA_SQL)

source = sqlite3.connect(LOCAL_DB)
rows = source.execute(
    """
    SELECT custom_path, target_url, title, description,
           image_url, site_name, clicks, created_at
    FROM links
    """
).fetchall()
source.close()

sql = """
INSERT OR IGNORE INTO links
    (custom_path, target_url, title, description, image_url, site_name, clicks, created_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ?)
"""
for row in rows:
    client.execute(sql, list(row))

client.close()
print("Berhasil menyalin {} link ke Turso.".format(len(rows)))
