"""
visuals.py — Visuel neutre affiché quand aucune image produit n'est disponible.

Sobre et honnête : fond clair, icône vectorielle de la catégorie (trait fin) et nom du produit.
Il ne cherche pas à imiter une photo ou un emballage. Dès qu'une image est mise en cache par
download_images.py (assets/products/<slug>.webp), elle la remplace automatiquement.
"""
from __future__ import annotations

from html import escape

# Icônes au trait (viewBox 24x24, style « line icons »)
ICONS = {
    "cpu": '<rect x="6" y="6" width="12" height="12" rx="1.5"/><rect x="9.5" y="9.5" width="5" height="5" rx=".5"/>'
           '<path d="M9 2.5v3M12 2.5v3M15 2.5v3M9 18.5v3M12 18.5v3M15 18.5v3M2.5 9h3M2.5 12h3M2.5 15h3M18.5 9h3M18.5 12h3M18.5 15h3"/>',
    "gpu": '<rect x="2" y="6.5" width="17" height="10" rx="1.5"/><circle cx="7.5" cy="11.5" r="2.6"/><circle cx="14" cy="11.5" r="2.6"/>'
           '<path d="M19 9.5h2.5v4H19M5 16.5v3M9 16.5v3M13 16.5v3"/>',
    "motherboard": '<rect x="3.5" y="3" width="17" height="18" rx="1.5"/><rect x="7" y="6.5" width="5" height="5" rx=".5"/>'
                   '<path d="M15 6.5v7M17.5 6.5v7M7 15h7.5M7 18h7.5"/>',
    "ram": '<rect x="2.5" y="7" width="19" height="8" rx="1"/><path d="M5.5 9.5h2.5v3H5.5zM10.5 9.5H13v3h-2.5zM15.5 9.5H18v3h-2.5z"/>'
           '<path d="M5 15v2.5M9 15v2.5M13 15v2.5M17 15v2.5"/>',
    "ssd": '<rect x="2.5" y="8.5" width="16" height="7" rx="1"/><path d="M18.5 10h3v4h-3"/><path d="M5.5 10.5h6v3h-6z"/><circle cx="15.5" cy="12" r=".9"/>',
    "cooler": '<circle cx="12" cy="12" r="8.5"/><circle cx="12" cy="12" r="1.8"/>'
              '<path d="M12 10.2c0-3 1-5.2 3.2-5.2M13.8 12c3 0 5.2 1 5.2 3.2M12 13.8c0 3-1 5.2-3.2 5.2M10.2 12c-3 0-5.2-1-5.2-3.2"/>',
    "case": '<rect x="6" y="2.5" width="12" height="19" rx="1.5"/><path d="M9 6h6M9 8.5h6"/><circle cx="12" cy="15" r="2.6"/>',
    "psu": '<rect x="3" y="5.5" width="18" height="13" rx="1.5"/><circle cx="9" cy="12" r="3.6"/><path d="M15.5 9.5h3M15.5 12h3M15.5 14.5h3"/>'
           '<path d="M9 9.5v5M6.5 12h5"/>',
}


def icon_svg(category: str, size: int = 20, stroke: float = 1.5) -> str:
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            f'stroke-width="{stroke}" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
            f'{ICONS.get(category, ICONS["cpu"])}</svg>')


def product_svg(product: dict) -> str:
    """Visuel neutre 800x600 : fond #F8FAFC, icône de catégorie, nom et marque."""
    name = product["name"]
    brand = product.get("brand", "")
    lines, line = [], ""
    for word in name.split():
        if line and len(line) + len(word) + 1 > 30:
            lines.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    lines.append(line)
    lines = lines[:2]
    text = "".join(f'<text x="400" y="{440 + i * 36}" text-anchor="middle" font-family="Plus Jakarta Sans,Inter,Arial,sans-serif" '
                   f'font-size="27" font-weight="600" fill="#334155">{escape(l)}</text>' for i, l in enumerate(lines))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 600" role="img" aria-label="{escape(name)}">'
            f'<rect width="800" height="600" fill="#F8FAFC"/>'
            f'<g transform="translate(310 110) scale(7.5)" fill="none" stroke="#94A3B8" stroke-width="1.1" '
            f'stroke-linecap="round" stroke-linejoin="round">{ICONS.get(product["category"], ICONS["cpu"])}</g>'
            f'{text}<text x="400" y="{440 + 36 * len(lines) + 8}" text-anchor="middle" '
            f'font-family="Plus Jakarta Sans,Inter,Arial,sans-serif" font-size="15" letter-spacing="3" fill="#94A3B8">'
            f'{escape(brand.upper())}</text></svg>')
