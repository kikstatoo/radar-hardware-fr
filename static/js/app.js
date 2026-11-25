/* Radar Hardware FR — recherche et filtres instantanés (JavaScript vanilla, sans dépendance). */
(function () {
  "use strict";
  var form = document.getElementById("filters");
  var grid = document.getElementById("grid");
  if (!form || !grid) return;

  var $ = function (id) { return document.getElementById(id); };
  var q = $("f-q"), cat = $("f-cat"), brand = $("f-brand"), price = $("f-price"),
      priceOut = $("f-price-out"), deals = $("f-deals"), sort = $("f-sort"),
      count = $("f-count"), empty = $("empty");
  var cards = Array.prototype.slice.call(grid.querySelectorAll(".product-card"));
  var STORE = "radar-filters";

  // Normalise le texte : minuscules, sans accents (« mémoire » == « memoire »)
  function norm(s) {
    return (s || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/\s+/g, " ").trim();
  }
  cards.forEach(function (c) { c._name = norm(c.dataset.name + " " + c.dataset.brand); });

  var sorters = {
    score: function (a, b) { return b.dataset.score - a.dataset.score; },
    discount: function (a, b) { return b.dataset.discount - a.dataset.discount; },
    ratio: function (a, b) { return a.dataset.ratio - b.dataset.ratio; },
    "price-asc": function (a, b) { return a.dataset.price - b.dataset.price; },
    "price-desc": function (a, b) { return b.dataset.price - a.dataset.price; }
  };

  function apply() {
    var terms = norm(q.value).split(" ").filter(Boolean);
    var c = cat ? cat.value : "", b = brand.value, max = +price.value, onlyDeals = deals.checked;
    var visible = 0;
    priceOut.textContent = max + " €";
    cards.forEach(function (card) {
      var ok = terms.every(function (t) { return card._name.indexOf(t) !== -1; }) &&
        (!c || card.dataset.cat === c) &&
        (!b || card.dataset.brand === b) &&
        (+card.dataset.price <= max) &&
        (!onlyDeals || card.dataset.deal === "1");
      card.hidden = !ok;
      if (ok) visible++;
    });
    var fn = sorters[sort.value] || sorters.score;
    cards.slice().sort(fn).forEach(function (card) { grid.appendChild(card); });
    count.textContent = visible + " composant" + (visible > 1 ? "s" : "") + " affiché" + (visible > 1 ? "s" : "");
    empty.hidden = visible !== 0;
    try {
      sessionStorage.setItem(STORE, JSON.stringify({ c: c, b: b, d: onlyDeals, s: sort.value }));
    } catch (e) { /* stockage indisponible : sans importance */ }
  }

  // Restaure les derniers filtres de la session (confort de navigation)
  try {
    var saved = JSON.parse(sessionStorage.getItem(STORE) || "null");
    if (saved) {
      if (cat && saved.c) cat.value = saved.c;
      if (saved.b && brand.querySelector('option[value="' + saved.b + '"]')) brand.value = saved.b;
      deals.checked = !!saved.d;
      if (saved.s) sort.value = saved.s;
    }
  } catch (e) { /* ignore */ }

  var timer;
  q.addEventListener("input", function () { clearTimeout(timer); timer = setTimeout(apply, 60); });
  [cat, brand, deals, sort].forEach(function (el) { if (el) el.addEventListener("change", apply); });
  price.addEventListener("input", apply);
  apply();
})();
