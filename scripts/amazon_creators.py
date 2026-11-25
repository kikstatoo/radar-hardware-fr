"""Connecteur Amazon Creators API (remplaçant de PA-API 5.0) : prix réels et lien exact de la fiche produit.

Activation : ajoute ces secrets au dépôt GitHub (Settings > Secrets and variables > Actions) :
  AMAZON_CREATORS_CLIENT_ID      identifiant "Credential ID" créé dans Associates Central > Creators API
  AMAZON_CREATORS_CLIENT_SECRET  secret associé
Sans ces secrets, le module est inactif et le site reste sur les autres sources.

Amazon n'ouvre l'accès à l'API qu'après 10 ventes qualifiées sur 30 jours avec ton tag partenaire.
Règles respectées : 1 requête par seconde max, 10 ASIN par requête, aucune image Amazon stockée
(seules les URL renvoyées sont utilisées à l'affichage).
"""
from __future__ import annotations

import json
import os
import time
import urllib.request
from urllib.error import HTTPError, URLError

from common import AMAZON_DOMAINS, DATA_DIR, load_json, log, product_asin, save_json, _is_placeholder

TOKEN_URL = "https://api.amazon.co.uk/auth/o2/token"      # région Europe (credentials v3.x)
API_BASE = "https://creatorsapi.amazon/catalog/v1"
ASIN_CACHE = DATA_DIR / "asin_cache.json"
RESOURCES = [
    "itemInfo.title",
    "itemInfo.externalIds",
    "images.primary.large",
    "offersV2.listings.price",
    "offersV2.listings.availability",
    "offersV2.listings.merchantInfo",
    "offersV2.listings.isBuyBoxWinner",
    "offersV2.listings.deliveryInfo",
]
MAX_LOOKUPS_PER_RUN = 25  # recherches d'ASIN manquants par passage (le reste au passage suivant)

_token = {"value": None, "exp": 0}


def credentials():
    cid = os.environ.get("AMAZON_CREATORS_CLIENT_ID", "").strip()
    sec = os.environ.get("AMAZON_CREATORS_CLIENT_SECRET", "").strip()
    return (cid, sec) if cid and sec else None


def enabled(affiliates: dict) -> bool:
    return bool(credentials()) and not _is_placeholder(affiliates.get("amazon_tag"))


def _post(url: str, body: dict, headers: dict, timeout=20) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", **headers})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _access_token() -> str:
    if _token["value"] and time.time() < _token["exp"] - 60:
        return _token["value"]
    cid, sec = credentials()
    data = _post(TOKEN_URL, {"grant_type": "client_credentials", "client_id": cid,
                             "client_secret": sec, "scope": "creatorsapi::default"}, {})
    _token["value"] = data["access_token"]
    _token["exp"] = time.time() + int(data.get("expires_in", 3600))
    return _token["value"]


def _call(operation: str, marketplace: str, body: dict) -> dict:
    time.sleep(1.05)  # quota de base : 1 requête / seconde
    return _post(f"{API_BASE}/{operation}", {"marketplace": marketplace, **body},
                 {"Authorization": f"Bearer {_access_token()}", "x-marketplace": marketplace})


def _get(d, *path):
    for k in path:
        if isinstance(d, dict):
            d = d.get(k, d.get(k[:1].upper() + k[1:]))
        else:
            return None
    return d


def _items(resp: dict) -> list:
    for path in (("itemsResult", "items"), ("searchResult", "items"), ("items",)):
        v = _get(resp, *path)
        if isinstance(v, list):
            return v
    return []


def _buybox(item: dict):
    listings = _get(item, "offersV2", "listings") or []
    if not listings:
        return None
    return next((l for l in listings if _get(l, "isBuyBoxWinner")), listings[0])


def _amount(listing: dict):
    for path in (("price", "money", "amount"), ("price", "amount"), ("price", "displayAmount")):
        v = _get(listing, *path)
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, str):
            try:
                return float(v.replace("€", "").replace(" ", "").replace(" ", "").replace(",", "."))
            except ValueError:
                pass
    return None


