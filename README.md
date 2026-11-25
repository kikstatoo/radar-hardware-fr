# 📡 Radar Hardware Europe

Comparateur de prix **hardware PC Gamer** pour la France et l'Europe (14 marchands 🇫🇷 🇩🇪 🇪🇸 🇳🇱, prix **livrés en France**), mis à jour **toutes les heures** et **100 % gratuit à faire tourner** (GitHub Actions + GitHub Pages, aucune base de données, aucune API payante).

- **Score Vraie Promo (0-100)** : prix actuel comparé à la moyenne, à la médiane 30 jours et au plus bas historique. Les badges « VRAIE PROMO » et « PLUS BAS HISTORIQUE » ne s'affichent que si le prix est au moins 8 % sous la moyenne 30 jours.
- **Ratio prix / performance** : chaque composant a un `perf_score`, ce qui permet de trier par € par point de performance.
- **SEO programmatique** : 24 fiches produits, 5 pages catégories, ~37 comparatifs « Versus », JSON-LD, sitemap.xml et robots.txt.
- **Alertes automatiques** : Discord, Telegram et X (Twitter) dès qu'un composant passe 10 % sous sa moyenne 30 jours.

---

## 🗂 Arborescence

```
radar-hardware-fr/
├── .github/workflows/auto-update.yml   ← automatisation horaire + déploiement Pages
├── config/
│   ├── affiliates.json   ← identifiants d'affiliation, marchands FR/EU, frais de port estimés
│   ├── settings.json     ← seuils (promo 8 %, alerte 10 %, cooldown 24 h…)
│   └── feeds.json        ← URLs des flux marchands (vide = mode démo)
├── data/
│   ├── products.json        ← catalogue des 24 composants (specs, perf_score, prix de référence)
│   ├── price_history.json   ← historique horaire (30 jours / 720 points max)
│   ├── offers_latest.json   ← dernières offres collectées
│   ├── alerts_sent.json     ← verrou anti-spam des alertes
│   ├── sim_state.json       ← état du marché simulé (mode démo)
│   └── site_stats.json      ← stats calculées, lues par notify.py
├── scripts/
│   ├── common.py         ← fonctions partagées (affiliation, JSON, HTTP…)
│   ├── fetch_prices.py   ← étape 1 : collecte des prix (flux CSV/XML, RSS, simulation)
│   ├── build_site.py     ← étape 2 : stats, graphiques, pages HTML, SEO
│   ├── visuals.py        ← visuels produits générés (SVG) quand aucune image officielle n'existe
│   └── notify.py         ← étape 3 : alertes Discord / Telegram / X
├── templates/            ← gabarits HTML (Jinja2)
├── static/               ← CSS, JavaScript (recherche instantanée), favicon
├── requirements.txt
└── dist/                 ← site généré (non versionné, reconstruit à chaque exécution)
```

---

## 💻 1. Tester le site en local sur Windows

