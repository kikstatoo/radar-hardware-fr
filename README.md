# Radar Hardware Europe

Comparateur de prix hardware PC pour la France et l'Europe : 166 composants sur 8 catégories, 14 marchands (France, Allemagne, Espagne, Pays-Bas), prix **livrés en France**, historique 30 jours, détection des vraies promos et configurateur PC avec vérification de compatibilité.

Fonctionnement 100 % gratuit : GitHub Actions met à jour les prix toutes les heures et publie le site sur GitHub Pages. Aucune base de données, aucune API payante.

---

## Contenu du projet

```
radar-hardware-fr/
├── .github/workflows/auto-update.yml   mise à jour horaire + déploiement GitHub Pages
├── assets/products/                    images produits en cache (WebP), versionnées
├── config/
│   ├── affiliates.json   identifiants d'affiliation, 14 marchands, frais de port estimés
│   ├── settings.json     seuils (promo 8 %, alerte 10 %, cooldown 24 h…), simulation
│   └── feeds.json        URLs des flux produits marchands (vide = mode démo)
├── data/
│   ├── products.json        catalogue : specs, indices de performance, données de compatibilité
│   ├── price_history.json   historique horaire (30 jours)
│   ├── offers_latest.json   dernières offres collectées
│   └── alerts_sent.json     verrou anti-spam des alertes
├── scripts/
│   ├── fetch_prices.py      étape 1 : collecte (flux CSV/XML, RSS, ou simulation)
│   ├── download_images.py   étape 2 : mise en cache des images produits autorisées
│   ├── build_site.py        étape 3 : statistiques, pages, SEO, configurateur
│   ├── notify.py            étape 4 : alertes Discord / Telegram / X
│   ├── visuals.py           visuel neutre quand aucune image n'est disponible
│   └── common.py            fonctions partagées
├── templates/               gabarits HTML (Jinja2)
└── static/                  CSS, JavaScript (recherche, carrousel, configurateur), favicon
```

---

## Tester en local (Windows)

Prérequis : Python 3.11 ou plus récent.

```bat
pip install -r requirements.txt
python scripts/fetch_prices.py && python scripts/download_images.py && python scripts/build_site.py
```

Sous Windows PowerShell 5, remplace `&&` par `;`. Ouvre ensuite `dist\index.html`, ou lance `python -m http.server 8000 -d dist` et va sur http://localhost:8000.

---

## Mode démo et mode réel

Tant qu'aucune URL n'est renseignée dans `config/feeds.json`, le site tourne en **mode démo** :

- les prix sont simulés et un bandeau l'indique ;
- les pages sont en `noindex` ;
- aucune donnée de prix n'est publiée pour Google ;
- aucune alerte sociale n'est envoyée.

Dès qu'un flux réel est branché, l'historique simulé est effacé et le site passe en mode réel.

Pour passer en réel :

1. Inscris-toi comme éditeur sur Awin et/ou Effinity, et postule aux programmes des marchands.
2. Colle l'URL du flux produits (CSV ou XML) de chaque marchand dans `config/feeds.json`.
3. Vérifie le bloc `fields` (colonnes EAN, MPN, nom, prix, lien, stock, image).

Les produits sont reconnus par EAN, puis MPN, puis mots-clés.

---

## Images produits

`scripts/download_images.py` met en cache, au format WebP dans `assets/products/`, les images que le site a le droit d'utiliser :

- les images fournies par les **flux produits des programmes d'affiliation** (Awin, Effinity), qui autorisent leurs éditeurs à les utiliser ;
- les URLs que tu renseignes toi-même dans `image_url` (`data/products.json`), par exemple depuis un kit presse constructeur.

Le script ne récupère pas d'images sur les pages des revendeurs et ne contourne aucune protection anti-hotlink : ces photos appartiennent aux marchands. Amazon interdit par ailleurs le stockage de ses images en dehors de son API.

Sans image disponible, un visuel neutre (icône de catégorie et nom du produit) est affiché : aucune image n'est jamais cassée.

---

## Configurateur PC

La page `configurateur.html` fonctionne entièrement dans le navigateur. Elle vérifie :

