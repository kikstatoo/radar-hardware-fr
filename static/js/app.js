/* Radar Hardware Europe — JavaScript vanilla, sans dépendance :
   zone France / Europe, recherche avec autocomplétion, carrousel, filtres et profils d'achat. */
(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };
  var body = document.body;
  var ROOT = body.getAttribute("data-root") || "";
  function store(key, val) {
    try { if (val === undefined) return localStorage.getItem(key); localStorage.setItem(key, val); } catch (e) { return null; }
  }
  function norm(s) {
    return (s || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/\s+/g, " ").trim();
  }

  /* ---------- 1. Zone : Europe livré en France / France uniquement ---------- */
  var regionSel = $("region-select");
  var applyFilters = function () {};
  function setRegion(r) {
    body.setAttribute("data-region", r === "fr" ? "fr" : "eu");
    if (regionSel) regionSel.value = body.getAttribute("data-region");
    store("radar-region", body.getAttribute("data-region"));
    applyFilters();
  }
  setRegion(store("radar-region") || "eu");
  if (regionSel) regionSel.addEventListener("change", function () { setRegion(regionSel.value); });

  /* ---------- 2. Recherche avec autocomplétion ---------- */
  var index = [];
  try { index = JSON.parse(($("search-index") || {}).textContent || "[]"); } catch (e) { index = []; }
  index.forEach(function (it) { it._n = norm(it.n + " " + it.c); });
  var input = $("search-input"), list = $("search-results"), active = -1, matches = [];
  function closeList() { if (list) { list.hidden = true; input.setAttribute("aria-expanded", "false"); active = -1; } }
  function renderList() {
    var terms = norm(input.value).split(" ").filter(Boolean);
    if (!terms.length) { closeList(); return; }
    matches = index.filter(function (it) { return terms.every(function (t) { return it._n.indexOf(t) !== -1; }); }).slice(0, 7);
    list.innerHTML = "";
    if (!matches.length) {
      var li0 = document.createElement("li"); li0.className = "sr-empty"; li0.textContent = "Aucun composant trouvé";
      list.appendChild(li0);
    }
    matches.forEach(function (it, i) {
      var li = document.createElement("li"); li.setAttribute("role", "option"); li.id = "sr-" + i;
      var a = document.createElement("a"); a.href = ROOT + it.u;
      var dot = document.createElement("span"); dot.className = "light light-" + it.l + " xs"; dot.innerHTML = '<span class="light-dot"></span>';
      var txt = document.createElement("span"); txt.innerHTML = '<span class="sr-name"></span><br><span class="sr-cat"></span>';
      txt.querySelector(".sr-name").textContent = it.n; txt.querySelector(".sr-cat").textContent = it.c;
      var pr = document.createElement("span"); pr.className = "mono accent"; pr.textContent = it.p;
      a.appendChild(dot); a.appendChild(txt); a.appendChild(pr); li.appendChild(a); list.appendChild(li);
    });
    list.hidden = false; input.setAttribute("aria-expanded", "true"); active = -1;
  }
  if (input && list) {
    input.addEventListener("input", renderList);
    input.addEventListener("focus", function () { if (input.value) renderList(); });
    input.addEventListener("keydown", function (e) {
      var items = list.querySelectorAll("[role=option]");
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault(); if (!items.length) return;
        active = (active + (e.key === "ArrowDown" ? 1 : -1) + items.length) % items.length;
        items.forEach(function (li, i) { li.setAttribute("aria-selected", i === active ? "true" : "false"); });
        input.setAttribute("aria-activedescendant", "sr-" + active);
      } else if (e.key === "Enter") {
        e.preventDefault(); var pick = matches[active >= 0 ? active : 0];
        if (pick) window.location.href = ROOT + pick.u;
      } else if (e.key === "Escape") { closeList(); }
    });
    document.addEventListener("click", function (e) { if (!e.target.closest || !e.target.closest(".search")) closeList(); });
  }

  /* ---------- 3. Carrousel « Top Deals » ---------- */
  var car = $("carousel"), track = $("carousel-track");
  if (car && track) {
    var slides = track.children, dots = car.querySelectorAll(".carousel-dots button"), cur = 0, timer = null, paused = false;
    var go = function (i) {
      cur = (i + slides.length) % slides.length;
      track.scrollTo({ left: slides[cur].offsetLeft - track.offsetLeft, behavior: "smooth" });
    };
    var sync = function () {
      var i = Math.round(track.scrollLeft / Math.max(1, track.clientWidth));
      cur = Math.max(0, Math.min(slides.length - 1, i));
      dots.forEach(function (d, k) { d.setAttribute("aria-selected", k === cur ? "true" : "false"); });
    };
    var t; track.addEventListener("scroll", function () { clearTimeout(t); t = setTimeout(sync, 60); }, { passive: true });
    car.querySelector(".prev").addEventListener("click", function () { go(cur - 1); });
    car.querySelector(".next").addEventListener("click", function () { go(cur + 1); });
    dots.forEach(function (d, k) { d.addEventListener("click", function () { go(k); }); });
    var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (!reduce) timer = setInterval(function () { if (!paused && !document.hidden) go(cur + 1); }, 5500);
    ["mouseenter", "focusin", "touchstart"].forEach(function (ev) { car.addEventListener(ev, function () { paused = true; }, { passive: true }); });
    ["mouseleave", "focusout"].forEach(function (ev) { car.addEventListener(ev, function () { paused = false; }); });
    car.addEventListener("touchend", function () { setTimeout(function () { paused = false; }, 4000); }, { passive: true });
  }

  /* ---------- 4. Filtres, tri et profils d'achat ---------- */
  var grid = $("grid");
  if (!grid || !$("f-sort")) return;
  var q = $("f-q"), cat = $("f-cat"), brand = $("f-brand"), price = $("f-price"), priceOut = $("f-price-out"),
      deals = $("f-deals"), sort = $("f-sort"), count = $("f-count"), empty = $("empty"), resetBtn = $("profiles-reset");
  var pills = Array.prototype.slice.call(document.querySelectorAll(".pill[data-profile]"));
  var cards = Array.prototype.slice.call(grid.querySelectorAll(".pcard"));
  var profile = "";
  cards.forEach(function (c) { c._name = norm(c.dataset.name + " " + c.dataset.brand); c._profiles = (c.dataset.profiles || "").split(" "); });
  function priceOf(c) { return +(body.getAttribute("data-region") === "fr" ? c.dataset.priceFr : c.dataset.price) || 0; }
  var sorters = {
    score: function (a, b) { return b.dataset.score - a.dataset.score; },
    discount: function (a, b) { return b.dataset.discount - a.dataset.discount; },
    ratio: function (a, b) { return a.dataset.ratio - b.dataset.ratio; }, // 1 = meilleur FPS/€ de sa catégorie
    "price-asc": function (a, b) { return (priceOf(a) || 1e9) - (priceOf(b) || 1e9); },
    "price-desc": function (a, b) { return priceOf(b) - priceOf(a); }
  };
  applyFilters = function () {
    var terms = norm(q.value).split(" ").filter(Boolean);
    var c = cat ? cat.value : "", b = brand.value, max = +price.value;
    var onlyDeals = deals.checked || profile === "deals";
    var prof = (profile === "upgrade" || profile === "sans-compromis") ? profile : "";
    var visible = 0;
    priceOut.textContent = max + " €";
    cards.forEach(function (card) {
      var p = priceOf(card);
      var ok = terms.every(function (t) { return card._name.indexOf(t) !== -1; }) &&
        (!c || card.dataset.cat === c) && (!b || card.dataset.brand === b) &&
        p > 0 && p <= max && (!onlyDeals || card.dataset.deal === "1") &&
        (!prof || card._profiles.indexOf(prof) !== -1);
      card.hidden = !ok;
      if (ok) visible++;
    });
    cards.slice().sort(sorters[sort.value] || sorters.score).forEach(function (card) { grid.appendChild(card); });
    count.textContent = visible + " composant" + (visible > 1 ? "s" : "") + " · prix " +
      (body.getAttribute("data-region") === "fr" ? "chez les marchands français" : "livrés en France depuis l'Europe");
    empty.hidden = visible !== 0;
    pills.forEach(function (pl) { pl.setAttribute("aria-pressed", pl.dataset.profile === profile ? "true" : "false"); });
    resetBtn.hidden = !(profile || onlyDeals || c || b || terms.length || max < +price.max || sort.value !== "score");
  };
  function resetAll() {
    q.value = ""; if (cat) cat.value = ""; brand.value = ""; price.value = price.max; deals.checked = false;
    sort.value = "score"; profile = ""; applyFilters();
  }
  pills.forEach(function (pl) {
    pl.addEventListener("click", function () {
      profile = profile === pl.dataset.profile ? "" : pl.dataset.profile;
      sort.value = profile === "ratio" ? "ratio" : profile === "deals" ? "discount" : (sort.value === "ratio" || sort.value === "discount" ? "score" : sort.value);
      applyFilters();
    });
  });
  resetBtn.addEventListener("click", resetAll);
  if ($("empty-reset")) $("empty-reset").addEventListener("click", resetAll);
  var tmr;
  q.addEventListener("input", function () { clearTimeout(tmr); tmr = setTimeout(applyFilters, 60); });
  [cat, brand, deals, sort].forEach(function (el) { if (el) el.addEventListener("change", applyFilters); });
  price.addEventListener("input", applyFilters);
  applyFilters();
})();