**Prérequis :** Python 3.11 ou plus récent ([python.org](https://www.python.org/downloads/), coche « Add Python to PATH » à l'installation).

Ouvre une **Invite de commandes** (`cmd`) dans le dossier du projet, puis :

```bat
pip install -r requirements.txt
python scripts/fetch_prices.py && python scripts/build_site.py
```

> Sous **Windows PowerShell 5**, remplace `&&` par `;` :
> `python scripts/fetch_prices.py; python scripts/build_site.py`

Puis ouvre le site :

- **Le plus simple :** double-clique sur `dist\index.html`.
- **Comme en ligne :** `python -m http.server 8000 -d dist`, puis va sur <http://localhost:8000>.

Relance les deux commandes pour simuler une heure de plus : les prix bougent, les graphiques s'allongent.

---

## 🧪 Mode démo et mode réel

| | **Mode démo** (par défaut) | **Mode réel** |
|---|---|---|
| Activation | Aucune `url` dans `config/feeds.json` | Au moins une `url` renseignée |
| Prix | Simulés (-15 % à +5 %, ventes flash, ruptures) | Flux marchands CSV/XML + RSS |
| Historique | 30 jours simulés générés au 1er lancement | Effacé au passage en réel, puis vrais points |
| Bandeau « Mode démonstration » | Affiché | Masqué |
| Indexation Google | `noindex` (on ne fait pas indexer de faux prix) | `index` |
| JSON-LD `AggregateOffer` | Non publié | Publié (prix affichés dans Google) |
| Alertes sociales | Coupées | Actives |

Ces garde-fous évitent de publier de faux bons plans sous ton nom. Tu peux les modifier dans `config/settings.json` (`send_in_simulation_mode`, `noindex_in_simulation_mode`), mais ce n'est pas conseillé sur un site public.

### Passer en mode réel

1. Inscris-toi gratuitement comme éditeur sur **Awin** et/ou **Effinity**, puis postule aux programmes TopAchat, Rue du Commerce, Fnac, Cdiscount… et à **Amazon Partenaires**.
2. Une fois accepté, récupère l'**URL du flux produits** (CSV ou XML) de chaque marchand et colle-la dans `config/feeds.json` (champ `url`).
3. Vérifie le bloc `fields` : il fait correspondre les colonnes du flux (EAN, MPN, nom, prix, lien, stock). Les noms par défaut sont ceux des flux Awin.
4. Le rapprochement avec le catalogue se fait par **EAN**, puis **MPN**, puis **mots-clés** (`match_keywords` / `exclude_keywords` dans `products.json`). Ajoute les EAN de tes produits dans `products.json` pour un matching parfait.

---

## 💰 2. Configurer l'affiliation

Édite `config/affiliates.json` :

- `amazon_tag` : ton identifiant Amazon Partenaires (ex. `monsite-21`), ajouté automatiquement (`?tag=`) à tous les liens Amazon.
- `awin_publisher_id` + `awin_mid` de chaque marchand : les liens sont enrobés automatiquement en `awin1.com/cread.php`.
- `effiliation_id_compteur` (Cdiscount) et `aliexpress_aff_short_key`.
- `base_url` : l'adresse de ton site, par ex. `https://ton-pseudo.github.io/radar-hardware-fr`. Si tu laisses la valeur d'exemple, elle est déduite automatiquement du nom de ton dépôt sur GitHub.

Un identifiant laissé à `0000` désactive simplement l'enrobage pour ce marchand : le lien reste direct et fonctionnel.

---

## 🚀 3. Publier le projet avec GitHub Desktop

1. Installe [GitHub Desktop](https://desktop.github.com/) et connecte-toi à ton compte GitHub.
2. **File → Add local repository…** → choisis le dossier `radar-hardware-fr`. GitHub Desktop propose **« create a repository »** : clique dessus, garde la branche `main`, puis **Create repository**.
3. Écris un message dans **Summary** (ex. « Premier commit ») → **Commit to main**.
4. Clique sur **Publish repository**, **décoche « Keep this code private »** (un dépôt public rend GitHub Actions gratuit et illimité), puis **Publish repository**.

Pour les mises à jour suivantes : le bot pousse des données toutes les heures, donc clique toujours sur **Fetch origin** puis **Pull origin** avant de faire **Commit** et **Push origin**.

---

## ⚙️ 4. Activer GitHub Pages (3 clics)

Sur la page de ton dépôt GitHub :

1. **Settings** (onglet en haut à droite)
2. **Pages** (menu de gauche)
3. **Source → GitHub Actions**

Ensuite, onglet **Actions** → **Mise à jour des prix & déploiement** → **Run workflow** pour lancer le premier déploiement. Ton site est en ligne à l'adresse affichée dans **Settings → Pages** (environ 2 minutes plus tard), puis se met à jour toutes les heures.

---

## 🔔 5. Ajouter les secrets d'alerte (Discord, Telegram, X)

**Settings → Secrets and variables → Actions → New repository secret**, puis crée chaque secret (nom exact) :

| Secret | Où le trouver |
|---|---|
| `DISCORD_WEBHOOK_URL` | Serveur Discord → Paramètres du salon → Intégrations → Webhooks → Nouveau webhook → Copier l'URL |
| `TELEGRAM_BOT_TOKEN` | Parle à **@BotFather** sur Telegram → `/newbot` → copie le token |
| `TELEGRAM_CHAT_ID` | Ajoute le bot comme admin de ta chaîne ; pour une chaîne publique, utilise `@nom_de_la_chaine` |
| `X_API_KEY`, `X_API_SECRET`, `X_ACCESS_TOKEN`, `X_ACCESS_TOKEN_SECRET` | [developer.x.com](https://developer.x.com) → ton app → Keys and tokens (permissions **Read and Write**) |

Chaque canal ne s'active que si ses secrets existent : tu peux commencer par Discord seul. Les alertes ne partent qu'en **mode réel**, avec au maximum 3 alertes par heure et 24 h de cooldown par produit.

> L'accès gratuit à l'API X est très limité et ses conditions changent souvent : si l'envoi d'image est refusé, le script tweete le texte seul et le site continue de fonctionner.

---

## 🔧 Personnaliser

- **Ajouter un produit :** copie un bloc dans `data/products.json` avec un `slug` unique, puis relance le build. Sa fiche, ses comparatifs et le sitemap sont générés automatiquement.
- **Seuils :** `deal_threshold_percent` (badge, 8 %) et `min_drop_percent` (alerte, 10 %) dans `config/settings.json`.
- **Design :** variables CSS en haut de `static/css/style.css`.

## ⚠️ À savoir

- Les **prix de référence, specs et scores de performance** du catalogue sont des estimations de départ : vérifie-les (et ajoute les EAN) avant de passer en mode réel.
- Les tâches planifiées de GitHub peuvent avoir quelques minutes de retard aux heures chargées : c'est normal.
- Google réserve aujourd'hui l'affichage enrichi des FAQ à certains sites ; les données `FAQPage` restent utiles pour la compréhension de la page.
- La mention d'affiliation est dans le pied de page. Garde-la : elle est obligatoire pour les programmes d'affiliation et pour la loi française.