- le socket entre processeur, carte mère et refroidissement ;
- le type de mémoire (DDR4 ou DDR5) ;
- le format de la carte mère par rapport au boîtier ;
- la longueur de la carte graphique et la hauteur du ventirad (ou la taille du radiateur AIO) par rapport au boîtier ;
- la puissance de l'alimentation : consommation processeur + carte graphique + 120 W, avec 25 % de marge.

Chaque pièce est proposée au meilleur prix livré en France. La liste d'achat est regroupée par marchand, et la config se partage par lien.

Les données de compatibilité sont dans le champ `compat` de chaque produit. Les longueurs de cartes graphiques sont indicatives : elles varient selon le modèle partenaire.

---

## Affiliation

Édite `config/affiliates.json` :

- `amazon_tag`, `amazon_tag_de`, `amazon_tag_es` : un identifiant Amazon Partenaires par pays.
- `awin_publisher_id`, puis `awin_mid` pour chaque marchand Awin.
- `effiliation_id_compteur` pour Cdiscount.
- `shipping_fr` pour chaque marchand : frais de port **estimés** vers la France. Vérifie-les et ajuste-les.

Un identifiant laissé à zéro garde un lien direct, toujours fonctionnel.

---

## Publication

Le dépôt GitHub est relié à GitHub Pages (Settings, Pages, Source : GitHub Actions). Chaque push sur `main` et chaque heure, le workflow :

1. collecte les prix ;
2. met les images en cache ;
3. génère le site ;
4. envoie les alertes ;
5. sauvegarde les données ;
6. déploie le site.

Secrets optionnels (Settings, Secrets and variables, Actions) :

- `DISCORD_WEBHOOK_URL` ;
- `TELEGRAM_BOT_TOKEN` et `TELEGRAM_CHAT_ID` ;
- `X_API_KEY`, `X_API_SECRET`, `X_ACCESS_TOKEN` et `X_ACCESS_TOKEN_SECRET`.

## À vérifier avant la mise en ligne réelle

- Prix de référence, indices de performance et dimensions (boîtiers, ventirads, cartes graphiques) : ce sont des valeurs de départ issues des fiches constructeur, à contrôler.
- EAN : seuls certains produits en ont un vérifié. Ajoute ceux des autres pour un rapprochement parfait avec les flux.
- Frais de port et adresses de recherche des marchands.
- La mention d'affiliation du pied de page est obligatoire : garde-la.

## Prix exacts et liens directs vers la fiche produit

En mode démonstration, les prix sont des estimations et chaque bouton indique « Rechercher chez … » : il ouvre la recherche du marchand (par EAN ou référence fabricant quand elle est connue). Dès qu'une vraie source est branchée, le site bascule tout seul en mode réel : prix relevés, bouton « Voir l'offre » vers la fiche exacte.

1. **Tag Amazon Partenaires** : remplace `ton-tag-21` dans `config/affiliates.json` (`amazon_tag`, `amazon_tag_de`, `amazon_tag_es`). Tant que la valeur d'exemple est là, aucun tag n'est ajouté aux liens.
2. **Flux Awin / Effinity** (LDLC, Materiel.net, Rue du Commerce, Fnac, Cdiscount…) : colle l'URL de chaque flux produit dans `config/feeds.json`. Chaque ligne du flux fournit le lien profond vers la fiche, le prix et les frais de port.
3. **Amazon Creators API** (accessible après 10 ventes qualifiées sur 30 jours) : crée un identifiant dans Associates Central, puis ajoute les secrets `AMAZON_CREATORS_CLIENT_ID` et `AMAZON_CREATORS_CLIENT_SECRET` au dépôt. Le robot récupère alors chaque heure le prix de la Buy Box et le lien `detailPageURL`, et retrouve tout seul l'ASIN des produits qui n'en ont pas (cache `data/asin_cache.json`).
4. **ASIN manuels** : un ASIN vérifié peut être ajouté dans `data/products.json` (`"asin": {"amazon_fr": "B0…"}`) pour obtenir un lien `/dp/` direct même en mode démo.
