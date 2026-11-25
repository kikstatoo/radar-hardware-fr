"""
download_images.py — Cache local des images produits (étape exécutée avant le build).

Sources utilisées, dans cet ordre, pour chaque produit :
  1. data/products.json > image_url : image que tu as le droit d'utiliser
     (kit presse constructeur, image fournie par un programme d'affiliation…).
  2. Les images officielles fournies par les flux marchands (Awin / Effinity), récupérées
     par fetch_prices.py dans data/offers_latest.json. Les programmes d'affiliation
     autorisent leurs éditeurs à utiliser ces visuels pour promouvoir les produits.

Ce script ne récupère PAS d'images sur les pages des revendeurs (scraping) et ne contourne
aucune protection anti-hotlink : ces photos appartiennent aux marchands. Amazon interdit par
ailleurs le stockage de ses images en dehors de son API.

Chaque image est vérifiée, redimensionnée (800 px max) et convertie en WebP dans
assets/products/<slug>.webp (versionné dans le dépôt). build_site.py la copie dans dist/.
Sans image disponible, le site affiche un visuel neutre (jamais d'image cassée).
"""
from __future__ import annotations

import io
import sys
import time

from PIL import Image, UnidentifiedImageError

from common import OFFERS_FILE, ROOT, load_catalog, load_json, load_settings, log, now_ts, save_json

IMG_DIR = ROOT / "assets" / "products"
MANIFEST = IMG_DIR / "manifest.json"
MAX_SIZE = 800


def candidate_urls(product: dict, offers: list[dict]) -> list[tuple[str, str]]:
    urls = []
    if str(product.get("image_url", "")).startswith("https://"):
        urls.append((product["image_url"], "catalogue"))
    for o in offers:
        if str(o.get("image", "")).startswith("https://"):
            urls.append((o["image"], f"flux {o.get('merchant', '')}"))
    seen, out = set(), []
    for u, src in urls:
        if u not in seen:
            seen.add(u)
            out.append((u, src))
    return out


def fetch_image(url: str, settings: dict) -> Image.Image | None:
    import requests

    net = settings.get("network", {})
    headers = {"User-Agent": net.get("user_agent", "RadarHardwareEurope/1.0"), "Accept": "image/avif,image/webp,image/*"}
    for attempt in range(1, int(net.get("retries", 3)) + 1):
        try:
            r = requests.get(url, headers=headers, timeout=float(net.get("timeout_seconds", 30)))
            if r.status_code == 200 and r.content:
                img = Image.open(io.BytesIO(r.content))
                img.load()
                return img
            log(f"  HTTP {r.status_code} (tentative {attempt})")
            if r.status_code in (401, 403, 404, 410):
                return None
        except (requests.RequestException, UnidentifiedImageError, OSError) as exc:
            log(f"  Erreur : {exc.__class__.__name__} (tentative {attempt})")
        time.sleep(min(2 ** attempt, 10))
    return None


def save_webp(img: Image.Image, path) -> None:
    if img.mode in ("P", "LA") or (img.mode == "RGBA"):
        img = img.convert("RGBA")
        bg = Image.new("RGB", img.size, (248, 250, 252))  # fond clair #F8FAFC
        bg.paste(img, mask=img.split()[-1])
        img = bg
    else:
        img = img.convert("RGB")
    img.thumbnail((MAX_SIZE, MAX_SIZE))
    img.save(path, "WEBP", quality=85, method=6)


def main() -> int:
    settings = load_settings()
    products = load_catalog().get("products", [])
    offers = (load_json(OFFERS_FILE, {}) or {}).get("products", {})
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    manifest = load_json(MANIFEST, {}) or {}
    added = failed = skipped = 0
    for p in products:
        target = IMG_DIR / f"{p['slug']}.webp"
        cands = candidate_urls(p, offers.get(p["slug"], []))
        if target.exists() and manifest.get(p["slug"], {}).get("url") in {u for u, _ in cands} | {None}:
            skipped += 1
            continue
        if not cands:
            continue
        for url, source in cands:  # retry + source secondaire
            log(f"Image {p['slug']} depuis {source}")
            img = fetch_image(url, settings)
            if img is not None and min(img.size) >= 120:
                save_webp(img, target)
                manifest[p["slug"]] = {"file": target.name, "url": url, "source": source, "fetched": now_ts()}
                added += 1
                break
        else:
            failed += 1
    save_json(MANIFEST, manifest)
    log(f"Images : {added} ajoutée(s), {skipped} déjà en cache, {failed} en échec, "
        f"{len(products) - len(manifest)} produit(s) sans image disponible (visuel neutre affiché).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
