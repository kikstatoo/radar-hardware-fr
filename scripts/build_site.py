"""
build_site.py — Moteur d'analyse + générateur du site statique (étape 2 du pipeline).

1. Ajoute le meilleur prix du moment à data/price_history.json (30 jours / 720 points max).
2. Calcule les statistiques : prix actuel, moyenne et médiane 30 j, plus bas historique,
   réduction réelle, score « Vraie Promo » (0-100), ratio prix / performance.
3. Génère les graphiques d'historique (matplotlib) et les vignettes sociales 1200x675 (Pillow).
4. Produit tout le site dans dist/ : accueil, catégories, fiches produits, comparatifs
   « Versus », JSON-LD Schema.org, sitemap.xml, robots.txt, 404.
5. Écrit data/site_stats.json, lu ensuite par notify.py.
"""
from __future__ import annotations

import json
import shutil
import statistics
import sys
from datetime import datetime, timezone
from itertools import combinations

import matplotlib

matplotlib.use("Agg")  # rendu sans écran (GitHub Actions, serveur)
from jinja2 import Environment, FileSystemLoader, select_autoescape  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from visuals import icon_svg, product_svg  # noqa: E402

from common import (ROOT, DIST_DIR, HISTORY_FILE, OFFERS_FILE, SITE_STATS_FILE, STATIC_DIR,  # noqa: E402
                    TEMPLATES_DIR, date_fr, fmt_pct, fmt_price, get_base_url, iso, load_affiliates,
                    load_catalog, load_json, load_settings, log, month_year_fr, now_ts, save_json)

try:
    from zoneinfo import ZoneInfo
    PARIS = ZoneInfo("Europe/Paris")
except Exception:  # tzdata absent : on reste en UTC
    PARIS = timezone.utc

COLORS = {
    "bg": "#090B10", "surface": "#111622", "border": "#1E293B", "text": "#E2E8F0",
    "muted": "#94A3B8", "green": "#00E599", "cyan": "#38BDF8", "amber": "#F59E0B", "rose": "#F43F5E",
}


# =============================================================================
# 1. Historique
# =============================================================================
def update_history(history: dict, offers_doc: dict, products: list[dict], settings: dict) -> dict:
    """Ajoute un point horodaté par produit (si les offres sont plus récentes que le dernier point)."""
    mode = offers_doc.get("mode", "simulation")
    if history.get("mode") != mode:
        history = {"mode": mode, "last_offers_ts": 0, "products": {}}
    ts = int(offers_doc.get("generated_at", now_ts()))
    max_points = int(settings.get("history_max_points", 720))
    horizon = ts - int(settings.get("history_days", 30)) * 86400
    append = ts > int(history.get("last_offers_ts", 0))
    for product in products:
        entry = history["products"].setdefault(product["slug"], {"points": [], "all_time_min": None})
        if append:
            offers = offers_doc.get("products", {}).get(product["slug"], [])
            prices = [o["price"] for o in offers if o.get("in_stock") and not o.get("stale")]
            price = min(prices) if prices else None
            entry["points"].append([ts, price])
            atl = entry.get("all_time_min")
            if price is not None and (atl is None or price < atl["price"]):
                entry["all_time_min"] = {"price": price, "ts": ts}
        entry["points"] = [p for p in entry["points"] if p[0] >= horizon][-max_points:]
    if append:
        history["last_offers_ts"] = ts
    return history


