"""
fetch_prices.py — Collecte des prix (étape 1 du pipeline horaire).

Système hybride, sans scraping agressif ni blocage IP :
  1. Flux produits marchands CSV/XML (Awin, Effinity…) configurés dans config/feeds.json,
     rapprochés du catalogue par EAN, puis MPN, puis mots-clés.
  2. Flux RSS publics de bons plans (prix extrait du titre).
  3. Mode simulation réaliste automatique tant qu'aucune URL de flux n'est renseignée :
     variations de -15 % à +5 % par marchand, ventes flash, ruptures et retours en stock.

Sortie : data/offers_latest.json (+ data/sim_state.json en mode démo, et un historique
de 30 jours pré-rempli au tout premier lancement pour que le site soit complet immédiatement).
"""
from __future__ import annotations

import csv
import gzip
import io
import math
import random
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

from common import (HISTORY_FILE, OFFERS_FILE, SIM_STATE_FILE, affiliate_url, http_get,
                    load_affiliates, load_catalog, load_feeds, load_json, load_settings, log,
                    merchant_search_url, normalize, normalize_code, now_ts, parse_price, iso,
                    save_json)

csv.field_size_limit(min(sys.maxsize, 2**31 - 1))

FACTOR_MIN, FACTOR_MAX = -0.15, 0.05  # bornes de variation simulée autour du prix de référence


