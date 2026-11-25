"""
common.py — Fonctions partagées par tous les scripts du Radar Hardware FR.

Contient : chemins du projet, lecture/écriture JSON atomique, gestion du temps,
construction des liens d'affiliation, normalisation de texte et HTTP résilient.
Aucune dépendance payante, aucune clé d'API d'IA.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, quote_plus, urlparse, urlencode, parse_qsl, urlunparse

# --- Console UTF-8 (évite les plantages d'accents sous Windows) -------------
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

# --- Chemins ----------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
TEMPLATES_DIR = ROOT / "templates"
STATIC_DIR = ROOT / "static"
DIST_DIR = ROOT / "dist"

PRODUCTS_FILE = DATA_DIR / "products.json"
OFFERS_FILE = DATA_DIR / "offers_latest.json"
HISTORY_FILE = DATA_DIR / "price_history.json"
ALERTS_FILE = DATA_DIR / "alerts_sent.json"
SIM_STATE_FILE = DATA_DIR / "sim_state.json"
SITE_STATS_FILE = DATA_DIR / "site_stats.json"

MONTHS_FR = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
             "août", "septembre", "octobre", "novembre", "décembre"]


def log(msg: str) -> None:
    """Affiche un message horodaté (visible dans les logs GitHub Actions)."""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


# --- JSON -------------------------------------------------------------------
def load_json(path: Path, default=None):
    """Charge un JSON ; renvoie `default` si le fichier est absent ou corrompu."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return default
    except json.JSONDecodeError as exc:
        log(f"⚠ JSON illisible {path.name} ({exc}) — valeur par défaut utilisée.")
        return default


def save_json(path: Path, data, compact: bool = False) -> None:
    """Écrit un JSON de façon atomique (fichier temporaire puis renommage)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        if compact:
            json.dump(data, fh, ensure_ascii=False, separators=(",", ":"))
        else:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    os.replace(tmp, path)


def load_settings() -> dict:
    return load_json(CONFIG_DIR / "settings.json", {})


def load_affiliates() -> dict:
    return load_json(CONFIG_DIR / "affiliates.json", {})


def load_feeds() -> dict:
    return load_json(CONFIG_DIR / "feeds.json", {"product_feeds": [], "rss_feeds": []})


def load_catalog() -> dict:
    return load_json(PRODUCTS_FILE, {"categories": {}, "products": []})


# --- Temps ------------------------------------------------------------------
def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def now_ts() -> int:
    return int(time.time())


def iso(ts: int | float | None = None) -> str:
    dt = datetime.fromtimestamp(ts, timezone.utc) if ts is not None else now_utc()
    return dt.replace(microsecond=0).isoformat()


def month_year_fr(dt: datetime | None = None) -> str:
    dt = dt or now_utc()
    return f"{MONTHS_FR[dt.month - 1]} {dt.year}"


def date_fr(ts: int) -> str:
    dt = datetime.fromtimestamp(ts, timezone.utc)
    return f"{dt.day} {MONTHS_FR[dt.month - 1]} {dt.year}"


# --- Texte ------------------------------------------------------------------
def normalize(text: str) -> str:
    """Minuscules, sans accents, ponctuation réduite à des espaces."""
    text = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode()
    text = text.lower().replace("_", " ")
    text = re.sub(r"[^a-z0-9\-\.\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_code(code: str) -> str:
    """Normalise un EAN/MPN pour comparaison (alphanumérique, majuscules)."""
    return re.sub(r"[^A-Za-z0-9]", "", str(code or "")).upper()


def parse_price(value) -> float | None:
    """Convertit '1 099,90 €', '1099.90', 1099.9 en float. None si illisible."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value) if value > 0 else None
    s = str(value).replace(" ", " ").replace("€", "").replace("EUR", "").strip()
    s = s.replace(" ", "")
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    else:
        s = s.replace(",", ".")
    m = re.search(r"\d+(?:\.\d+)?", s)
    if not m:
        return None
    price = float(m.group(0))
    return price if price > 0 else None


def fmt_price(value: float | None) -> str:
    """Format français : 1 099,90 €"""
    if value is None:
        return "—"
    s = f"{value:,.2f}".replace(",", " ").replace(".", ",")
    return f"{s} €"


def fmt_pct(value: float | None, decimals: int = 0) -> str:
    if value is None:
        return "—"
    return f"{value:.{decimals}f}".replace(".", ",") + " %"


# --- Affiliation ------------------------------------------------------------
def _is_placeholder(value) -> bool:
    """Un identifiant vide ou composé uniquement de zéros est considéré non configuré."""
    v = str(value or "").strip()
    return not v or set(v) <= {"0"}