# =============================================================================
# 2. Statistiques
# =============================================================================
def compute_stats(product: dict, offers: list[dict], entry: dict, settings: dict) -> dict:
    threshold = float(settings.get("deal_threshold_percent", 8.0))
    in_stock = [o for o in offers if o.get("in_stock")]
    best = min(in_stock, key=lambda o: o["price"]) if in_stock else None
    current = best["price"] if best else None
    prices = [p for _, p in entry.get("points", []) if p is not None]
    atl = (entry.get("all_time_min") or {})
    s = {
        "price_current": current,
        "best_offer": best,
        "offer_count": len(offers),
        "in_stock_count": len(in_stock),
        "price_high_now": max((o["price"] for o in in_stock), default=None),
        "price_avg_30d": round(statistics.fmean(prices), 2) if prices else current,
        "price_median_30d": round(statistics.median(prices), 2) if prices else current,
        "price_max_30d": max(prices) if prices else current,
        "price_min_30d": min(prices) if prices else current,
        "price_min_all_time": atl.get("price", current),
        "price_min_all_time_date": date_fr(atl["ts"]) if atl.get("ts") else None,
        "points": len(prices),
    }
    if current is None:
        s.update(discount_vs_avg=0.0, discount_vs_median=0.0, true_deal_score=0, is_true_deal=False,
                 is_all_time_low=False, savings_eur=0.0, price_per_perf=None, perf_per_100eur=None,
                 trend_7d=0.0, verdict="Indisponible", verdict_level="none",
                 light="none", light_label="Indisponible")
        return s

    avg, med, atl_price = s["price_avg_30d"], s["price_median_30d"], s["price_min_all_time"] or current
    s["discount_vs_avg"] = round((avg - current) / avg * 100, 1) if avg else 0.0
    s["discount_vs_median"] = round((med - current) / med * 100, 1) if med else 0.0
    s["savings_eur"] = round(max(0.0, avg - current), 2)
    s["is_true_deal"] = s["discount_vs_avg"] >= threshold
    s["is_all_time_low"] = s["is_true_deal"] and current <= atl_price + 0.01

    # --- Score Anti-Arnaque / Vraie Promo (0-100) ---------------------------
    # 55 pts : écart réel sous la médiane 30 j (20 % sous la médiane = score plein)
    s1 = min(55.0, max(0.0, s["discount_vs_median"]) * 55 / 20)
    # 30 pts : proximité du plus bas historique
    gap = (current / atl_price - 1) * 100 if atl_price else 0
    s2 = 30.0 if gap <= 0.5 else max(0.0, 30 - gap * 3)
    # 15 pts : anti-gonflage — part du mois où le prix était réellement plus élevé
    s3 = 15.0 * (sum(1 for p in prices if p >= current * 1.03) / len(prices)) if prices else 0.0
    score = s1 + s2 + s3
    if s["discount_vs_avg"] <= 0:
        score = min(score, 35)  # pas de vraie baisse : plafonné
    s["true_deal_score"] = int(round(max(0, min(100, score))))

    recent = [p for t, p in entry.get("points", [])[-168:] if p is not None]
    s["trend_7d"] = round((current - statistics.fmean(recent)) / statistics.fmean(recent) * 100, 1) if recent else 0.0
    perf = float(product.get("perf_score") or 0)
    s["price_per_perf"] = round(current / perf, 2) if perf else None
    s["perf_per_100eur"] = round(perf / current * 100, 2) if perf else None

    # --- Verdict « feu tricolore » (lisible par un débutant) ---------------
    if s["discount_vs_avg"] >= threshold or current <= atl_price + 0.01:
        s["light"], s["light_label"] = "green", "Meilleur moment pour acheter"
    elif current > avg * 1.04:
        s["light"], s["light_label"] = "red", "Prix élevé"
    else:
        s["light"], s["light_label"] = "yellow", "Prix standard"

    sc = s["true_deal_score"]
    if sc >= 75:
        s["verdict"], s["verdict_level"] = "Excellent moment pour acheter", "great"
    elif sc >= 50:
        s["verdict"], s["verdict_level"] = "Bon prix", "good"
    elif sc >= 30:
        s["verdict"], s["verdict_level"] = "Prix dans la moyenne", "fair"
    else:
        s["verdict"], s["verdict_level"] = "Mieux vaut attendre", "wait"
    return s


# =============================================================================
# 3. Graphiques & vignettes sociales
# =============================================================================
def _load_font(kind: str, size: int):
    """Polices DejaVu fournies avec matplotlib : disponibles partout, y compris Windows."""
    name = {"bold": "DejaVuSans-Bold.ttf", "regular": "DejaVuSans.ttf", "mono": "DejaVuSansMono-Bold.ttf"}[kind]
    path = matplotlib.get_data_path() + "/fonts/ttf/" + name
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default()


