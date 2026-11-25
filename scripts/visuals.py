"""
visuals.py — Visuels produits générés (SVG vectoriels, nets à toutes les tailles).

Illustrations ORIGINALES par catégorie (processeur, carte graphique, RAM, SSD, carte mère),
sans logo ni reproduction d'emballage constructeur. Elles garantissent qu'aucune carte du site
n'a d'image cassée ou vide. Dès qu'une image officielle est disponible (champ image_url du
catalogue ou image fournie par un flux marchand Awin), le site l'utilise à la place.
"""
from __future__ import annotations

import re
from html import escape

ACCENTS = {"AMD": "#F97316", "Intel": "#3B82F6", "NVIDIA": "#22C55E", "Corsair": "#EAB308",
           "G.Skill": "#A855F7", "Kingston": "#EF4444", "Samsung": "#3B82F6", "Western Digital": "#64748B",
           "Crucial": "#06B6D4", "MSI": "#EF4444", "ASUS": "#F59E0B"}


def short_label(product: dict) -> tuple[str, str]:
    """('RTX 5070 Ti', '16 Go') à partir du nom complet."""
    name = product["name"]
    for prefix in ("NVIDIA GeForce ", "AMD Radeon ", "AMD Ryzen ", "Intel Core ", "WD_BLACK ", "G.Skill ",
                   "Corsair ", "Kingston ", "Samsung ", "Crucial ", "MSI ", "ASUS "):
        name = name.replace(prefix, "")
    m = re.search(r"\s(\d+\s?(?:Go|To))\b", name)
    sub = m.group(1) if m else ""
    main = name.replace(sub, "").replace("(2x16 Go)", "").replace("PCIe 4.0", "").strip(" -")
    main = re.sub(r"\s+", " ", main)
    if product["category"] == "ram":
        main = re.sub(r"DDR5.*", "", main).strip()
        sub = "32 Go DDR5-6000"
    if product["category"] == "cpu":
        main = product["name"].replace("AMD ", "").replace("Intel ", "").strip()
        sub = product["specs"].get("Socket", "")
    return main[:26], sub


def _bg(accent: str) -> str:
    return (f'<defs><radialGradient id="g" cx="50%" cy="38%" r="75%"><stop offset="0" stop-color="#FFFFFF"/>'
            f'<stop offset="1" stop-color="#E2E8F0"/></radialGradient>'
            f'<linearGradient id="m" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#3A4458"/>'
            f'<stop offset="1" stop-color="#1B2130"/></linearGradient>'
            f'<linearGradient id="a" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{accent}"/>'
            f'<stop offset="1" stop-color="#38BDF8"/></linearGradient></defs>'
            f'<rect width="400" height="300" fill="url(#g)"/>'
            f'<ellipse cx="200" cy="262" rx="150" ry="14" fill="#0F172A" opacity=".12"/>')


def _cpu(accent: str, main: str, sub: str) -> str:
    pins = "".join(f'<rect x="{110 + i * 12}" y="60" width="5" height="10" fill="#D4A72C"/>'
                   f'<rect x="{110 + i * 12}" y="230" width="5" height="10" fill="#D4A72C"/>' for i in range(15))
    pins += "".join(f'<rect x="90" y="{80 + i * 12}" width="10" height="5" fill="#D4A72C"/>'
                    f'<rect x="300" y="{80 + i * 12}" width="10" height="5" fill="#D4A72C"/>' for i in range(13))
    return (pins + '<rect x="100" y="70" width="200" height="160" rx="10" fill="#0E7C4A"/>'
            '<rect x="118" y="84" width="164" height="132" rx="8" fill="#C9CED6" stroke="#9AA3AF" stroke-width="2"/>'
            '<rect x="118" y="84" width="164" height="132" rx="8" fill="url(#m)" opacity=".08"/>'
            f'<rect x="132" y="98" width="40" height="6" rx="3" fill="{accent}"/>'
            f'<text x="200" y="150" text-anchor="middle" font-family="Arial,Helvetica,sans-serif" font-weight="800" font-size="{20 if len(main) < 16 else 15}" fill="#1E293B">{escape(main)}</text>'
            f'<text x="200" y="176" text-anchor="middle" font-family="Consolas,monospace" font-size="13" fill="#475569">{escape(sub)}</text>')


def _gpu(accent: str, main: str, sub: str) -> str:
    def fan(cx: int) -> str:
        blades = "".join(f'<path d="M{cx} 145 q14 -26 30 -10" fill="none" stroke="#475569" stroke-width="6" '
                         f'stroke-linecap="round" transform="rotate({a} {cx} 145)"/>' for a in range(0, 360, 45))
        return (f'<circle cx="{cx}" cy="145" r="44" fill="#111827" stroke="#334155" stroke-width="3"/>{blades}'
                f'<circle cx="{cx}" cy="145" r="12" fill="#1F2937" stroke="{accent}" stroke-width="2"/>')
    return ('<rect x="40" y="188" width="320" height="16" fill="#0E7C4A"/>'
            + "".join(f'<rect x="{120 + i * 8}" y="200" width="5" height="12" fill="#D4A72C"/>' for i in range(18))
            + '<rect x="30" y="85" width="340" height="110" rx="14" fill="url(#m)" stroke="#475569" stroke-width="2"/>'
            f'<rect x="30" y="85" width="340" height="6" rx="3" fill="url(#a)"/>'
            + fan(110) + fan(200) + fan(290)
            + f'<text x="200" y="62" text-anchor="middle" font-family="Arial,Helvetica,sans-serif" font-weight="800" font-size="22" fill="#1E293B">{escape(main)}</text>'
            f'<text x="200" y="250" text-anchor="middle" font-family="Consolas,monospace" font-size="14" fill="#475569">{escape(sub)}</text>')