def _resolve_missing(products: list, merchant_key: str, marketplace: str, tag: str, cache: dict) -> None:
    """Trouve l'ASIN des produits sans ASIN (recherche par EAN, sinon par nom) et le met en cache."""
    budget = MAX_LOOKUPS_PER_RUN
    for p in products:
        key = f"{merchant_key}:{p['slug']}"
        if product_asin(p, merchant_key) or key in cache or budget <= 0:
            continue
        budget -= 1
        query = p.get("ean") or p.get("search_query") or p["name"]
        try:
            resp = _call("searchItems", marketplace, {"keywords": query, "searchIndex": "Computers",
                                                      "itemCount": 5, "partnerTag": tag,
                                                      "resources": ["itemInfo.title", "itemInfo.externalIds"]})
        except (HTTPError, URLError, TimeoutError, ValueError) as e:
            log(f"  Amazon searchItems {p['slug']} : {e}")
            continue
        found = ""
        want_ean = (p.get("ean") or "").lstrip("0")
        must = [k.lower() for k in p.get("match_keywords", [])]
        avoid = [k.lower() for k in p.get("exclude_keywords", [])]
        for it in _items(resp):
            title = str(_get(it, "itemInfo", "title", "displayValue") or "").lower()
            eans = _get(it, "itemInfo", "externalIds", "eaNs", "displayValues") or \
                _get(it, "itemInfo", "externalIds", "eans", "displayValues") or []
            if want_ean and any(str(e).lstrip("0") == want_ean for e in eans):
                found = it.get("asin", ""); break
            if not want_ean and all(k in title for k in must) and not any(k in title for k in avoid):
                found = it.get("asin", ""); break
        cache[key] = found or None  # None = rien de fiable : on ne retente pas à chaque passage


def fetch_offers(products: list, affiliates: dict) -> dict:
    """Offres Amazon réelles {slug: [offer]} pour chaque place de marché Amazon configurée."""
    if not enabled(affiliates):
        return {}
    merchants = affiliates.get("merchants", {})
    cache = load_json(ASIN_CACHE, {}) or {}
    out: dict = {}
    for mkey, domain in AMAZON_DOMAINS.items():
        m = merchants.get(mkey)
        if not m:
            continue
        tag = affiliates.get(m.get("amazon_tag_key", "amazon_tag"), "")
        if _is_placeholder(tag):
            continue
        scope = [p for p in products if mkey in p.get("merchants", [])]
        try:
            _resolve_missing(scope, mkey, domain, tag, cache)
        except Exception as e:  # le reste du pipeline ne doit jamais tomber à cause d'Amazon
            log(f"ATTENTION - résolution ASIN {mkey} : {e}")
        asin_to_slug = {}
        for p in scope:
            a = product_asin(p, mkey) or cache.get(f"{mkey}:{p['slug']}")
            if a:
                asin_to_slug[a] = p["slug"]
        asins = list(asin_to_slug)
        for i in range(0, len(asins), 10):
            batch = asins[i:i + 10]
            try:
                resp = _call("getItems", domain, {"itemIds": batch, "itemIdType": "ASIN",
                                                  "partnerTag": tag, "resources": RESOURCES})
            except (HTTPError, URLError, TimeoutError, ValueError) as e:
                log(f"  Amazon getItems {mkey} : {e}")
                continue
            for it in _items(resp):
                slug = asin_to_slug.get(it.get("asin"))
                lst = _buybox(it)
                price = _amount(lst) if lst else None
                if not slug or price is None:
                    continue
                avail = str(_get(lst, "availability", "type") or "").upper()
                seller = str(_get(lst, "merchantInfo", "name") or "")
                out.setdefault(slug, []).append({
                    "merchant": mkey, "price": round(price, 2),
                    "in_stock": avail not in {"OUT_OF_STOCK", "UNAVAILABLE"},
                    "url": it.get("detailPageURL") or f"https://{domain}/dp/{it['asin']}?tag={tag}",
                    "link": "product", "source": "amazon-api", "asin": it["asin"],
                    "title": _get(it, "itemInfo", "title", "displayValue") or "",
                    "seller": seller,
                    "free_shipping": bool(_get(lst, "deliveryInfo", "isFreeShippingEligible")),
                })
    save_json(ASIN_CACHE, cache)
    log(f"Amazon Creators API : {sum(len(v) for v in out.values())} offres réelles.")
    return out
