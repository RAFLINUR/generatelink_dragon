"""Custom Open Graph News Link Generator - Flask + SQLite.

 oleh: Dragon (Owner Dragon)

 Form hanya berisi Target Link + Custom Link. Metadata Open Graph diambil
 otomatis dari Target Link saat link dibuat.
"""

import os
import re
import secrets
import sqlite3
import string
from urllib.parse import urljoin, urlparse

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

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY", "dragon-og-generator-secret-key"),
    DATABASE=os.path.join(app.root_path, "data", "links.db"),
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

# User-Agent crawler/media sosial yang harus menerima meta tag tanpa redirect.
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

# Nilai pengganti saat menyalin data dari skema lama yang mengizinkan NULL.
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


# ---------------------------------------------------------------------------
# Database (dibuat & dimigrasi otomatis saat aplikasi dijalankan)
# ---------------------------------------------------------------------------
def get_db():
    """Buka koneksi SQLite khusus untuk request saat ini."""
    if "db" not in g:
        g.db = sqlite3.connect(app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    """Buat tabel baru atau migrasi skema lama tanpa kehilangan data."""
    os.makedirs(os.path.dirname(app.config["DATABASE"]), exist_ok=True)

    # Koneksi sendiri agar bisa dipanggil di luar application context.
    db = sqlite3.connect(app.config["DATABASE"])
    try:
        columns = {row[1] for row in db.execute("PRAGMA table_info(links)")}

        if not columns:
            db.execute(SCHEMA_SQL)
        else:
            # Skema lama memakai kolom "slug" -> rename menjadi "custom_path".
            if "custom_path" not in columns and "slug" in columns:
                db.execute("ALTER TABLE links RENAME COLUMN slug TO custom_path")
                columns = {row[1] for row in db.execute("PRAGMA table_info(links)")}

            # Bentuk skema lain: bangun ulang tabel dan salin kolom yang cocok.
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
    finally:
        db.close()


init_db()


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------
def is_http_url(value):
    """Terima hanya URL dengan skema http:// atau https://."""
    try:
        parsed = urlparse(value.strip())
    except ValueError:
        return False
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def normalize_custom_path(raw):
    """Bersihkan slash di awal/akhir dan rapikan slash ganda di tengah."""
    value = (raw or "").strip().strip("/")
    return re.sub(r"/+", "/", value)


def is_reserved_path(value):
    first = value.split("/", 1)[0].lower() if value else ""
    return first in RESERVED_SEGMENTS


def generate_unique_path():
    db = get_db()
    while True:
        candidate = "".join(
            secrets.choice(RANDOM_ALPHABET) for _ in range(RANDOM_LENGTH)
        )
        if db.execute(
            "SELECT 1 FROM links WHERE custom_path = ?", (candidate,)
        ).fetchone() is None:
            return candidate


def is_crawler():
    user_agent = (request.headers.get("User-Agent") or "").lower()
    return any(signature in user_agent for signature in BOT_SIGNATURES)


def meta_content(soup, key):
    """Cari meta tag berdasarkan property maupun attribute name."""
    for attribute in ("property", "name"):
        tag = soup.find("meta", attrs={attribute: key})
        if tag and tag.get("content", "").strip():
            return tag["content"].strip()
    return ""


def fetch_metadata(target_url):
    """Scrape OG metadata dengan fallback aman jika gagal."""
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

        result["title"] = (
            meta_content(soup, "og:title") or page_title or domain
        )
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
        # Scrape gagal (timeout, 404, encoding, dll.) -> pakai fallback.
        pass

    return result


def absolute_image_url(image_url):
    """Pastikan og:image selalu URL absolut/full."""
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
    links = get_db().execute(
        "SELECT * FROM links ORDER BY created_at DESC, id DESC"
    ).fetchall()
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

    db = get_db()
    if custom_path and db.execute(
        "SELECT 1 FROM links WHERE custom_path = ?", (custom_path,)
    ).fetchone():
        errors.append("Custom Link tersebut sudah digunakan. Pilih yang lain atau kosongkan.")

    if errors:
        for message in errors:
            flash(message, "error")
        return redirect(url_for("index"))

    if not custom_path:
        custom_path = generate_unique_path()

    metadata = fetch_metadata(target_url)
    db.execute(
        """
        INSERT INTO links
            (custom_path, target_url, title, description, image_url, site_name)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            custom_path,
            target_url,
            metadata["title"],
            metadata["description"],
            metadata["image_url"],
            metadata["site_name"],
        ),
    )
    db.commit()
    flash("Link berhasil dibuat: /{}".format(custom_path), "success")
    return redirect(url_for("index"))


@app.route("/<path:custom_path>")
def preview(custom_path):
    custom_path = custom_path.strip("/")
    row = get_db().execute(
        "SELECT * FROM links WHERE custom_path = ?", (custom_path,)
    ).fetchone()
    if row is None:
        abort(404)

    link = dict(row)
    bot = is_crawler()

    if not bot:
        db = get_db()
        db.execute("UPDATE links SET clicks = clicks + 1 WHERE id = ?", (link["id"],))
        db.commit()
        link["clicks"] += 1

    link["og_image"] = absolute_image_url(link["image_url"])
    return render_template("preview.html", link=link, is_bot=bot)


@app.post("/delete/<int:link_id>")
def delete(link_id):
    db = get_db()
    row = db.execute(
        "SELECT image_url FROM links WHERE id = ?", (link_id,)
    ).fetchone()
    if row is None:
        abort(404)

    image_url = row["image_url"]
    db.execute("DELETE FROM links WHERE id = ?", (link_id,))
    db.commit()

    # Bersihkan file gambar lokal lama jika tidak dipakai link lain.
    if image_url.startswith("static/uploads/"):
        still_used = db.execute(
            "SELECT 1 FROM links WHERE image_url = ?", (image_url,)
        ).fetchone()
        if still_used is None:
            file_path = os.path.join(
                os.path.join(app.root_path, "static", "uploads"),
                os.path.basename(image_url),
            )
            if os.path.isfile(file_path):
                os.remove(file_path)

    flash("Link berhasil dihapus.", "success")
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