def _ram(accent: str, main: str, sub: str, rgb: bool) -> str:
    def stick(y: int) -> str:
        chips = "".join(f'<rect x="{78 + i * 32}" y="{y + 40}" width="24" height="18" fill="#0F172A"/>' for i in range(8))
        light = (f'<rect x="64" y="{y - 8}" width="272" height="10" rx="4" fill="url(#a)"/>' if rgb else "")
        return (light + f'<rect x="60" y="{y}" width="280" height="70" rx="4" fill="#0E7C4A"/>{chips}'
                f'<rect x="60" y="{y}" width="280" height="38" rx="4" fill="url(#m)"/>'
                f'<rect x="72" y="{y + 12}" width="60" height="5" rx="2" fill="{accent}"/>'
                + "".join(f'<rect x="{70 + i * 6}" y="{y + 64}" width="3" height="8" fill="#D4A72C"/>' for i in range(44)))
    return (stick(80) + stick(165)
            + f'<text x="200" y="58" text-anchor="middle" font-family="Arial,Helvetica,sans-serif" font-weight="800" font-size="20" fill="#1E293B">{escape(main)}</text>'
            f'<text x="200" y="272" text-anchor="middle" font-family="Consolas,monospace" font-size="14" fill="#475569">{escape(sub)}</text>')


def _ssd(accent: str, main: str, sub: str) -> str:
    return ('<rect x="40" y="120" width="320" height="64" rx="6" fill="#0F172A"/>'
            '<rect x="330" y="132" width="30" height="40" fill="#0F172A"/>'
            + "".join(f'<rect x="{44 + i * 6}" y="140" width="3" height="24" fill="#D4A72C"/>' for i in range(3))
            + '<circle cx="352" cy="152" r="8" fill="#E2E8F0"/>'
            '<rect x="70" y="128" width="230" height="48" rx="4" fill="url(#m)"/>'
            f'<rect x="70" y="128" width="230" height="8" rx="3" fill="url(#a)"/>'
            f'<text x="185" y="162" text-anchor="middle" font-family="Consolas,monospace" font-size="13" fill="#E2E8F0">{escape(sub)} · NVMe</text>'
            f'<text x="200" y="92" text-anchor="middle" font-family="Arial,Helvetica,sans-serif" font-weight="800" font-size="22" fill="#1E293B">{escape(main)}</text>'
            '<text x="200" y="226" text-anchor="middle" font-family="Consolas,monospace" font-size="13" fill="#475569">M.2 2280 · PCIe 4.0</text>')


def _mb(accent: str, main: str, sub: str) -> str:
    slots = "".join(f'<rect x="248" y="{60 + i * 14}" width="8" height="110" fill="#1F2937"/>' for i in range(0))
    return ('<rect x="90" y="40" width="220" height="230" rx="6" fill="#111827" stroke="#334155" stroke-width="2"/>'
            '<rect x="130" y="70" width="64" height="64" rx="4" fill="#C9CED6" stroke="#64748B" stroke-width="2"/>'
            '<rect x="142" y="82" width="40" height="40" fill="#E5E7EB"/>'
            + "".join(f'<rect x="{214 + i * 12}" y="60" width="7" height="100" rx="2" fill="#475569"/>' for i in range(4))
            + '<rect x="100" y="56" width="22" height="90" rx="3" fill="url(#m)" stroke="#475569"/>'
            '<rect x="130" y="54" width="70" height="12" rx="3" fill="url(#m)" stroke="#475569"/>'
            f'<rect x="110" y="178" width="180" height="10" rx="2" fill="#334155"/><rect x="110" y="178" width="60" height="10" rx="2" fill="{accent}"/>'
            '<rect x="110" y="206" width="180" height="6" rx="2" fill="#334155"/>'
            '<rect x="230" y="222" width="60" height="36" rx="4" fill="url(#m)" stroke="#475569"/>'
            f'<rect x="120" y="226" width="90" height="12" rx="3" fill="url(#a)" opacity=".85"/>'
            + slots
            + f'<text x="200" y="30" text-anchor="middle" font-family="Arial,Helvetica,sans-serif" font-weight="800" font-size="{18 if len(main) < 20 else 15}" fill="#1E293B">{escape(main)}</text>'
            f'<text x="200" y="290" text-anchor="middle" font-family="Consolas,monospace" font-size="12" fill="#475569">{escape(sub)}</text>')


def product_svg(product: dict) -> str:
    accent = ACCENTS.get(product.get("brand"), "#38BDF8")
    main, sub = short_label(product)
    cat = product["category"]
    if cat == "cpu":
        body = _cpu(accent, main, sub)
    elif cat == "gpu":
        body = _gpu(accent, main, sub)
    elif cat == "ram":
        body = _ram(accent, main, sub, product["specs"].get("RGB") == "Oui")
    elif cat == "ssd":
        body = _ssd(accent, main, sub)
    else:
        body = _mb(accent, main, product["specs"].get("Chipset", "") + " · " + product["specs"].get("Format", ""))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 300" role="img" '
            f'aria-label="{escape(product["name"])}">{_bg(accent)}{body}</svg>')
