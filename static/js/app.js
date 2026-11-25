/* Radar Hardware Europe — JavaScript vanilla, sans dépendance :
   zone France / Europe, recherche avec autocomplétion, carrousel, filtres, pagination, graphique. */
(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };
  var body = document.body, ROOT = body.getAttribute("data-root") || "";
  function store(k, v) { try { if (v === undefined) return localStorage.getItem(k); localStorage.setItem(k, v); } catch (e) { return null; } }
  function norm(s) { return (s || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/\s+/g, " ").trim(); }
  function euro(v) { return v.toFixed(2).replace(".", ",").replace(/\B(?=(\d{3})+(?!\d))/g, " ") + " €"; }
  window.RH = { store: store, norm: norm, euro: euro };

  /* 1. Zone Europe / France */
  var regionSel = $("region-select"), onRegion = [];
  window.RH.onRegion = function (fn) { onRegion.push(fn); };
  function setRegion(r) {
    body.setAttribute("data-region", r === "fr" ? "fr" : "eu");
    if (regionSel) regionSel.value = body.getAttribute("data-region");
    store("radar-region", body.getAttribute("data-region"));
    onRegion.forEach(function (fn) { fn(); });
  }
  if (regionSel) regionSel.addEventListener("change", function () { setRegion(regionSel.value); });

  /* 2. Recherche avec autocomplétion */
  var index = [];
  try { index = JSON.parse(($("search-index") || {}).textContent || "[]"); } catch (e) { index = []; }
  index.forEach(function (it) { it._n = norm(it.n + " " + it.c); });
  var input = $("search-input"), list = $("search-results"), active = -1, matches = [];
  function closeList() { if (list) { list.hidden = true; input.setAttribute("aria-expanded", "false"); active = -1; } }
  function renderList() {
    var terms = norm(input.value).split(" ").filter(Boolean);
    if (!terms.length) { closeList(); return; }
    matches = index.filter(function (it) { return terms.every(function (t) { return it._n.indexOf(t) !== -1; }); }).slice(0, 8);
    list.innerHTML = "";
    if (!matches.length) { var e0 = document.createElement("li"); e0.className = "sr-empty"; e0.textContent = "Aucun composant trouvé"; list.appendChild(e0); }
    matches.forEach(function (it, i) {
      var li = document.createElement("li"); li.setAttribute("role", "option"); li.id = "sr-" + i;
      var a = document.createElement("a"); a.href = ROOT + it.u;
      var img = document.createElement("img"); img.src = ROOT + it.i; img.alt = ""; img.loading = "lazy";
      var txt = document.createElement("span");
      var n = document.createElement("span"); n.className = "sr-name"; n.textContent = it.n;
      var c = document.createElement("span"); c.className = "sr-cat"; c.textContent = it.c;
      txt.appendChild(n); txt.appendChild(c);
      var pr = document.createElement("span"); pr.className = "sr-price"; pr.textContent = it.p;
      a.appendChild(img); a.appendChild(txt); a.appendChild(pr); li.appendChild(a); list.appendChild(li);
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
        e.preventDefault(); var pick = matches[active >= 0 ? active : 0]; if (pick) window.location.href = ROOT + pick.u;
      } else if (e.key === "Escape") { closeList(); }
    });
    document.addEventListener("click", function (e) { if (!e.target.closest || !e.target.closest(".search")) closeList(); });
  }

  /* 3. Carrousel Top Deals (4,5 s, barre de progression, pause au survol, swipe natif) */
  var car = $("carousel"), track = $("carousel-track"), bar = $("carousel-bar");
  if (car && track && track.children.length) {
    var slides = track.children, dots = car.querySelectorAll(".carousel-dots button"), cur = 0, paused = false, t0 = performance.now(), DUR = 4500;
    var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    var go = function (i) {
      cur = (i + slides.length) % slides.length; t0 = performance.now();
      track.scrollTo({ left: slides[cur].offsetLeft - track.offsetLeft, behavior: reduce ? "auto" : "smooth" });
    };
    var sync = function () {
      var i = Math.round(track.scrollLeft / Math.max(1, track.clientWidth));
      if (i !== cur) { cur = i; t0 = performance.now(); }
      dots.forEach(function (d, k) { d.setAttribute("aria-selected", k === cur ? "true" : "false"); });
    };
    var st; track.addEventListener("scroll", function () { clearTimeout(st); st = setTimeout(sync, 80); }, { passive: true });
    document.querySelectorAll(".deals .prev").forEach(function (b) { b.addEventListener("click", function () { go(cur - 1); }); });
    document.querySelectorAll(".deals .next").forEach(function (b) { b.addEventListener("click", function () { go(cur + 1); }); });
    dots.forEach(function (d, k) { d.addEventListener("click", function () { go(k); }); });
    ["mouseenter", "focusin", "touchstart"].forEach(function (ev) { car.addEventListener(ev, function () { paused = true; }, { passive: true }); });
    ["mouseleave", "focusout"].forEach(function (ev) { car.addEventListener(ev, function () { paused = false; t0 = performance.now(); }); });
    car.addEventListener("touchend", function () { setTimeout(function () { paused = false; t0 = performance.now(); }, 3000); }, { passive: true });
    if (!reduce) {
      var tick = function (now) {
        if (paused || document.hidden) { t0 = now - (parseFloat(bar.style.width) || 0) / 100 * DUR; }
        var p = Math.min(1, (now - t0) / DUR);
        bar.style.width = (p * 100) + "%";
        if (p >= 1) go(cur + 1);
        requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
    }
  }

  /* 4. Graphique de prix interactif (infobulle) */
  document.querySelectorAll(".chart-card").forEach(function (card) {
    var svg = card.querySelector("svg.chart"), tip = card.querySelector(".chart-tip");
    if (!svg) return;
    var pts = []; try { pts = JSON.parse(card.getAttribute("data-points") || "[]"); } catch (e) { return; }
    if (pts.length < 2) return;
    var vb = svg.viewBox.baseVal, L = +svg.dataset.l, R = +svg.dataset.r, T = +svg.dataset.t, B = +svg.dataset.b,
        lo = +svg.dataset.lo, hi = +svg.dataset.hi, tmin = pts[0][0], tmax = pts[pts.length - 1][0];
    var cursor = svg.querySelector(".ch-cursor"), dot = svg.querySelector(".ch-dot");
    function move(e) {
      var r = svg.getBoundingClientRect(), cx = ((e.touches ? e.touches[0].clientX : e.clientX) - r.left) / r.width * vb.width;
      var t = tmin + (cx - L) / (vb.width - L - R) * (tmax - tmin), best = pts[0];
      pts.forEach(function (p) { if (Math.abs(p[0] - t) < Math.abs(best[0] - t)) best = p; });
      var x = L + (best[0] - tmin) / (tmax - tmin) * (vb.width - L - R), y = T + (hi - best[1]) / (hi - lo) * (vb.height - T - B);
      cursor.setAttribute("x1", x); cursor.setAttribute("x2", x); cursor.setAttribute("visibility", "visible");
      dot.setAttribute("cx", x); dot.setAttribute("cy", y); dot.setAttribute("visibility", "visible");
      var d = new Date(best[0] * 1000);
      tip.innerHTML = d.toLocaleDateString("fr-FR", { day: "2-digit", month: "short" }) + " " + d.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" }) + " · <b>" + euro(best[1]) + "</b>";
      tip.style.left = Math.max(60, Math.min(r.width - 60, x / vb.width * r.width)) + "px"; tip.hidden = false;
    }
    function leave() { tip.hidden = true; cursor.setAttribute("visibility", "hidden"); dot.setAttribute("visibility", "hidden"); }
    svg.addEventListener("mousemove", move); svg.addEventListener("touchmove", move, { passive: true });
    svg.addEventListener("mouseleave", leave); svg.addEventListener("touchend", leave);
  });

  /* 5. Filtres, tri, profils, pagination */
  var grid = $("grid");
  if (grid && $("f-sort")) {
    var q = $("f-q"), cat = $("f-cat"), brand = $("f-brand"), price = $("f-price"), priceOut = $("f-price-out"),
        deals = $("f-deals"), sort = $("f-sort"), count = $("f-count"), empty = $("empty"), resetBtn = $("profiles-reset"), more = $("show-more");
    var pills = Array.prototype.slice.call(document.querySelectorAll(".chip-btn[data-profile]"));
    var cards = Array.prototype.slice.call(grid.querySelectorAll(".pcard"));
    var PAGE = +(grid.getAttribute("data-page") || 24), limit = PAGE, profile = "";
    cards.forEach(function (c) { c._name = norm(c.dataset.name + " " + c.dataset.brand); c._profiles = (c.dataset.profiles || "").split(" "); });
    var priceOf = function (c) { return +(body.getAttribute("data-region") === "fr" ? c.dataset.priceFr : c.dataset.price) || 0; };
    var sorters = {
      score: function (a, b) { return b.dataset.score - a.dataset.score; },
      discount: function (a, b) { return b.dataset.discount - a.dataset.discount; },
      ratio: function (a, b) { return a.dataset.ratio - b.dataset.ratio; },
      "price-asc": function (a, b) { return (priceOf(a) || 1e9) - (priceOf(b) || 1e9); },
      "price-desc": function (a, b) { return priceOf(b) - priceOf(a); }
    };
    var apply = function (keepLimit) {
      if (!keepLimit) limit = PAGE;
      var terms = norm(q.value).split(" ").filter(Boolean), c = cat ? cat.value : "", b = brand.value, max = +price.value;
      var onlyDeals = deals.checked || profile === "deals", prof = (profile === "upgrade" || profile === "sans-compromis") ? profile : "";
      priceOut.textContent = max + " €";
      var ok = cards.filter(function (card) {
        var p = priceOf(card);
        return terms.every(function (t) { return card._name.indexOf(t) !== -1; }) && (!c || card.dataset.cat === c) &&
          (!b || card.dataset.brand === b) && p > 0 && p <= max && (!onlyDeals || card.dataset.deal === "1") &&
          (!prof || card._profiles.indexOf(prof) !== -1);
      });
      ok.sort(sorters[sort.value] || sorters.score);
      cards.forEach(function (card) { card.hidden = true; });
      ok.forEach(function (card, i) { grid.appendChild(card); card.hidden = i >= limit; });
      count.textContent = ok.length + " composant" + (ok.length > 1 ? "s" : "") + " · " +
        (body.getAttribute("data-region") === "fr" ? "marchands français" : "marchands européens, livrés en France");
      more.hidden = ok.length <= limit;
      if (!more.hidden) more.textContent = "Afficher plus (" + (ok.length - limit) + " restants)";
      empty.hidden = ok.length !== 0;
      pills.forEach(function (pl) { pl.setAttribute("aria-pressed", pl.dataset.profile === profile ? "true" : "false"); });
      resetBtn.hidden = !(profile || onlyDeals || c || b || terms.length || max < +price.max || sort.value !== "score");
    };
    var resetAll = function () { q.value = ""; if (cat) cat.value = ""; brand.value = ""; price.value = price.max; deals.checked = false; sort.value = "score"; profile = ""; apply(); };
    pills.forEach(function (pl) { pl.addEventListener("click", function () {
      profile = profile === pl.dataset.profile ? "" : pl.dataset.profile;
      sort.value = profile === "ratio" ? "ratio" : profile === "deals" ? "discount" : (sort.value === "ratio" || sort.value === "discount" ? "score" : sort.value);
      apply();
    }); });
    more.addEventListener("click", function () { limit += PAGE; apply(true); });
    resetBtn.addEventListener("click", resetAll);
    if ($("empty-reset")) $("empty-reset").addEventListener("click", resetAll);
    var tm; q.addEventListener("input", function () { clearTimeout(tm); tm = setTimeout(apply, 80); });
    [cat, brand, deals, sort].forEach(function (el) { if (el) el.addEventListener("change", function () { apply(); }); });
    price.addEventListener("input", function () { apply(); });
    window.RH.onRegion(function () { apply(true); });
  }
  setRegion(store("radar-region") || "eu");
})();
