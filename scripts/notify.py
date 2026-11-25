"""
notify.py — Acquisition automatisée (étape 3 du pipeline).

Publie une alerte quand un composant passe au moins `min_drop_percent` (10 % par défaut)
sous sa moyenne 30 jours, avec verrou anti-spam (data/alerts_sent.json) :
  • Discord : Embed riche (vert émeraude, miniature du graphique, vignette sociale).
  • Telegram : vignette sociale + légende HTML + boutons cliquables.
  • X (Twitter) API v2 : tweet + image, signature OAuth 1.0a faite à la main (aucune lib payante).

Chaque canal ne s'active que si ses secrets sont présents dans les variables d'environnement.
En mode démo (prix simulés), aucune alerte n'est publiée (réglable dans config/settings.json).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import sys
import time
from pathlib import Path
from urllib.parse import quote

import requests

from common import (ALERTS_FILE, ROOT, SITE_STATS_FILE, fmt_price, load_json, load_settings, log,
                    now_ts, save_json)

TIMEOUT = 30


def plain(text: str) -> str:
    """Espaces fines/insécables → espaces normales (meilleur rendu sur les réseaux)."""
    return text.replace(" ", " ").replace(" ", " ")


# =============================================================================
# Sélection des alertes
# =============================================================================
def pick_alerts(stats: dict, alerts: dict, settings: dict) -> list[dict]:
    min_drop = float(settings.get("min_drop_percent", 10.0))
    cooldown = float(settings.get("alert_cooldown_hours", 24)) * 3600
    extra = float(settings.get("alert_realert_extra_drop_percent", 3.0))
    now = now_ts()
    chosen = []
    for p in stats.get("products", []):
        if p["price_current"] is None or not p.get("best_url") or p["discount_vs_avg"] < min_drop:
            continue
        last = alerts.get(p["slug"])
        if last:
            in_cooldown = now - last["ts"] < cooldown
            much_lower = p["price_current"] <= last["price"] * (1 - extra / 100)
            if in_cooldown and not much_lower:
                continue
            if not in_cooldown and p["price_current"] >= last["price"]:
                continue  # même prix que la dernière alerte : on ne répète pas
        chosen.append(p)
    chosen.sort(key=lambda p: p["discount_vs_avg"], reverse=True)
    return chosen[: int(settings.get("max_alerts_per_run", 3))]


def headline(p: dict) -> str:
    return "🏆 PLUS BAS HISTORIQUE" if p["is_all_time_low"] else f"🔥 VRAIE PROMO -{p['discount_vs_avg']:.0f} %"


# =============================================================================
# Discord
# =============================================================================
def send_discord(p: dict, webhook: str, site_name: str) -> bool:
    chart, social = ROOT / p["chart_path"], ROOT / p["social_path"]
    embed = {
        "title": plain(f"{headline(p)} — {p['name']}"),
        "url": p["page_url"],
        "color": 0x00E599,
        "description": plain(f"~~{fmt_price(p['price_avg_30d'])}~~ ➜ **{fmt_price(p['price_current'])}** "
                             f"chez **{p['best_merchant_name']}**\nÉconomie : **{fmt_price(p['savings_eur'])}** "
                             f"vs moyenne 30 jours."),
        "fields": [
            {"name": "Score Vraie Promo", "value": f"{p['true_deal_score']}/100", "inline": True},
            {"name": "Plus bas historique", "value": plain(fmt_price(p["price_min_all_time"])), "inline": True},
            {"name": "Offre", "value": f"[Voir l'offre →]({p['best_url']})", "inline": False},
        ],
        "thumbnail": {"url": "attachment://chart.png"},
        "image": {"url": "attachment://alert.png"},
        "footer": {"text": f"{site_name} • lien affilié"},
    }
    files, handles = {}, []
    try:
        for key, path, name in (("files[0]", chart, "chart.png"), ("files[1]", social, "alert.png")):
            if path.exists():
                fh = open(path, "rb")
                handles.append(fh)
                files[key] = (name, fh, "image/png")
        if "files[0]" not in files:
            embed.pop("thumbnail")
        if "files[1]" not in files:
            embed.pop("image")
        payload = {"username": site_name, "embeds": [embed], "allowed_mentions": {"parse": []}}
        resp = requests.post(webhook, data={"payload_json": json.dumps(payload)}, files=files or None, timeout=TIMEOUT)
        if resp.status_code in (200, 204):
            return True
        log(f"  Discord HTTP {resp.status_code} : {resp.text[:200]}")
    except requests.RequestException as exc:
        log(f"  Discord erreur réseau : {exc}")
    finally:
        for fh in handles:
            fh.close()
    return False


# =============================================================================
# Telegram
# =============================================================================
def _html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def send_telegram(p: dict, token: str, chat_id: str) -> bool:
    caption = plain(
        f"<b>{_html(headline(p))}</b>\n<b>{_html(p['name'])}</b>\n\n"
        f"<s>{fmt_price(p['price_avg_30d'])}</s> ➜ <b>{fmt_price(p['price_current'])}</b> chez {_html(p['best_merchant_name'])}\n"
        f"Économie : {fmt_price(p['savings_eur'])} vs moyenne 30 j • Score {p['true_deal_score']}/100\n\n"
        f"#PCGamer #BonPlanPC #Hardware")
    markup = {"inline_keyboard": [[{"text": "Voir l'offre →", "url": p["best_url"]}],
                                  [{"text": "📈 Historique des prix", "url": p["page_url"]}]]}
    social = ROOT / p["social_path"]
    try:
        if social.exists():
            with open(social, "rb") as fh:
                resp = requests.post(f"https://api.telegram.org/bot{token}/sendPhoto",
                                     data={"chat_id": chat_id, "caption": caption, "parse_mode": "HTML",
                                           "reply_markup": json.dumps(markup)},
                                     files={"photo": ("alert.png", fh, "image/png")}, timeout=TIMEOUT)
        else:
            resp = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                                 data={"chat_id": chat_id, "text": caption, "parse_mode": "HTML",
                                       "reply_markup": json.dumps(markup)}, timeout=TIMEOUT)
        if resp.ok and resp.json().get("ok"):
            return True
        log(f"  Telegram HTTP {resp.status_code} : {resp.text[:200]}")
    except (requests.RequestException, ValueError) as exc:
        log(f"  Telegram erreur : {exc}")
    return False


# =============================================================================
# X (Twitter) — OAuth 1.0a utilisateur, signé à la main
# =============================================================================
def _pct(s) -> str:
    return quote(str(s), safe="~-._")


def oauth1_header(method: str, url: str, keys: dict, params: dict | None = None) -> str:
    oauth = {
        "oauth_consumer_key": keys["api_key"],
        "oauth_nonce": secrets.token_hex(16),
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": str(int(time.time())),
        "oauth_token": keys["access_token"],
        "oauth_version": "1.0",
    }
    all_params = {**(params or {}), **oauth}
    param_str = "&".join(f"{k}={v}" for k, v in sorted((_pct(k), _pct(v)) for k, v in all_params.items()))
    base = "&".join([method.upper(), _pct(url), _pct(param_str)])
    key = f"{_pct(keys['api_secret'])}&{_pct(keys['access_secret'])}"
    oauth["oauth_signature"] = base64.b64encode(hmac.new(key.encode(), base.encode(), hashlib.sha1).digest()).decode()
    return "OAuth " + ", ".join(f'{_pct(k)}="{_pct(v)}"' for k, v in sorted(oauth.items()))


def x_upload_media(path: Path, keys: dict) -> str | None:
    """Tente l'upload via l'endpoint v2, puis l'ancien v1.1 (selon ce que ton accès autorise)."""
    endpoints = [("https://api.x.com/2/media/upload", {"media_category": "tweet_image"}),
                 ("https://upload.twitter.com/1.1/media/upload.json", {})]
    for url, extra in endpoints:
        try:
            with open(path, "rb") as fh:
                resp = requests.post(url, headers={"Authorization": oauth1_header("POST", url, keys)},
                                     files={"media": ("alert.png", fh, "image/png")}, data=extra, timeout=TIMEOUT)
            if resp.ok:
                body = resp.json()
                media_id = (body.get("data") or {}).get("id") or body.get("media_id_string")
                if media_id:
                    return str(media_id)
            log(f"  X upload {url.split('/')[2]} HTTP {resp.status_code} : {resp.text[:160]}")
        except (requests.RequestException, ValueError) as exc:
            log(f"  X upload erreur : {exc}")
    return None