# =============================================================================
# 1. Flux marchands CSV / XML
# =============================================================================
def _decompress(raw: bytes) -> bytes:
    """Décompresse automatiquement gzip/zip (les flux Awin sont souvent gzippés)."""
    if raw[:2] == b"\x1f\x8b":
        return gzip.decompress(raw)
    if raw[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            first = zf.namelist()[0]
            return zf.read(first)
    return raw


def _truthy_stock(value) -> bool:
    v = normalize(str(value))
    if v in ("", "none"):
        return True  # champ absent : on considère l'offre active
    return v in ("1", "yes", "oui", "true", "in stock", "instock", "en stock", "disponible", "y") or \
        (v.isdigit() and int(v) > 0) or "in stock" in v or "en stock" in v


def _iter_csv_rows(text: str, delimiter: str):
    sample = text[:4096]
    if not delimiter:
        try:
            delimiter = csv.Sniffer().sniff(sample, delimiters=",;|\t").delimiter
        except csv.Error:
            delimiter = ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    for row in reader:
        yield {(k or "").strip(): (v or "").strip() for k, v in row.items()}


def _iter_xml_rows(text: str, item_tag: str):
    root = ET.fromstring(text)
    for el in root.iter():
        tag = el.tag.split("}")[-1]
        if tag != item_tag:
            continue
        row = {}
        for child in el:
            row[child.tag.split("}")[-1]] = (child.text or "").strip()
        row.update({k: v for k, v in el.attrib.items()})
        yield row


class Matcher:
    """Rapproche une ligne de flux d'un produit du catalogue."""

    def __init__(self, products: list[dict]):
        self.by_ean = {}
        for p in products:  # EAN principal + EAN additionnels (ex. modèles partenaires d'une carte graphique)
            for code in [p.get("ean", "")] + list(p.get("eans", [])):
                if normalize_code(code):
                    self.by_ean[normalize_code(code).lstrip("0")] = p
        self.by_mpn = {normalize_code(p["mpn"]): p for p in products if p.get("mpn")}
        self.products = products

    def match(self, ean: str, mpn: str, name: str, category_hint: str | None = None):
        e = normalize_code(ean).lstrip("0")  # « 730143315289 » == « 0730143315289 »
        if e and e in self.by_ean:
            return self.by_ean[e]
        m = normalize_code(mpn)
        if m and m in self.by_mpn:
            return self.by_mpn[m]
        n = normalize(name)
        if not n:
            return None
        best, best_len = None, 0
        for p in self.products:
            kws = [normalize(k) for k in p.get("match_keywords", [])]
            if not kws or not all(k in n for k in kws):
                continue
            if any(normalize(x) in n for x in p.get("exclude_keywords", [])):
                continue
            score = sum(len(k) for k in kws)
            if score > best_len:  # le jeu de mots-clés le plus précis gagne
                best, best_len = p, score
        return best


def fetch_product_feeds(feeds_cfg: dict, products: list[dict], settings: dict, affiliates: dict):
    """Lit tous les flux produits configurés. Renvoie {slug: [offres]} et le nb de flux lus."""
    matcher = Matcher(products)
    offers: dict[str, list[dict]] = {}
    feeds_ok = 0
    for feed in feeds_cfg.get("product_feeds", []):
        url = (feed.get("url") or "").strip()
        if not url or not feed.get("enabled", True):
            continue
        merchant = feed.get("merchant", "inconnu")
        log(f"→ Flux {merchant} ({feed.get('format', 'csv')})")
        raw = http_get(url, settings, binary=True)
        if raw is None:
            log(f"  ✗ flux {merchant} indisponible, on continue.")
            continue
        try:
            text = _decompress(raw).decode("utf-8-sig", errors="replace")
            fields = feed.get("fields", {})
            if feed.get("format", "csv").lower() == "xml":
                rows = _iter_xml_rows(text, feed.get("item_tag", "product"))
            else:
                rows = _iter_csv_rows(text, feed.get("delimiter", ","))
            matched = 0
            for row in rows:
                product = matcher.match(row.get(fields.get("ean", "ean"), ""),
                                        row.get(fields.get("mpn", "mpn"), ""),
                                        row.get(fields.get("name", "name"), ""))
                if not product:
                    continue
                price = parse_price(row.get(fields.get("price", "price")))
                link = row.get(fields.get("url", "url"), "")
                if not price or not link:
                    continue
                # Garde-fou : un prix incohérent (accessoire, lot…) est ignoré
                if not (0.4 * product["price_ref"] <= price <= 2.5 * product["price_ref"]):
                    continue
                in_stock = _truthy_stock(row.get(fields.get("in_stock", "in_stock"), ""))
                offer = {
                    "merchant": merchant,
                    "price": round(price, 2),
                    "in_stock": in_stock,
                    "url": affiliate_url(merchant, link, affiliates, feed.get("url_is_affiliate", False)),
                    "source": "feed",
                }
                bucket = offers.setdefault(product["slug"], [])
                existing = next((o for o in bucket if o["merchant"] == merchant), None)
                if existing is None:
                    bucket.append(offer)
                    matched += 1
                elif (offer["in_stock"], -offer["price"]) > (existing["in_stock"], -existing["price"]):
                    bucket[bucket.index(existing)] = offer  # garde la meilleure offre du marchand
            feeds_ok += 1
            log(f"  ✓ {matched} produits du catalogue trouvés chez {merchant}")
        except (ET.ParseError, csv.Error, UnicodeError, ValueError) as exc:
            log(f"  ✗ flux {merchant} illisible : {exc}")
    return offers, feeds_ok


# =============================================================================
# 2. Flux RSS bons plans
# =============================================================================
PRICE_RE = re.compile(r"(\d{1,3}(?:[   .]\d{3})*(?:[.,]\d{1,2})?)\s?(?:€|eur)", re.I)


def fetch_rss_deals(feeds_cfg: dict, products: list[dict], settings: dict, affiliates: dict):
    matcher = Matcher(products)
    offers: dict[str, list[dict]] = {}
    count = 0
    merchant_names = {normalize(m["name"]).split(".")[0]: k for k, m in affiliates.get("merchants", {}).items()}
    for feed in feeds_cfg.get("rss_feeds", []):
        url = (feed.get("url") or "").strip()
        if not url or not feed.get("enabled", True):
            continue
        log(f"→ RSS {feed.get('name', url)}")
        text = http_get(url, settings)
        if not text:
            continue
        try:
            root = ET.fromstring(text.encode("utf-8"))
        except ET.ParseError as exc:
            log(f"  ✗ RSS illisible : {exc}")
            continue
        max_age = float(feed.get("max_age_hours", 48)) * 3600
        for item in root.iter():
            if item.tag.split("}")[-1] not in ("item", "entry"):
                continue
            vals = {c.tag.split("}")[-1]: (c.text or "").strip() for c in item}
            link = vals.get("link") or next((c.attrib.get("href") for c in item if c.tag.endswith("link")), "")
            title = vals.get("title", "")
            date_raw = vals.get("pubDate") or vals.get("updated") or vals.get("published")
            if date_raw:
                try:
                    if now_ts() - parsedate_to_datetime(date_raw).timestamp() > max_age:
                        continue
                except (TypeError, ValueError):
                    pass
            product = matcher.match("", "", title)
            m = PRICE_RE.search(title)
            if not product or not m or not link:
                continue
            price = parse_price(m.group(1))
            if not price or not (0.4 * product["price_ref"] <= price <= 2.5 * product["price_ref"]):
                continue
            n_title = normalize(title)
            merchant = next((k for name, k in merchant_names.items() if name and name in n_title), "bonplan")
            offers.setdefault(product["slug"], []).append({
                "merchant": merchant, "price": round(price, 2), "in_stock": True,
                "url": affiliate_url(merchant, link, affiliates), "source": "rss",
            })
            count += 1
        log(f"  ✓ {count} bons plans rapprochés du catalogue")
    return offers


# =============================================================================
# 3. Simulation réaliste (mode démo)
# =============================================================================
def _psychological_price(value: float) -> float:
    """Arrondit à un prix 'marchand' : 449,90 / 1 099,00 / 89,99."""
    if value >= 1000:
        return math.floor(value / 10) * 10 + 9.99
    if value >= 100:
        return math.floor(value) + (0.90 if int(value) % 2 else 0.99)
    return math.floor(value) + 0.99


def _new_merchant_state(bias: float, rng: random.Random) -> dict:
    return {"factor": max(FACTOR_MIN, min(FACTOR_MAX, bias + rng.gauss(0, 0.01))), "flash": 0, "in_stock": True}


def simulate_step(products: list[dict], state: dict, sim_cfg: dict, rng: random.Random) -> dict:
    """Fait avancer le marché simulé d'une heure. Modifie `state`, renvoie {slug: [offres brutes]}."""
    biases = sim_cfg.get("merchant_bias", {})
    p_flash = float(sim_cfg.get("flash_sale_probability", 0.002))
    p_oos = float(sim_cfg.get("out_of_stock_probability", 0.01))
    p_back = float(sim_cfg.get("back_in_stock_probability", 0.15))
    result = {}
    for product in products:
        pst = state.setdefault(product["slug"], {"trend": 0.0, "merchants": {}})
        # Dérive lente du marché pour ce produit (retour à la moyenne)
        pst["trend"] = max(-0.06, min(0.03, pst["trend"] + rng.gauss(0, 0.003) - 0.02 * pst["trend"]))
        offers = []
        for mk in product.get("merchants", []):
            bias = float(biases.get(mk, 0.0))
            ms = pst["merchants"].get(mk) or _new_merchant_state(bias, rng)
            if ms["flash"] > 0:
                ms["flash"] -= 1
                if ms["flash"] == 0:
                    ms["factor"] = bias + rng.gauss(0, 0.01)
            elif rng.random() < p_flash:
                ms["factor"] = rng.uniform(-0.15, -0.10)  # vente flash
                ms["flash"] = rng.randint(2, 10)
                ms["in_stock"] = True
            else:
                ms["factor"] += rng.gauss(0, 0.004) + 0.12 * (bias - ms["factor"])
            ms["factor"] = max(FACTOR_MIN, min(FACTOR_MAX, ms["factor"]))
            # Rupture / retour en stock contrôlés (jamais de rupture pendant une vente flash)
            if ms["in_stock"] and ms["flash"] == 0 and rng.random() < p_oos:
                ms["in_stock"] = False
            elif not ms["in_stock"] and rng.random() < p_back:
                ms["in_stock"] = True
            pst["merchants"][mk] = ms
            total = max(FACTOR_MIN, min(FACTOR_MAX, ms["factor"] + pst["trend"]))
            offers.append({"merchant": mk,
                           "price": round(_psychological_price(product["price_ref"] * (1 + total)), 2),
                           "in_stock": ms["in_stock"]})
        if offers and not any(o["in_stock"] for o in offers):
            offers[0]["in_stock"] = True  # au moins une offre disponible
        result[product["slug"]] = offers
    return result


def best_in_stock(offers: list[dict]) -> float | None:
    prices = [o["price"] for o in offers if o.get("in_stock")]
    return min(prices) if prices else None


def seed_simulated_history(products: list[dict], sim_cfg: dict, settings: dict, rng: random.Random) -> dict:
    """Pré-remplit 30 jours d'historique horaire simulé (premier lancement uniquement)."""
    days = int(sim_cfg.get("seed_days", 30))
    max_points = int(settings.get("history_max_points", 720))
    hours = min(days * 24, max_points) - 1
    state: dict = {}
    end = now_ts() - (now_ts() % 3600)
    history = {"mode": "simulation", "last_offers_ts": 0, "products": {}}
    for h in range(hours, 0, -1):
        ts = end - h * 3600
        step = simulate_step(products, state, sim_cfg, rng)
        for slug, offers in step.items():
            price = best_in_stock(offers)
            entry = history["products"].setdefault(slug, {"points": [], "all_time_min": None})
            entry["points"].append([ts, price])
            if price is not None and (entry["all_time_min"] is None or price < entry["all_time_min"]["price"]):
                entry["all_time_min"] = {"price": price, "ts": ts}
    history["last_offers_ts"] = end - 3600
    return history, state


def run_simulation(products, settings, affiliates):
    sim_cfg = settings.get("simulation", {})
    rng = random.Random()
    history = load_json(HISTORY_FILE, None)
    state = load_json(SIM_STATE_FILE, None)
    if not history or not history.get("products") or history.get("mode") != "simulation" or not state:
        log("Premier lancement en mode démo : génération de 30 jours d'historique simulé…")
        history, state = seed_simulated_history(products, sim_cfg, settings, rng)
        save_json(HISTORY_FILE, history, compact=True)
    raw = simulate_step(products, state, sim_cfg, rng)
    save_json(SIM_STATE_FILE, state, compact=True)
    by_slug = {p["slug"]: p for p in products}
    offers = {}
    for slug, items in raw.items():
        product = by_slug[slug]
        offers[slug] = [{**o, "url": affiliate_url(o["merchant"], merchant_search_url(o["merchant"], product, affiliates), affiliates),
                         "source": "simulation"} for o in items]
    return offers


# =============================================================================
# Orchestration
# =============================================================================
def has_real_sources(feeds_cfg: dict) -> bool:
    all_feeds = feeds_cfg.get("product_feeds", []) + feeds_cfg.get("rss_feeds", [])
    return any((f.get("url") or "").strip() and f.get("enabled", True) for f in all_feeds)


def main() -> int:
    settings, affiliates, feeds_cfg = load_settings(), load_affiliates(), load_feeds()
    products = load_catalog().get("products", [])
    if not products:
        log("✗ Catalogue vide (data/products.json).")
        return 1

    if has_real_sources(feeds_cfg):
        mode = "live"
        log("Mode RÉEL : lecture des flux marchands et RSS.")
        offers, feeds_ok = fetch_product_feeds(feeds_cfg, products, settings, affiliates)
        for slug, extra in fetch_rss_deals(feeds_cfg, products, settings, affiliates).items():
            offers.setdefault(slug, []).extend(extra)
        previous = load_json(OFFERS_FILE, {}) or {}
        if not offers and previous.get("mode") == "live":
            # Panne réseau générale : on garde les dernières offres connues plutôt qu'un site vide
            log("⚠ Aucune offre récupérée : conservation des offres précédentes (marquées 'stale').")
            offers = {slug: [{**o, "stale": True} for o in items]
                      for slug, items in previous.get("products", {}).items()}
        # Passage démo → réel : on efface l'historique simulé pour ne jamais mélanger faux et vrais prix
        history = load_json(HISTORY_FILE, {}) or {}
        if history.get("mode") != "live":
            log("Historique simulé effacé (bascule vers les vrais prix).")
            save_json(HISTORY_FILE, {"mode": "live", "last_offers_ts": 0, "products": {}}, compact=True)
            save_json(SIM_STATE_FILE, {}, compact=True)
    else:
        mode = "simulation"
        log("Mode DÉMO : aucune URL de flux dans config/feeds.json → prix simulés.")
        offers = run_simulation(products, settings, affiliates)

    ts = now_ts()
    for items in offers.values():
        items.sort(key=lambda o: (not o["in_stock"], o["price"]))
    save_json(OFFERS_FILE, {"generated_at": ts, "generated_at_iso": iso(ts), "mode": mode, "products": offers})
    total = sum(len(v) for v in offers.values())
    log(f"✓ {total} offres enregistrées pour {len(offers)} produits → data/offers_latest.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
