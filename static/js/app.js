/* Radar Hardware FR — recherche, filtres et profils d'achat instantanés (JavaScript vanilla, sans dépendance). */
(function () {
  "use strict";
  var form = document.getElementById("filters");
  var grid = document.getElementById("grid");
  if (!form || !grid) return;

  var $ = function (id) { return document.getElementById(id); };
  var q = $("f-q"), cat = $("f-cat"), brand = $("f-brand"), price = $("f-price"),
      priceOut = $("f-price-out"), deals = $("f-deals"), sort = $("f-sort"),
      count = $("f-count"), empty = $("empty"), resetBtn = $("profiles-reset");
  var pills = Array.prototype.slice.call(document.querySelectorAll(".pill[data-profile]"));
  var cards = Array.prototype.slice.call(grid.querySelectorAll(".product-card"));
  var STORE = "radar-filters";
  var state = { profile: "", minDiscount: 0 };

  // Normalise le texte : minuscules, sans accents (« mémoire » == « memoire »)
  function norm(s) {
    return (s || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/\s+/g, " ").trim();
  }
  cards.forEach(function (c) {
    c._name = norm(c.dataset.name + " " + c.dataset.brand);
    c._profiles = (c.dataset.profiles || "").split(" ");
  });

  var sorters = {
    score: function (a, b) { return b.dataset.score - a.dataset.score; },
    discount: function (a, b) { return b.dataset.discount - a.dataset.discount; },
    // Indice relatif à la catégorie : 1 = meilleur rapport performance / prix de sa catégorie
    ratio: function (a, b) { return a.dataset.ratio - b.dataset.ratio; },
    "price-asc": function (a, b) { return a.dataset.price - b.dataset.price; },
    "price-desc": function (a, b) { return b.dataset.price - a.dataset.price; }
  };

  function apply(save) {
    var terms = norm(q.value).split(" ").filter(Boolean);
    var c = cat ? cat.value : "", b = brand.value, max = +price.value;
    var onlyDeals = deals.checked || state.profile === "deals";
    var prof = (state.profile === "upgrade" || state.profile === "sans-compromis") ? state.profile : "";
    var visible = 0;
    priceOut.textContent = max + " €";
    cards.forEach(function (card) {
      var ok = terms.every(function (t) { return card._name.indexOf(t) !== -1; }) &&
        (!c || card.dataset.cat === c) &&
        (!b || card.dataset.brand === b) &&
        (+card.dataset.price <= max) &&
        (!onlyDeals || card.dataset.deal === "1") &&
        (!prof || card._profiles.indexOf(prof) !== -1) &&
        (!state.minDiscount || +card.dataset.discount >= state.minDiscount);
      card.hidden = !ok;
      if (ok) visible++;
    });
    var fn = sorters[sort.value] || sorters.score;
    cards.slice().sort(fn).forEach(function (card) { grid.appendChild(card); });
    count.textContent = visible + " composant" + (visible > 1 ? "s" : "") + " affiché" + (visible > 1 ? "s" : "") +
      (state.minDiscount ? " · baisses de " + state.minDiscount + " % minimum" : "");
    empty.hidden = visible !== 0;
    pills.forEach(function (p) { p.setAttribute("aria-pressed", p.dataset.profile === state.profile ? "true" : "false"); });
    if (resetBtn) resetBtn.hidden = !(state.profile || state.minDiscount || onlyDeals || c || b || terms.length || max < +price.max);
    if (save !== false) {
      try {
        sessionStorage.setItem(STORE, JSON.stringify({ c: c, b: b, d: deals.checked, s: sort.value, p: state.profile }));
      } catch (e) { /* stockage indisponible : sans importance */ }
    }
  }

  function resetAll() {
    q.value = ""; if (cat) cat.value = ""; brand.value = ""; price.value = price.max;
    deals.checked = false; sort.value = "score"; state.profile = ""; state.minDiscount = 0;
    apply();
  }

  // Profils d'achat : exclusifs, un second clic désactive le profil
  pills.forEach(function (pill) {
    pill.addEventListener("click", function () {
      var p = pill.dataset.profile;
      state.minDiscount = 0;
      state.profile = state.profile === p ? "" : p;
      if (state.profile === "ratio") sort.value = "ratio";
      else if (sort.value === "ratio") sort.value = "score";
      if (state.profile === "deals") sort.value = "discount";
      apply();
    });
  });
  if (resetBtn) resetBtn.addEventListener("click", resetAll);
  var emptyReset = $("empty-reset");
  if (emptyReset) emptyReset.addEventListener("click", resetAll);

  // Bouton principal de la hero : vraies baisses de 10 % minimum, puis défilement doux
  var heroCta = $("cta-deals");
  if (heroCta) {
    heroCta.addEventListener("click", function (e) {
      e.preventDefault();
      resetAll();
      state.minDiscount = +heroCta.dataset.minDiscount || 10;
      sort.value = "discount";
      apply();
      var target = $("tous");
      if (target) target.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }

  // Restaure les derniers filtres de la session (confort de navigation)
  try {
    var saved = JSON.parse(sessionStorage.getItem(STORE) || "null");
    if (saved) {
      if (cat && saved.c) cat.value = saved.c;
      if (saved.b && brand.querySelector('option[value="' + saved.b + '"]')) brand.value = saved.b;
      deals.checked = !!saved.d;
      if (saved.s) sort.value = saved.s;
      if (saved.p && pills.some(function (p) { return p.dataset.profile === saved.p; })) state.profile = saved.p;
    }
  } catch (e) { /* ignore */ }

  var timer;
  q.addEventListener("input", function () { clearTimeout(timer); timer = setTimeout(apply, 60); });
  [cat, brand, deals, sort].forEach(function (el) { if (el) el.addEventListener("change", function () { state.minDiscount = 0; apply(); }); });
  price.addEventListener("input", function () { apply(); });
  apply(false);
})();