def chart_svg(entry: dict, stats: dict) -> tuple[str, str]:
    """Graphique SVG vectoriel (net à toutes les tailles) + données JSON pour l'infobulle."""
    pts = [(t, p) for t, p in entry.get("points", []) if p is not None]
    if len(pts) < 2:
        return "", "[]"
    step = max(1, len(pts) // 240)  # ~240 points suffisent pour 30 jours
    pts = pts[::step] + ([pts[-1]] if (len(pts) - 1) % step else [])
    W, H, L, R, T, B = 900, 300, 64, 16, 16, 34
    ys = [p for _, p in pts]
    lo, hi = min(ys), max(ys)
    pad = max((hi - lo) * 0.18, hi * 0.01)
    lo, hi = lo - pad, hi + pad
    t0, t1 = pts[0][0], pts[-1][0]
    X = lambda t: L + (t - t0) / max(1, t1 - t0) * (W - L - R)
    Y = lambda v: T + (hi - v) / (hi - lo) * (H - T - B)
    line = " ".join(f"{X(t):.1f},{Y(v):.1f}" for t, v in pts)
    area = f"{X(t0):.1f},{H - B} {line} {X(t1):.1f},{H - B}"
    grid = ""
    for i in range(5):
        v = lo + (hi - lo) * i / 4
        grid += (f'<line x1="{L}" x2="{W - R}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" class="ch-grid"/>'
                 f'<text x="{L - 8}" y="{Y(v) + 4:.1f}" text-anchor="end" class="ch-ax">{v:,.0f} €</text>'.replace(",", " "))
    for i in range(6):
        t = t0 + (t1 - t0) * i / 5
        d = datetime.fromtimestamp(t, PARIS)
        grid += f'<text x="{X(t):.1f}" y="{H - 10}" text-anchor="middle" class="ch-ax">{d:%d/%m}</text>'
    avg = stats.get("price_avg_30d")
    avg_line = (f'<line x1="{L}" x2="{W - R}" y1="{Y(avg):.1f}" y2="{Y(avg):.1f}" class="ch-avg"/>'
                f'<text x="{W - R}" y="{Y(avg) - 6:.1f}" text-anchor="end" class="ch-avg-t">Moyenne 30 j</text>') if avg else ""
    i_min = min(range(len(ys)), key=lambda i: ys[i])
    svg = (f'<svg class="chart" viewBox="0 0 {W} {H}" preserveAspectRatio="none" role="img" '
           f'aria-label="Évolution du meilleur prix sur 30 jours" data-l="{L}" data-r="{R}" data-t="{T}" data-b="{B}" '
           f'data-lo="{lo:.2f}" data-hi="{hi:.2f}">'
           f'<defs><linearGradient id="chg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#10B981" stop-opacity=".28"/>'
           f'<stop offset="1" stop-color="#10B981" stop-opacity="0"/></linearGradient></defs>'
           f'{grid}<polygon points="{area}" fill="url(#chg)"/>{avg_line}'
           f'<polyline points="{line}" class="ch-line"/>'
           f'<circle cx="{X(pts[i_min][0]):.1f}" cy="{Y(ys[i_min]):.1f}" r="4.5" class="ch-min"/>'
           f'<circle cx="{X(pts[-1][0]):.1f}" cy="{Y(ys[-1]):.1f}" r="4.5" class="ch-last"/>'
           f'<line class="ch-cursor" x1="0" x2="0" y1="{T}" y2="{H - B}" visibility="hidden"/>'
           f'<circle class="ch-dot" r="5" cx="0" cy="0" visibility="hidden"/></svg>')
    data = json.dumps([[t, round(v, 2)] for t, v in pts], separators=(",", ":"))
    return svg, data


def _wrap(draw, text: str, font, max_width: int) -> list[str]:
    words, lines, line = text.split(), [], ""
    for w in words:
        test = f"{line} {w}".strip()
        if draw.textlength(test, font=font) <= max_width:
            line = test
        else:
            if line:
                lines.append(line)
            line = w
    if line:
        lines.append(line)
    return lines


def make_social_image(product: dict, entry: dict, stats: dict, merchant_name: str, site_name: str, out_path) -> None:
    W, H = 1200, 675
    img = Image.new("RGB", (W, H), COLORS["bg"])
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((40, 40, W - 40, H - 40), radius=28, fill=COLORS["surface"], outline=COLORS["border"], width=2)
    d.text((84, 78), site_name.upper(), font=_load_font("bold", 26), fill=COLORS["cyan"])
    d.text((84, 112), "Comparateur de prix hardware PC Gamer", font=_load_font("regular", 20), fill=COLORS["muted"])

    # Badge
    if stats.get("is_all_time_low"):
        badge, color = "PLUS BAS HISTORIQUE", COLORS["amber"]
    elif stats.get("is_true_deal"):
        badge, color = f"VRAIE PROMO -{stats['discount_vs_avg']:.0f} %", COLORS["rose"]
    else:
        badge, color = "SUIVI DE PRIX", COLORS["cyan"]
    bf = _load_font("bold", 24)
    bw = d.textlength(badge, font=bf)
    d.rounded_rectangle((W - 84 - bw - 36, 76, W - 84, 124), radius=24, fill=color)
    d.text((W - 84 - bw - 18, 87), badge, font=bf, fill=COLORS["bg"])

    # Nom du produit
    nf = _load_font("bold", 48)
    y = 176
    for line in _wrap(d, product["name"], nf, W - 168)[:2]:
        d.text((84, y), line, font=nf, fill=COLORS["text"])
        y += 60

    # Prix
    price = stats.get("price_current")
    pf = _load_font("mono", 110)
    price_txt = fmt_price(price).replace(" ", " ").replace(" ", " ")
    d.text((80, y + 24), price_txt, font=pf, fill=COLORS["green"])
    old = stats.get("price_avg_30d")
    of = _load_font("mono", 40)
    if old and price and old > price:
        old_txt = fmt_price(old).replace(" ", " ").replace(" ", " ")
        ox, oy = 88, y + 160
        d.text((ox, oy), old_txt, font=of, fill=COLORS["muted"])
        ow = d.textlength(old_txt, font=of)
        d.line((ox - 4, oy + 24, ox + ow + 4, oy + 24), fill=COLORS["rose"], width=4)
        d.text((ox + ow + 24, oy + 6), f"moy. 30 j  •  -{fmt_price(stats['savings_eur'])}".replace(" ", " ").replace(" ", " "),
               font=_load_font("regular", 28), fill=COLORS["muted"])
    d.text((88, H - 112), f"Meilleur prix chez {merchant_name}", font=_load_font("bold", 28), fill=COLORS["text"])

    # Mini-courbe
    ys = [p for _, p in entry.get("points", []) if p is not None][-240:]
    if len(ys) > 2:
        x0, y0, x1, y1 = W - 470, H - 250, W - 84, H - 84
        lo, hi = min(ys), max(ys)
        span = (hi - lo) or 1
        coords = [(x0 + i * (x1 - x0) / (len(ys) - 1), y1 - (v - lo) / span * (y1 - y0)) for i, v in enumerate(ys)]
        d.line(coords, fill=COLORS["cyan"], width=4, joint="curve")
        cx, cy = coords[-1]
        d.ellipse((cx - 8, cy - 8, cx + 8, cy + 8), fill=COLORS["green"])
    img.save(out_path, optimize=True)


def sparkline_svg(entry: dict, w: int = 120, h: int = 36) -> str:
    """Mini-courbe SVG inline (ultra légère, idéale pour Lighthouse)."""
    ys = [p for _, p in entry.get("points", []) if p is not None][-240:]
    if len(ys) < 2:
        return ""
    step = max(1, len(ys) // 60)
    ys = ys[::step] + ([ys[-1]] if (len(ys) - 1) % step else [])
    lo, hi = min(ys), max(ys)
    span = (hi - lo) or 1
    pts = " ".join(f"{i * w / (len(ys) - 1):.1f},{h - 3 - (v - lo) / span * (h - 6):.1f}" for i, v in enumerate(ys))
    return (f'<svg class="spark" viewBox="0 0 {w} {h}" width="{w}" height="{h}" aria-hidden="true" focusable="false">'
            f'<polyline fill="none" stroke="#38BDF8" stroke-width="2" stroke-linejoin="round" '
            f'stroke-linecap="round" points="{pts}"/></svg>')


# =============================================================================
# 4. Contenus SEO générés par templates (sans IA)
# =============================================================================
def seo_paragraphs(p: dict, s: dict, cat: dict, merchant_name: str) -> list[str]:
    name, cur = p["name"], s.get("price_current")
    if cur is None:
        return [f"Le {name} est actuellement en rupture chez l'ensemble des marchands suivis. "
                f"Notre radar vérifie les stocks toutes les heures : revenez bientôt ou rejoignez nos alertes."]
    avg, d = s["price_avg_30d"], s["discount_vs_avg"]
    out = []
    if d >= 0.5:
        out.append(f"Le {name} est actuellement affiché à {fmt_price(cur)} livré en France chez {merchant_name}, soit "
                   f"{fmt_pct(d, 1)} en dessous de sa moyenne des 30 derniers jours ({fmt_price(avg)}).")
    elif d <= -0.5:
        out.append(f"Le {name} est actuellement affiché à {fmt_price(cur)} chez {merchant_name}, soit "
                   f"{fmt_pct(-d, 1)} au-dessus de sa moyenne des 30 derniers jours ({fmt_price(avg)}).")
    else:
        out.append(f"Le {name} est actuellement affiché à {fmt_price(cur)} chez {merchant_name}, "
                   f"un tarif aligné sur sa moyenne des 30 derniers jours ({fmt_price(avg)}).")
    atl = s["price_min_all_time"]
    if s["is_all_time_low"]:
        out.append(f"C'est le plus bas prix jamais relevé par notre radar pour ce {cat['singular']} : "
                   f"une occasion rare, le score Vraie Promo atteint {s['true_deal_score']}/100.")
    elif s["is_true_deal"]:
        out.append(f"Il s'agit d'une vraie promotion : la baisse dépasse notre seuil anti-gonflage et le "
                   f"plus bas historique reste à {fmt_price(atl)}" +
                   (f" (relevé le {s['price_min_all_time_date']})." if s.get("price_min_all_time_date") else "."))
    else:
        out.append(f"Le plus bas historique enregistré est de {fmt_price(atl)}" +
                   (f" (le {s['price_min_all_time_date']})" if s.get("price_min_all_time_date") else "") +
                   f". Avec un score Vraie Promo de {s['true_deal_score']}/100, notre verdict : "
                   f"« {s['light_label'].lower()} ».")
    t = s["trend_7d"]
    if t <= -2:
        out.append(f"La tendance de la semaine est à la baisse ({fmt_pct(t, 1)} par rapport à la moyenne 7 jours).")
    elif t >= 2:
        out.append(f"Attention, le prix remonte cette semaine (+{fmt_pct(t, 1)} par rapport à la moyenne 7 jours).")
    else:
        out.append("Le prix est resté stable ces 7 derniers jours.")
    if s.get("price_per_perf"):
        out.append(f"Côté rentabilité, il revient à {fmt_price(s['price_per_perf'])} par point de performance "
                   f"({cat['perf_label']}), comparé chez {s['offer_count']} marchands français et européens, livraison en France comprise.")
    return out


def faq_items(p: dict, s: dict, merchant_name: str, best_cat: dict | None) -> list[tuple[str, str]]:
    name, cur = p["name"], s.get("price_current")
    items = []
    if cur is not None:
        items.append((f"Quel est le meilleur prix pour le {name} ?",
                      f"Le meilleur prix actuel du {name} est de {fmt_price(cur)} chez {merchant_name}. "
                      f"Le prix moyen sur 30 jours est de {fmt_price(s['price_avg_30d'])} et le plus bas historique "
                      f"de {fmt_price(s['price_min_all_time'])}."))
        if s["light"] == "green":
            ans = (f"Oui, notre verdict est « Meilleur moment pour acheter ». Le prix actuel est {fmt_pct(s['discount_vs_avg'], 1)} sous la moyenne des 30 derniers jours, "
                   f"avec un score Vraie Promo de {s['true_deal_score']}/100.")
        elif s["light"] == "yellow":
            ans = (f"Prix standard : c'est un tarif dans la fourchette habituelle, légèrement de ces 30 derniers jours "
                   f"(moyenne {fmt_price(s['price_avg_30d'])}), mais pas une vraie promo. Score : {s['true_deal_score']}/100.")
        else:
            ans = (f"Prix élevé : mieux vaut attendre, le prix est gonflé de plus de 4 % par rapport à la moyenne 30 jours "
                   f"({fmt_price(s['price_avg_30d'])}). Mieux vaut patienter ou activer une alerte.")
        items.append((f"Est-ce le bon moment pour acheter le {name} ?", ans))
        items.append((f"Le {name} a-t-il déjà été moins cher ?",
                      f"Le plus bas prix relevé par notre radar est de {fmt_price(s['price_min_all_time'])}" +
                      (f", le {s['price_min_all_time_date']}." if s.get("price_min_all_time_date") else ".")))
    items.append((f"Chez quels marchands acheter le {name} ?",
                  f"Nous comparons {s['offer_count']} offres ({', '.join(sorted({o for o in p.get('_merchant_names', [])}))}) "
                  f"et mettons à jour les prix et les stocks toutes les heures."))
    if best_cat and best_cat["slug"] != p["slug"]:
        items.append((f"Quel est le meilleur rapport prix / performance de la catégorie ?",
                      f"En ce moment, c'est le {best_cat['name']} qui offre le meilleur ratio prix / performance "
                      f"de sa catégorie."))
    return items


def shipping_label(ship) -> tuple[str, bool]:
    if ship is None:
        return "Port : voir le site", False
    if ship == 0:
        return "Livraison FR incluse", True
    return f"+{fmt_price(ship)}", False


def json_ld(data) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


# =============================================================================
# 5. Construction du site
# =============================================================================
def select_versus(products: list[dict], settings: dict) -> list[tuple[dict, dict]]:
    """Duels pertinents au sein de chaque catégorie, choisis sur le prix de référence
    (et non le prix du jour) pour que les URLs restent stables pour Google."""
    seo = settings.get("seo", {})
    max_ratio = float(seo.get("versus_max_price_ratio", 1.6))
    per_cat = int(seo.get("versus_max_per_category", 20))
    by_cat: dict[str, list[dict]] = {}
    for p in products:
        if p.get("perf_score"):  # pas de duel pour boîtiers, alimentations, refroidissement
            by_cat.setdefault(p["category"], []).append(p)
    pairs = []
    for items in by_cat.values():
        cands = []
        for a, b in combinations(items, 2):
            ratio = max(a["price_ref"], b["price_ref"]) / min(a["price_ref"], b["price_ref"])
            if ratio <= max_ratio:
                cands.append((ratio, a, b))
        cands.sort(key=lambda c: c[0])
        pairs.extend((a, b) for _, a, b in cands[:per_cat])
    return pairs


def main() -> int:
    settings, affiliates = load_settings(), load_affiliates()
    catalog = load_catalog()
    products, categories = catalog.get("products", []), catalog.get("categories", {})
    offers_doc = load_json(OFFERS_FILE, None)
    if not offers_doc:
        log("ERREUR - data/offers_latest.json absent : lance d'abord scripts/fetch_prices.py")
        return 1

    mode = offers_doc.get("mode", "simulation")
    demo = mode != "live"
    site_name = affiliates.get("site_name", "Radar Hardware Europe")
    base_url = get_base_url(affiliates)
    merchants = affiliates.get("merchants", {})
    mname = lambda k: merchants.get(k, {}).get("name", "Bon plan" if k == "bonplan" else k.capitalize())

    # --- Historique & stats ---
    history = update_history(load_json(HISTORY_FILE, {}) or {}, offers_doc, products, settings)
    save_json(HISTORY_FILE, history, compact=True)
    log(f"OK - Historique mis à jour ({len(products)} produits)")

    build_ts = now_ts()
    build_dt = datetime.fromtimestamp(build_ts, PARIS)
    updated_label = f"{build_dt.day} {month_year_fr(build_dt)} à {build_dt:%H}h{build_dt:%M}"

    # --- Préparation du dossier dist/ ---
    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR)
    for sub in ("assets/social", "assets/products", "assets/css", "assets/js", "produit", "categorie", "comparatif"):
        (DIST_DIR / sub).mkdir(parents=True, exist_ok=True)
    shutil.copy(STATIC_DIR / "css" / "style.css", DIST_DIR / "assets/css/style.css")
    shutil.copy(STATIC_DIR / "js" / "app.js", DIST_DIR / "assets/js/app.js")
    shutil.copy(STATIC_DIR / "js" / "configurator.js", DIST_DIR / "assets/js/configurator.js")
    cached_dir = ROOT / "assets" / "products"  # images mises en cache par download_images.py
    shutil.copy(STATIC_DIR / "favicon.svg", DIST_DIR / "favicon.svg")
    inline_css = (STATIC_DIR / "css" / "style.css").read_text(encoding="utf-8")

    items = []
    for p in products:
        offers = offers_doc.get("products", {}).get(p["slug"], [])
        entry = history["products"].get(p["slug"], {"points": [], "all_time_min": None})
        s = compute_stats(p, offers, entry, settings)
        cat = categories.get(p["category"], {"label": p["category"], "slug": p["category"],
                                              "singular": "composant", "perf_label": "Indice"})
        bo = s["best_offer"]
        best_merchant = mname(bo["merchant"]) if bo else "—"
        p["_merchant_names"] = [mname(m) for m in p.get("merchants", [])]
        offers_view = []
        for o in sorted(offers, key=lambda o: (not o["in_stock"], o["price"])):
            m = merchants.get(o["merchant"], {})
            label, free = shipping_label(o.get("shipping"))
            offers_view.append({**o, "merchant_name": mname(o["merchant"]), "country": m.get("country", "FR"),
                                "ship_label": label, "ship_free": free,
                                "item_price": o.get("item_price", o["price"]),
                                "saving": round(s["price_avg_30d"] - o["price"], 2) if s["price_avg_30d"] and o["price"] < s["price_avg_30d"] - 0.5 else 0,
                                "color": m.get("color", "#38BDF8"), "is_best": bo is not None and o is bo})
        fr_offers = [o for o in offers_view if o["in_stock"] and o["country"] == "FR"]
        best_fr = min(fr_offers, key=lambda o: o["price"]) if fr_offers else None
        best_view = next((o for o in offers_view if o["is_best"]), None)
        # Image : copie locale en cache (servie par GitHub Pages) sinon visuel neutre
        cached = cached_dir / f"{p['slug']}.webp"
        if cached.exists():
            shutil.copy(cached, DIST_DIR / "assets/products" / cached.name)
            image = f"assets/products/{cached.name}"
        else:
            (DIST_DIR / "assets/products" / f"{p['slug']}.svg").write_text(product_svg(p), encoding="utf-8")
            image = f"assets/products/{p['slug']}.svg"
        chart, chart_data = chart_svg(entry, s)
        items.append({"p": p, "s": s, "cat": cat, "offers": offers_view, "entry": entry,
                      "best_merchant": best_merchant, "best_view": best_view, "best_fr": best_fr,
                      "image": image, "has_photo": cached.exists(), "spark": sparkline_svg(entry),
                      "chart": chart, "chart_data": chart_data,
                      "url": f"produit/{p['slug']}.html"})
        make_social_image(p, entry, s, best_merchant, site_name, DIST_DIR / "assets/social" / f"{p['slug']}-alert.png")
    log(f"OK - {len(items)} vignettes sociales, {sum(1 for i in items if i['has_photo'])} photos produits en cache")

    by_slug = {it["p"]["slug"]: it for it in items}
    by_cat: dict[str, list[dict]] = {}
    for it in items:
        by_cat.setdefault(it["p"]["category"], []).append(it)
    best_ratio = {}
    for ck, lst in by_cat.items():
        ranked = sorted([i for i in lst if i["s"]["price_per_perf"]], key=lambda i: i["s"]["price_per_perf"])
        best = ranked[0]["s"]["price_per_perf"] if ranked else None
        for rank, it in enumerate(ranked, 1):
            it["ratio_rank"] = rank
            it["ratio_index"] = round(it["s"]["price_per_perf"] / best, 3)
        best_ratio[ck] = ranked[0]["p"] if ranked else None

    # --- Versus ---
    versus = []
    for a, b in select_versus(products, settings):
        ia, ib = by_slug[a["slug"]], by_slug[b["slug"]]
        slug = f"{a['slug']}-vs-{b['slug']}"
        ra, rb = ia["s"]["perf_per_100eur"] or 0, ib["s"]["perf_per_100eur"] or 0
        winner = ia if ra >= rb else ib
        faster = ia if a["perf_score"] >= b["perf_score"] else ib
        spec_keys = list(dict.fromkeys(list(a["specs"].keys()) + list(b["specs"].keys())))
        versus.append({"slug": slug, "a": ia, "b": ib, "winner": winner, "faster": faster,
                       "spec_keys": spec_keys, "url": f"comparatif/{slug}.html",
                       "title": f"{a['name']} vs {b['name']}"})
    vs_by_product: dict[str, list[dict]] = {}
    for v in versus:
        vs_by_product.setdefault(v["a"]["p"]["slug"], []).append(v)
        vs_by_product.setdefault(v["b"]["p"]["slug"], []).append(v)

    # --- Hero : Top 4 des plus grosses baisses réelles ---
    with_price = [i for i in items if i["s"]["price_current"] is not None]
    hero = sorted(with_price, key=lambda i: (i["s"]["is_true_deal"], i["s"]["discount_vs_avg"]), reverse=True)[:6]
    deals_count = sum(1 for i in items if i["s"]["is_true_deal"])

    # --- Rendu Jinja ---
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=select_autoescape(["html"]),
                      trim_blocks=True, lstrip_blocks=True)
    env.filters["price"] = fmt_price
    env.filters["pct"] = fmt_pct
    env.filters["num"] = lambda v, d=1: "—" if v is None else f"{v:.{d}f}".replace(".", ",")
    env.globals["icon"] = icon_svg
    common_ctx = {
        "site_name": site_name, "base_url": base_url, "demo": demo, "noindex": demo and settings.get("seo", {}).get("noindex_in_simulation_mode", True),
        "updated_label": updated_label, "updated_iso": iso(build_ts), "month_year": month_year_fr(build_dt),
        "categories": categories, "inline_css": inline_css, "year": build_dt.year,
        "threshold": settings.get("deal_threshold_percent", 8.0),
        "amazon_enabled": bool(affiliates.get("amazon_tag")),
    }
    common_ctx["search_index"] = json_ld([{"n": i["p"]["name"], "u": i["url"], "c": i["cat"]["label"], "i": i["image"],
                                           "p": fmt_price(i["s"]["price_current"]), "l": i["s"]["light"]} for i in items])
    common_ctx["amazon_enabled"] = any(affiliates.get(k) for k in ("amazon_tag", "amazon_tag_de", "amazon_tag_es"))
    common_ctx["merchant_count"] = len(merchants)
    common_ctx["merchant_list"] = [{"name": m["name"], "country": m.get("country", "FR"), "color": m.get("color")}
                                   for m in merchants.values()]
    common_ctx["product_count"] = len(items)
    pages = []

    def render(template: str, rel_path: str, depth: int, **ctx):
        root = ctx.pop("root", "../" * depth)
        html = env.get_template(template).render(**common_ctx, root=root,
                                                 canonical=f"{base_url}/{rel_path}".replace("/index.html", "/"), **ctx)
        out = DIST_DIR / rel_path
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(html, encoding="utf-8")
        pages.append(rel_path)

    brands = sorted({i["p"]["brand"] for i in items})
    def top_price(lst):
        return max((o["price"] for i in lst for o in (i["best_view"], i["best_fr"]) if o), default=1000)
    max_price = top_price(items)
    render("index.html", "index.html", 0, items=items, hero=hero, brands=brands, max_price=int(max_price // 10 + 1) * 10,
           deals_count=deals_count, versus=versus[:12], by_cat=by_cat,
           page_title="Comparateur Prix Hardware PC Gamer France & Europe - Meilleurs Tarifs & Historique",
           meta_description=(f"Comparez les prix livrés en France de {len(items)} composants PC (processeurs, cartes graphiques, RAM, SSD, "
                             f"cartes mères, boîtiers, alimentations) chez {len(merchants)} marchands français et européens. Configurateur PC, "
                             f"Historique 30 jours et détection des vraies promos ({month_year_fr(build_dt)})."),
           og_image=f"{base_url}/assets/social/{hero[0]['p']['slug']}-alert.png" if hero else None)

    for ck, cat in categories.items():
        lst = by_cat.get(ck, [])
        has_perf = bool(cat.get("perf_label"))
        ranked = sorted(lst, key=lambda i: (i["s"]["price_per_perf"] or 1e9) if has_perf else (i["s"]["price_current"] or 1e9))
        cat_brands = sorted({i["p"]["brand"] for i in lst})
        render("category.html", f"categorie/{cat['slug']}.html", 1, cat=cat, cat_key=ck, items=lst, ranked=ranked, has_perf=has_perf,
               brands=cat_brands, max_price=int(top_price(lst) // 10 + 1) * 10,
               versus=[v for v in versus if v["a"]["p"]["category"] == ck],
               page_title=f"{cat['label']} : comparatif des prix en France et en Europe ({month_year_fr(build_dt)}) | {site_name}",
               meta_description=(f"{len(lst)} {cat['label'].lower()} comparés au meilleur prix livré en France. "
                                 f"Prix mis à jour toutes les heures chez les marchands français, historique et vraies promos."),
               og_image=f"{base_url}/assets/social/{ranked[0]['p']['slug']}-alert.png" if ranked else None)

    for it in items:
        p, s, cat = it["p"], it["s"], it["cat"]
        best_cat = best_ratio.get(p["category"])
        faq = faq_items(p, s, it["best_merchant"], best_cat)
        prod_url = f"{base_url}/produit/{p['slug']}.html"
        product_ld = {"@context": "https://schema.org", "@type": "Product", "name": p["name"],
                      "brand": {"@type": "Brand", "name": p["brand"]}, "category": cat["label"],
                      "image": f"{base_url}/{it['image']}" if it["has_photo"] else f"{base_url}/assets/social/{p['slug']}-alert.png", "url": prod_url,
                      "description": f"{p['name']} : comparatif de prix, historique 30 jours et caractéristiques."}
        if p.get("mpn"):
            product_ld["mpn"] = p["mpn"]
        if p.get("ean"):
            product_ld["gtin13"] = p["ean"]
        # Les offres ne sont publiées en données structurées qu'avec de VRAIS prix (jamais en mode démo)
        if not demo and s["price_current"] is not None:
            product_ld["offers"] = {"@type": "AggregateOffer", "priceCurrency": "EUR",
                                    "lowPrice": f"{s['price_current']:.2f}",
                                    "highPrice": f"{(s['price_high_now'] or s['price_current']):.2f}",
                                    "offerCount": s["in_stock_count"],
                                    "availability": "https://schema.org/InStock" if s["in_stock_count"] else "https://schema.org/OutOfStock"}
        faq_ld = {"@context": "https://schema.org", "@type": "FAQPage",
                  "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faq]}
        crumbs_ld = {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Accueil", "item": f"{base_url}/"},
            {"@type": "ListItem", "position": 2, "name": cat["label"], "item": f"{base_url}/categorie/{cat['slug']}.html"},
            {"@type": "ListItem", "position": 3, "name": p["name"], "item": prod_url}]}
        price_txt = fmt_price(s["price_current"]) if s["price_current"] is not None else "rupture"
        similar = sorted([i for i in by_cat[p["category"]] if i is not it],
                         key=lambda i: abs(i["p"]["price_ref"] - p["price_ref"]))[:4]
        render("product.html", it["url"], 1, it=it, p=p, s=s, cat=cat, faq=faq,
               seo_text=seo_paragraphs(p, s, cat, it["best_merchant"]),
               versus=vs_by_product.get(p["slug"], [])[:6], similar=similar,
               ld_blocks=[json_ld(product_ld), json_ld(faq_ld), json_ld(crumbs_ld)],
               page_title=f"{p['name']} : {price_txt} – prix & historique ({month_year_fr(build_dt)})",
               meta_description=(f"{p['name']} au meilleur prix : {price_txt} chez {it['best_merchant']}. "
                                 f"Moyenne 30 j {fmt_price(s['price_avg_30d'])}, plus bas historique "
                                 f"{fmt_price(s['price_min_all_time'])}. Comparatif de {s['offer_count']} marchands."),
               og_image=f"{base_url}/assets/social/{p['slug']}-alert.png")

    for v in versus:
        a, b = v["a"], v["b"]
        render("versus.html", v["url"], 1, v=v, a=a, b=b, cat=a["cat"],
               page_title=f"{a['p']['name']} vs {b['p']['name']} : lequel choisir ? ({month_year_fr(build_dt)})",
               meta_description=(f"Comparatif {a['p']['name']} contre {b['p']['name']} : prix du jour, caractéristiques, "
                                 f"performances et meilleur rapport prix/performance. Vainqueur : {v['winner']['p']['name']}."),
               og_image=f"{base_url}/assets/social/{v['winner']['p']['slug']}-alert.png")

    # --- Configurateur PC : données compactes embarquées dans la page ---
    steps = [("cpu", "Processeur"), ("motherboard", "Carte mère"), ("ram", "Mémoire vive"), ("gpu", "Carte graphique"),
             ("ssd", "Stockage SSD"), ("cooler", "Refroidissement"), ("case", "Boîtier"), ("psu", "Alimentation")]
    cfg_items = []
    for it in items:
        bv, bf = it["best_view"], it["best_fr"]
        cfg_items.append({"s": it["p"]["slug"], "c": it["p"]["category"], "n": it["p"]["name"], "b": it["p"]["brand"],
                          "u": it["url"], "i": it["image"], "k": it["p"].get("compat", {}),
                          "e": [bv["price"], bv["merchant_name"], bv["country"], bv["url"]] if bv else None,
                          "f": [bf["price"], bf["merchant_name"], bf["country"], bf["url"]] if bf else None,
                          "a": it["s"]["price_avg_30d"], "l": it["s"]["light"]})
    render("configurateur.html", "configurateur.html", 0, steps=steps, cfg_json=json_ld({"steps": steps, "items": cfg_items}),
           page_title=f"Configurateur PC gamer : compatibilité et meilleurs prix européens ({month_year_fr(build_dt)})",
           meta_description=("Assemblez votre PC pièce par pièce : vérification automatique de compatibilité (socket, RAM, format, "
                             "dimensions, alimentation) et meilleur prix livré en France pour chaque composant."),
           og_image=None, page_kind="config")

    render("404.html", "404.html", 0, root=f"{base_url}/", page_title=f"Page introuvable | {site_name}",
           meta_description="Cette page n'existe pas ou plus.", og_image=None)
    pages.remove("404.html")

    # --- Fichiers techniques SEO ---
    lastmod = iso(build_ts)
    urls = "".join(f"  <url><loc>{base_url}/{'' if pg == 'index.html' else pg}</loc><lastmod>{lastmod}</lastmod>"
                   f"<changefreq>hourly</changefreq><priority>{'1.0' if pg == 'index.html' else '0.8' if pg.startswith(('categorie', 'produit')) else '0.6'}</priority></url>\n"
                   for pg in pages)
    (DIST_DIR / "sitemap.xml").write_text(
        f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{urls}</urlset>\n',
        encoding="utf-8")
    (DIST_DIR / "robots.txt").write_text(f"User-agent: *\nAllow: /\n\nSitemap: {base_url}/sitemap.xml\n", encoding="utf-8")
    (DIST_DIR / ".nojekyll").write_text("", encoding="utf-8")

    # --- Données pour notify.py ---
    stats_out = {"mode": mode, "generated_at": build_ts, "base_url": base_url, "site_name": site_name, "products": []}
    for it in items:
        s, bo = it["s"], it["s"]["best_offer"]
        stats_out["products"].append({
            "slug": it["p"]["slug"], "name": it["p"]["name"], "category": it["cat"]["label"],
            "price_current": s["price_current"], "price_avg_30d": s["price_avg_30d"],
            "price_min_all_time": s["price_min_all_time"], "discount_vs_avg": s["discount_vs_avg"],
            "savings_eur": s["savings_eur"], "true_deal_score": s["true_deal_score"],
            "is_true_deal": s["is_true_deal"], "is_all_time_low": s["is_all_time_low"],
            "best_merchant": bo["merchant"] if bo else None, "best_merchant_name": it["best_merchant"],
            "best_url": bo["url"] if bo else None, "page_url": f"{base_url}/{it['url']}",
            "chart_path": f"dist/assets/social/{it['p']['slug']}-alert.png",
            "social_path": f"dist/assets/social/{it['p']['slug']}-alert.png",
        })
    save_json(SITE_STATS_FILE, stats_out)
    log(f"OK - Site généré : {len(pages)} pages indexables dans dist/ ({len(versus)} comparatifs, {deals_count} vraies promos)"
        + (" — MODE DÉMO" if demo else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