def _with_query_param(url: str, key: str, value: str) -> str:
    parts = urlparse(url)
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k != key]
    query.append((key, value))
    return urlunparse(parts._replace(query=urlencode(query)))


def merchant_search_url(merchant_key: str, product: dict, affiliates: dict) -> str:
    """URL de recherche du produit chez le marchand (utilisée en mode démo)."""
    merchant = affiliates.get("merchants", {}).get(merchant_key, {})
    template = merchant.get("search_url", "https://www.google.com/search?q={query}")
    query = product.get("search_query") or product["name"]
    if "wholesale-{query}" in template:
        return template.replace("{query}", quote(query.replace(" ", "-")))
    return template.replace("{query}", quote_plus(query))


def affiliate_url(merchant_key: str, url: str, affiliates: dict, already_affiliate: bool = False) -> str:
    """Injecte automatiquement les identifiants d'affiliation dans une URL marchand.

    - Amazon : ajout du paramètre ?tag=
    - Awin : enrobage https://www.awin1.com/cread.php?awinmid=..&awinaffid=..&ued=URL
    - Effiliation (Effinity) : enrobage track.effiliation.com
    - AliExpress : enrobage s.click.aliexpress.com
    Si un identifiant n'est pas configuré, l'URL directe est renvoyée (lien toujours valide).
    """
    if not url or already_affiliate:
        return url
    merchant = affiliates.get("merchants", {}).get(merchant_key, {})
    network = merchant.get("network", "direct")

    if network == "amazon":
        tag = affiliates.get("amazon_tag", "")
        return _with_query_param(url, "tag", tag) if tag else url

    if network == "awin":
        mid, pub = merchant.get("awin_mid"), affiliates.get("awin_publisher_id")
        if _is_placeholder(mid) or _is_placeholder(pub):
            return url
        return (f"https://www.awin1.com/cread.php?awinmid={quote(str(mid))}"
                f"&awinaffid={quote(str(pub))}&ued={quote(url, safe='')}")

    if network == "effiliation":
        cid = merchant.get("effiliation_id_compteur") or affiliates.get("effiliation_id_compteur")
        if _is_placeholder(cid):
            return url
        return (f"https://track.effiliation.com/servlet/effi.redir?id_compteur={quote(str(cid))}"
                f"&url={quote(url, safe='')}")

    if network == "aliexpress":
        key = affiliates.get("aliexpress_aff_short_key", "")
        if _is_placeholder(key):
            return url
        return (f"https://s.click.aliexpress.com/deep_link.htm?aff_short_key={quote(key)}"
                f"&dl_target={quote(url, safe='')}")

    return url


def get_base_url(affiliates: dict) -> str:
    """URL publique du site. Si la valeur d'exemple n'a pas été modifiée et que l'on
    tourne dans GitHub Actions, elle est déduite automatiquement du dépôt."""
    base = (os.environ.get("SITE_BASE_URL") or affiliates.get("base_url") or "").rstrip("/")
    repo = os.environ.get("GITHUB_REPOSITORY")  # ex: pseudo/radar-hardware-fr
    if (not base or "votre-pseudo" in base) and repo and "/" in repo:
        owner, name = repo.split("/", 1)
        if name.lower() == f"{owner.lower()}.github.io":
            base = f"https://{owner.lower()}.github.io"
        else:
            base = f"https://{owner.lower()}.github.io/{name}"
    return base or "http://localhost:8000"


# --- HTTP résilient ---------------------------------------------------------
def http_get(url: str, settings: dict, binary: bool = False):
    """GET avec plusieurs tentatives et délai croissant. Renvoie bytes/str ou None."""
    import requests  # import local : les scripts sans réseau n'en ont pas besoin

    net = settings.get("network", {})
    retries = int(net.get("retries", 3))
    timeout = float(net.get("timeout_seconds", 30))
    headers = {"User-Agent": net.get("user_agent", "RadarHardwareFR/1.0")}
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, headers=headers, timeout=timeout)
            if resp.status_code == 200:
                return resp.content if binary else resp.text
            log(f"  HTTP {resp.status_code} sur {urlparse(url).netloc} (tentative {attempt}/{retries})")
            if resp.status_code in (401, 403, 404):
                return None
        except requests.RequestException as exc:
            log(f"  Erreur réseau {urlparse(url).netloc} : {exc.__class__.__name__} (tentative {attempt}/{retries})")
        time.sleep(min(2 ** attempt, 20))
    return None