def send_x(p: dict, keys: dict) -> bool:
    text = plain(f"{headline(p)}\n{p['name']} à {fmt_price(p['price_current'])} chez {p['best_merchant_name']} "
                 f"(moy. 30 j : {fmt_price(p['price_avg_30d'])})\n\n📈 {p['page_url']}\n\n#PCGamer #BonPlanPC #Hardware")
    if len(text) > 280:
        text = text[:277] + "…"
    payload = {"text": text}
    social = ROOT / p["social_path"]
    media_id = x_upload_media(social, keys) if social.exists() else None
    if media_id:
        payload["media"] = {"media_ids": [media_id]}
    url = "https://api.x.com/2/tweets"
    try:
        resp = requests.post(url, json=payload, timeout=TIMEOUT,
                             headers={"Authorization": oauth1_header("POST", url, keys), "Content-Type": "application/json"})
        if resp.status_code in (200, 201):
            return True
        log(f"  X HTTP {resp.status_code} : {resp.text[:200]}")
    except requests.RequestException as exc:
        log(f"  X erreur réseau : {exc}")
    return False


# =============================================================================
# Orchestration
# =============================================================================
def main() -> int:
    settings = load_settings()
    notif = settings.get("notifications", {})
    stats = load_json(SITE_STATS_FILE, None)
    if not stats:
        log("Pas de data/site_stats.json : lance d'abord build_site.py.")
        return 0
    if stats.get("mode") != "live" and not notif.get("send_in_simulation_mode", False):
        log("Mode démo : alertes sociales désactivées (aucun faux bon plan publié).")
        return 0

    env = os.environ
    discord = env.get("DISCORD_WEBHOOK_URL", "").strip() if notif.get("discord", True) else ""
    tg_token = env.get("TELEGRAM_BOT_TOKEN", "").strip() if notif.get("telegram", True) else ""
    tg_chat = env.get("TELEGRAM_CHAT_ID", "").strip()
    x_keys = {"api_key": env.get("X_API_KEY", "").strip(), "api_secret": env.get("X_API_SECRET", "").strip(),
              "access_token": env.get("X_ACCESS_TOKEN", "").strip(), "access_secret": env.get("X_ACCESS_TOKEN_SECRET", "").strip()}
    x_on = notif.get("x", True) and all(x_keys.values())
    channels = [n for n, ok in (("Discord", discord), ("Telegram", tg_token and tg_chat), ("X", x_on)) if ok]
    if not channels:
        log("Aucun secret de notification configuré : étape ignorée.")
        return 0

    alerts = load_json(ALERTS_FILE, {}) or {}
    todo = pick_alerts(stats, alerts, settings)
    if not todo:
        log(f"Aucune baisse ≥ {settings.get('min_drop_percent', 10)} % hors cooldown. Canaux prêts : {', '.join(channels)}.")
        return 0

    site_name = stats.get("site_name", "Radar Hardware FR")
    for p in todo:
        log(f"→ Alerte {p['name']} ({fmt_price(p['price_current'])}, -{p['discount_vs_avg']} %)")
        sent = []
        if discord and send_discord(p, discord, site_name):
            sent.append("discord")
        if tg_token and tg_chat and send_telegram(p, tg_token, tg_chat):
            sent.append("telegram")
        if x_on and send_x(p, x_keys):
            sent.append("x")
        if sent:
            alerts[p["slug"]] = {"ts": now_ts(), "price": p["price_current"], "channels": sent}
            log(f"  ✓ envoyée sur {', '.join(sent)}")
    # Purge des verrous de plus de 30 jours
    horizon = now_ts() - 30 * 86400
    alerts = {k: v for k, v in alerts.items() if v.get("ts", 0) >= horizon}
    save_json(ALERTS_FILE, alerts)
    return 0


if __name__ == "__main__":
    sys.exit(main())
