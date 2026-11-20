"""Custom Open Graph News Link Generator - Flask.

 oleh: Dragon (Owner Dragon)

 Penyimpanan: SQLite (lokal), Turso/libSQL, atau MongoDB Atlas — dipilih
 otomatis lewat environment variable. Metadata Open Graph diambil otomatis
 dari Target Link saat link dibuat.
"""

import os
import re
import secrets
import sqlite3
import string
from contextlib import contextmanager
from datetime import datetime
from urllib.parse import urljoin, urlparse

import libsql_client
import requests
from bs4 import BeautifulSoup
from flask import (
    Flask,
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    url_for,
)
from pymongo import MongoClient, ReturnDocument
from pymongo.errors import PyMongoError

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY", "dragon-og-generator-secret-key"),
    DATABASE=os.path.join(app.root_path, "data", "links.db"),
    TURSO_DATABASE_URL=(
        os.environ.get("TURSO_DATABASE_URL") or os.environ.get("DATABASE_URL") or ""
    ),
    TURSO_AUTH_TOKEN=os.environ.get("TURSO_AUTH_TOKEN") or "",
    MONGODB_URI=(
        os.environ.get("MONGODB_URI") or os.environ.get("MONGODB_URL") or ""
    ),
    MONGODB_DB=os.environ.get("MONGODB_DB") or "generatelink_dragon",
)

CUSTOM_PATH_PATTERN = re.compile(r"^[\w./~-]+$", re.UNICODE)
RESERVED_SEGMENTS = {"create", "delete", "static", "favicon.ico"}
RANDOM_LENGTH = 6
RANDOM_ALPHABET = string.ascii_lowercase + string.digits

SCRAPE_TIMEOUT = 5
SCRAPER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

BOT_SIGNATURES = (
    "whatsapp",
    "facebookexternalhit",
    "facebookcatalog",
    "facebookbot",
    "twitterbot",
    "telegrambot",
    "telegram",
    "slackbot",
    "linkedinbot",
    "skypeuripreview",
    "discordbot",
    "pinterest",
    "embedly",
    "quora link preview",
    "vkshare",
    "line/",
    "xiaomishare",
    "googlebot",
    "bingbot",
)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS links (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    custom_path TEXT NOT NULL UNIQUE,
    target_url  TEXT NOT NULL,
    title       TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    image_url   TEXT NOT NULL DEFAULT '',
    site_name   TEXT NOT NULL DEFAULT '',
    clicks      INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""

REQUIRED_COLUMNS = {
    "id",
    "custom_path",
    "target_url",
    "title",
    "description",
    "image_url",
    "site_name",
    "clicks",
    "created_at",
}

NOT_NULL_FALLBACKS = {
    "custom_path": "''",
    "target_url": "''",
    "title": "''",
    "description": "''",
    "image_url": "''",
    "site_name": "''",
    "clicks": "0",
    "created_at": "CURRENT_TIMESTAMP",
}

LINK_FIELDS = (
    "custom_path",
    "target_url",
    "title",
    "description",
    "image_url",
    "site_name",
    "clicks",
    "created_at",
)


# ---------------------------------------------------------------------------
# Storage layer: satu interface untuk SQLite lokal dan MongoDB
# ---------------------------------------------------------------------------
class SQLiteStore:
    def __init__(self, path):
        self.path = path

    @contextmanager
    def _connection(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def init(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with self._connection() as db:
            columns = {row[1] for row in db.execute("PRAGMA table_info(links)")}

            if not columns:
                db.execute(SCHEMA_SQL)
            else:
                if "custom_path" not in columns and "slug" in columns:
                    db.execute("ALTER TABLE links RENAME COLUMN slug TO custom_path")
                    columns = {row[1] for row in db.execute("PRAGMA table_info(links)")}

                if not REQUIRED_COLUMNS.issubset(columns):
                    db.execute("ALTER TABLE links RENAME TO links_legacy")
                    db.execute(SCHEMA_SQL)
                    ordered = sorted(REQUIRED_COLUMNS)
                    names = ", ".join(ordered)
                    selected = ", ".join(
                        "COALESCE({0}, {1})".format(name, NOT_NULL_FALLBACKS[name])
                        if name in columns and name in NOT_NULL_FALLBACKS
                        else name
                        if name in columns
                        else NOT_NULL_FALLBACKS.get(name, "NULL")
                        for name in ordered
                    )
                    db.execute(
                        "INSERT OR IGNORE INTO links ({0}) SELECT {1} FROM links_legacy".format(
                            names, selected
                        )
                    )
                    db.execute("DROP TABLE links_legacy")
            db.commit()

    def list_links(self):
        with self._connection() as db:
            return [
                dict(row)
                for row in db.execute(
                    "SELECT * FROM links ORDER BY created_at DESC, id DESC"
                )
            ]

    def find_by_path(self, custom_path):
        with self._connection() as db:
            row = db.execute(
                "SELECT * FROM links WHERE custom_path = ?", (custom_path,)
            ).fetchone()
            return dict(row) if row else None

    def find_by_id(self, link_id):
        with self._connection() as db:
            row = db.execute(
                "SELECT * FROM links WHERE id = ?", (link_id,)
            ).fetchone()
            return dict(row) if row else None

    def path_exists(self, custom_path):
        return self.find_by_path(custom_path) is not None

    def insert(self, data):
        with self._connection() as db:
            cursor = db.execute(
                """
                INSERT INTO links
                    (custom_path, target_url, title, description, image_url, site_name, clicks, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                tuple(data.get(field, "") for field in LINK_FIELDS),
            )
            db.commit()
            return cursor.lastrowid

    def increment_clicks(self, link_id):
        with self._connection() as db:
            db.execute(
                "UPDATE links SET clicks = clicks + 1 WHERE id = ?", (link_id,)
            )
            db.commit()

    def delete(self, link_id):
        with self._connection() as db:
            db.execute("DELETE FROM links WHERE id = ?", (link_id,))
            db.commit()


class LibSQLStore:
    """Turso/libSQL remote — query SQL identik dengan SQLite."""

    def __init__(self, url, token):
        self._client = libsql_client.create_client_sync(url=url, auth_token=token)

    def init(self):
        self._client.execute(SCHEMA_SQL)

    @staticmethod
    def _rows(result):
        return [row.asdict() for row in result.rows]

    def list_links(self):
        result = self._client.execute(
            "SELECT * FROM links ORDER BY created_at DESC, id DESC"
        )
        return self._rows(result)

    def find_by_path(self, custom_path):
        result = self._client.execute(
            "SELECT * FROM links WHERE custom_path = ? LIMIT 1", [custom_path]
        )
        rows = self._rows(result)
        return rows[0] if rows else None

    def find_by_id(self, link_id):
        result = self._client.execute(
            "SELECT * FROM links WHERE id = ? LIMIT 1", [link_id]
        )
        rows = self._rows(result)
        return rows[0] if rows else None

    def path_exists(self, custom_path):
        result = self._client.execute(
            "SELECT 1 FROM links WHERE custom_path = ? LIMIT 1", [custom_path]
        )
        return bool(result.rows)

    def insert(self, data):
        columns = ", ".join(LINK_FIELDS)
        placeholders = ", ".join("?" for _ in LINK_FIELDS)
        result = self._client.execute(
            "INSERT INTO links ({0}) VALUES ({1})".format(columns, placeholders),
            [data.get(field, "") for field in LINK_FIELDS],
        )
        return result.last_insert_rowid

    def increment_clicks(self, link_id):
        self._client.execute(
            "UPDATE links SET clicks = clicks + 1 WHERE id = ?", [link_id]
        )

    def delete(self, link_id):
        self._client.execute("DELETE FROM links WHERE id = ?", [link_id])


class MongoStore:
    """MongoDB Atlas. ID numerik tetap dipakai agar route /delete/<int:id> utuh."""

    def __init__(self, uri, database_name):
        self.client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        self.collection = self.client[database_name]["links"]
        self.counters = self.client[database_name]["counters"]

    def init(self):
        self.collection.create_index("custom_path", unique=True)

    @staticmethod
    def _public(document):
        if not document:
            return None
        data = dict(document)
        data.pop("_id", None)
        return data

    @staticmethod
    def _now():
        return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    def list_links(self):
        documents = self.collection.find().sort([("created_at", -1), ("id", -1)])
        return [self._public(doc) for doc in documents]

    def find_by_path(self, custom_path):
        return self._public(self.collection.find_one({"custom_path": custom_path}))

    def find_by_id(self, link_id):
        return self._public(self.collection.find_one({"id": link_id}))

    def path_exists(self, custom_path):
        return self.collection.find_one(
            {"custom_path": custom_path}, {"_id": 1}
        ) is not None

    def insert(self, data):
        counter = self.counters.find_one_and_update(
            {"_id": "links"},
            {"$inc": {"seq": 1}},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        document = {field: data.get(field, "") for field in LINK_FIELDS}
        document["id"] = counter["seq"]
        document.setdefault("created_at", self._now())
        self.collection.insert_one(document)
        return document["id"]

    def increment_clicks(self, link_id):
        self.collection.update_one({"id": link_id}, {"$inc": {"clicks": 1}})

    def delete(self, link_id):
        self.collection.delete_one({"id": link_id})


_store = None
_store_ready = False


def get_store():
    global _store, _store_ready
    if _store is None:
        if app.config["TURSO_DATABASE_URL"]:
            _store = LibSQLStore(
                app.config["TURSO_DATABASE_URL"],
                app.config["TURSO_AUTH_TOKEN"],
            )
        elif app.config["MONGODB_URI"]:
            _store = MongoStore(app.config["MONGODB_URI"], app.config["MONGODB_DB"])
        else:
            _store = SQLiteStore(app.config["DATABASE"])
    if not _store_ready:
        try:
            _store.init()
            _store_ready = True
        except (PyMongoError, libsql_client.LibsqlError, OSError, sqlite3.Error):
            # Dicoba lagi pada request berikutnya saat database sudah tersedia.
            pass
    return _store


def init_db():
    """Inisialisasi ulang storage (dipakai saat startup & pengujian)."""
    global _store, _store_ready
    _store = None
    _store_ready = False
    return get_store()


init_db()


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------
def is_http_url(value):
    try:
        parsed = urlparse(value.strip())
    except ValueError:
        return False
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def normalize_custom_path(raw):
    value = (raw or "").strip().strip("/")
    return re.sub(r"/+", "/", value)


def is_reserved_path(value):
    first = value.split("/", 1)[0].lower() if value else ""
    return first in RESERVED_SEGMENTS


def generate_unique_path(store):
    while True:
        candidate = "".join(
            secrets.choice(RANDOM_ALPHABET) for _ in range(RANDOM_LENGTH)
        )
        if not store.path_exists(candidate):
            return candidate


def is_crawler():
    user_agent = (request.headers.get("User-Agent") or "").lower()
    return any(signature in user_agent for signature in BOT_SIGNATURES)


def meta_content(soup, key):
    for attribute in ("property", "name"):
        tag = soup.find("meta", attrs={attribute: key})
        if tag and tag.get("content", "").strip():
            return tag["content"].strip()
    return ""


def fetch_metadata(target_url):
    parsed = urlparse(target_url)
    domain = parsed.netloc or target_url
    result = {
        "title": domain,
        "description": "",
        "image_url": "",
        "site_name": domain,
    }

    try:
        response = requests.get(
            target_url,
            headers=SCRAPER_HEADERS,
            timeout=SCRAPE_TIMEOUT,
            allow_redirects=True,
        )
        response.raise_for_status()

        content_type = response.headers.get("Content-Type", "").lower()
        if content_type and "html" not in content_type:
            return result

        soup = BeautifulSoup(response.text, "html.parser")
        title_tag = soup.find("title")
        page_title = title_tag.get_text(strip=True) if title_tag else ""

        result["title"] = meta_content(soup, "og:title") or page_title or domain
        result["description"] = (
            meta_content(soup, "og:description")
            or meta_content(soup, "description")
            or ""
        )
        result["site_name"] = meta_content(soup, "og:site_name") or domain

        image = meta_content(soup, "og:image") or meta_content(soup, "twitter:image")
        if image:
            result["image_url"] = urljoin(response.url, image)
    except Exception:
        pass

    return result


def absolute_image_url(image_url):
    if not image_url:
        return ""
    if image_url.startswith(("http://", "https://")):
        return image_url
    return request.url_root.rstrip("/") + "/" + image_url.lstrip("/")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    links = get_store().list_links()
    return render_template(
        "index.html",
        links=links,
        total_links=len(links),
        total_clicks=sum(row["clicks"] for row in links),
    )


@app.post("/create")
def create():
    target_url = (request.form.get("target_url") or "").strip()
    custom_path = normalize_custom_path(request.form.get("custom_path"))
    errors = []

    if not is_http_url(target_url):
        errors.append("Target Link wajib diawali http:// atau https:// dan valid.")
    if custom_path and not CUSTOM_PATH_PATTERN.fullmatch(custom_path):
        errors.append(
            "Custom Link hanya boleh huruf, angka, titik, garis bawah, tanda hubung, dan slash (/)."
        )
    if custom_path and is_reserved_path(custom_path):
        errors.append(
            "Custom Link tidak boleh memakai nama route internal: create, delete, static, favicon.ico."
        )

    store = get_store()
    if custom_path and store.path_exists(custom_path):
        errors.append("Custom Link tersebut sudah digunakan. Pilih yang lain atau kosongkan.")

    if errors:
        for message in errors:
            flash(message, "error")
        return redirect(url_for("index"))

    if not custom_path:
        custom_path = generate_unique_path(store)

    metadata = fetch_metadata(target_url)
    data = dict(metadata)
    data["custom_path"] = custom_path
    data["target_url"] = target_url
    data.setdefault("clicks", 0)
    data.setdefault("created_at", datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))
    store.insert(data)

    flash("Link berhasil dibuat: /{}".format(custom_path), "success")
    return redirect(url_for("index"))


@app.route("/<path:custom_path>")
def preview(custom_path):
    custom_path = custom_path.strip("/")
    store = get_store()
    link = store.find_by_path(custom_path)
    if link is None:
        abort(404)

    bot = is_crawler()
    if not bot:
        store.increment_clicks(link["id"])
        link["clicks"] = link.get("clicks", 0) + 1

    link["og_image"] = absolute_image_url(link.get("image_url", ""))
    return render_template("preview.html", link=link, is_bot=bot)


@app.post("/delete/<int:link_id>")
def delete(link_id):
    store = get_store()
    row = store.find_by_id(link_id)
    if row is None:
        abort(404)

    image_url = row.get("image_url", "")
    store.delete(link_id)

    if image_url.startswith("static/uploads/"):
        still_used = any(
            item.get("image_url") == image_url for item in store.list_links()
        )
        if not still_used:
            file_path = os.path.join(
                app.root_path, "static", "uploads", os.path.basename(image_url)
            )
            if os.path.isfile(file_path):
                os.remove(file_path)

    flash("Link berhasil dihapus.", "success")
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
