/* BuildRadar — le configurateur PC de Radar Hardware (100 % côté client).
   Compatibilité : socket CPU/carte mère/refroidissement, type de RAM, format carte mère/boîtier,
   longueur GPU, hauteur ventirad / radiateur AIO, puissance d'alimentation.
   Badges de choix : Meilleur prix, Populaire, Recommandé (selon la config en cours).
   Optimiseur de panier : le moins cher / 2 marchands max / un seul marchand, frais de port comptés une fois par marchand. */
(function () {
  "use strict";
  var RH = window.RH || {}, $ = function (id) { return document.getElementById(id); };
  var body = document.body, ROOT = body.getAttribute("data-root") || "";
  var data; try { data = JSON.parse($("cfg-data").textContent); } catch (e) { return; }
  var euro = RH.euro || function (v) { return v.toFixed(2).replace(".", ",") + " €"; };
  var norm = RH.norm || function (s) { return (s || "").toLowerCase(); };
  var M = data.merchants; // [clé, nom, pays, frais de port, gratuit dès]
  var byCat = {}, bySlug = {};
  data.items.forEach(function (it) { (byCat[it.c] = byCat[it.c] || []).push(it); bySlug[it.s] = it; it._n = norm(it.n + " " + it.b); });
  var sel = {}, mode = "cheap", STORE = "radar-config", DONE = "radar-config-done";
  var isFR = function () { return body.getAttribute("data-region") === "fr"; };
  function offer(it) { return isFR() ? it.f : it.e; }
  function get(c) { return sel[c] && bySlug[sel[c]]; }

  /* ---------- Puissance ---------- */
  function estimatedWatts() {
    var c = get("cpu"), g = get("gpu");
    if (!c && !g) return 0;
    return (c ? c.k.power_w || 0 : 0) + (g ? g.k.power_w || 0 : 0) + 120;
  }
  function neededPsu() { var w = estimatedWatts(); return w ? Math.ceil(w * 1.25) : 0; }

  /* ---------- Compatibilité ---------- */
  function problems(it, s) {
    var k = it.k, out = [], g = function (c) { return s[c] && s[c] !== it.s ? bySlug[s[c]] : null; };
    var cpu = g("cpu"), mb = g("motherboard"), ram = g("ram"), gpu = g("gpu"), cool = g("cooler"), box = g("case");
    if (it.c === "cpu") {
      if (mb && mb.k.socket !== k.socket) out.push("Socket " + k.socket + " ≠ carte mère " + mb.k.socket);
      if (mb && k.ram.indexOf(mb.k.ram) < 0) out.push("Mémoire " + mb.k.ram + " non supportée");
      if (cool && cool.k.sockets.indexOf(k.socket) < 0) out.push("Refroidissement non compatible " + k.socket);
    } else if (it.c === "motherboard") {
      if (cpu && cpu.k.socket !== k.socket) out.push("Socket " + k.socket + " ≠ processeur " + cpu.k.socket);
      if (cpu && cpu.k.ram.indexOf(k.ram) < 0) out.push("Le processeur ne supporte pas la " + k.ram);
      if (ram && ram.k.ram !== k.ram) out.push("Carte mère " + k.ram + " ≠ mémoire " + ram.k.ram);
      if (box && box.k.forms.indexOf(k.form) < 0) out.push("Format " + k.form + " non supporté par le boîtier");
    } else if (it.c === "ram") {
      if (mb && mb.k.ram !== k.ram) out.push("Carte mère " + mb.k.ram + " uniquement");
      else if (!mb && cpu && cpu.k.ram.indexOf(k.ram) < 0) out.push("Processeur incompatible " + k.ram);
    } else if (it.c === "gpu") {
      if (box && k.length_mm > box.k.max_gpu_mm) out.push("Trop longue (" + k.length_mm + " mm > " + box.k.max_gpu_mm + " mm)");
    } else if (it.c === "cooler") {
      if (cpu && k.sockets.indexOf(cpu.k.socket) < 0) out.push("Socket " + cpu.k.socket + " non supporté");
      if (box && k.kind === "air" && k.height_mm > box.k.max_cooler_mm) out.push("Trop haut (" + k.height_mm + " mm > " + box.k.max_cooler_mm + " mm)");
      if (box && k.kind === "aio" && k.radiator_mm > box.k.max_radiator_mm) out.push("Radiateur " + k.radiator_mm + " mm non supporté");
    } else if (it.c === "case") {
      if (mb && k.forms.indexOf(mb.k.form) < 0) out.push("Carte mère " + mb.k.form + " non supportée");
      if (gpu && gpu.k.length_mm > k.max_gpu_mm) out.push("GPU trop longue pour ce boîtier");
      if (cool && cool.k.kind === "air" && cool.k.height_mm > k.max_cooler_mm) out.push("Ventirad trop haut pour ce boîtier");
      if (cool && cool.k.kind === "aio" && cool.k.radiator_mm > k.max_radiator_mm) out.push("Radiateur trop grand pour ce boîtier");
    } else if (it.c === "psu") {
      var need = neededPsu();
      if (need && k.watts < need) out.push("Puissance insuffisante (" + need + " W conseillés)");
    }
    return out;
  }

  /* ---------- Recommandation selon la config en cours ---------- */
  function price(it) { var o = offer(it); return o ? o[0] : 1e9; }
  function best(list, score) { var b = null, bs = -1e18; list.forEach(function (it) { var v = score(it); if (v > bs) { bs = v; b = it; } }); return b; }
  function cheapest(list) { return best(list, function (it) { return -price(it); }); }
  function recommend(cat, list) {
    if (!list.length) return null;
    var cpu = get("cpu"), gpu = get("gpu"), pick = null, why = "";
    var ratio = function (it) { return (it.pp || 0) / price(it); };
    if (cat === "cpu") {
      var min = gpu ? (gpu.pp >= 80 ? 85 : gpu.pp >= 55 ? 72 : 60) : 70;
      pick = best(list.filter(function (it) { return it.pp >= min; }), ratio) || best(list, ratio);
      why = gpu ? "Assez puissant pour ta carte graphique, au meilleur rapport perf/prix" : "Meilleur rapport performance gaming / prix";
    } else if (cat === "motherboard") {
      var high = cpu && cpu.pp >= 85, good = /B850|X870|X670E|Z790|Z890/;
      var pool = list.filter(function (it) { return it.k.wifi && (!high || good.test(it.k.chipset)); });
      pick = cheapest(pool.length ? pool : list.filter(function (it) { return it.k.wifi; })) || cheapest(list);
      why = high ? "Chipset récent et Wi-Fi, à la hauteur de ton processeur" : "Wi-Fi intégré, au meilleur prix";
    } else if (cat === "ram") {
      var r32 = list.filter(function (it) { return it.k.gb === 32; });
      pick = best(r32.length ? r32 : list, ratio);
      why = "32 Go, la quantité idéale pour jouer, au meilleur rapport perf/prix";
    } else if (cat === "gpu") {
      var lo = 25, hi = 60;
      if (cpu && cpu.pp >= 85) { lo = 60; hi = 120; } else if (cpu && cpu.pp >= 72) { lo = 40; hi = 85; }
      pick = best(list.filter(function (it) { return it.pp >= lo && it.pp <= hi; }), ratio) || best(list, ratio);
      why = cpu ? "Bien équilibrée avec ton processeur, meilleur rapport perf/prix" : "Meilleur rapport performance / prix";
    } else if (cat === "ssd") {
      var t2 = list.filter(function (it) { return it.k.tb === 2; });
      pick = best(t2.length ? t2 : list, ratio);
      why = "2 To, assez pour une grosse bibliothèque de jeux, meilleur rapport perf/prix";
    } else if (cat === "cooler") {
      var need = cpu ? Math.ceil(cpu.k.power_w * 1.1) : 180;
      pick = cheapest(list.filter(function (it) { return it.k.capacity_w >= need; })) || cheapest(list);
      why = "Dissipe au moins " + need + " W, assez pour ton processeur, au meilleur prix";
    } else if (cat === "case") {
      var pool2 = list.filter(function (it) { return !gpu || it.k.max_gpu_mm >= gpu.k.length_mm + 20; });
      pick = cheapest(pool2.length ? pool2 : list);
      why = gpu ? "Marge confortable pour ta carte graphique, au meilleur prix" : "Compatible avec ta config, au meilleur prix";
    } else if (cat === "psu") {
      var w = neededPsu() || 650, modern = gpu && gpu.pp >= 60;
      var pool3 = list.filter(function (it) { return it.k.watts >= w && it.k.gold && (!modern || it.k.atx3); });
      pick = cheapest(pool3.length ? pool3 : list.filter(function (it) { return it.k.watts >= w; })) || cheapest(list);
      why = "80+ Gold, " + (modern ? "ATX 3, " : "") + "assez puissante pour ta config (" + w + " W conseillés)";
    }
    return pick ? { s: pick.s, why: why } : null;
  }

  /* ---------- Rendu des étapes ---------- */
  function renderStep(li) {
    var cat = li.getAttribute("data-cat"), it = get(cat);
    var choice = li.querySelector(".cfg-choice"), pr = li.querySelector(".cfg-price"),
        open = li.querySelector(".cfg-open"), rm = li.querySelector(".cfg-remove");
    li.classList.toggle("is-set", !!it);
    if (it) {
      choice.classList.remove("muted"); choice.innerHTML = "";
      var a = document.createElement("a"); a.href = ROOT + it.u; a.textContent = it.n; choice.appendChild(a);
      var o = offer(it);
      pr.innerHTML = o ? euro(o[0]) + "<small>" + o[1] + " · " + o[2] + "</small>" : "<small>Indisponible dans cette zone</small>";
      open.querySelector("span").textContent = "Changer"; rm.hidden = false;
    } else {
      choice.classList.add("muted"); choice.textContent = "Aucun composant choisi"; pr.innerHTML = "";
      open.querySelector("span").textContent = "Choisir"; rm.hidden = true;
    }
  }
  function badge(cls, txt) { var b = document.createElement("span"); b.className = "pick " + cls; b.textContent = txt; return b; }

  function renderPicker(li) {
    var cat = li.getAttribute("data-cat"), list = li.querySelector(".cfg-list"),
        qv = norm(li.querySelector(".cfg-q").value), sortBy = li.querySelector(".cfg-sort").value;
    var compatible = (byCat[cat] || []).filter(function (it) { return !problems(it, sel).length && offer(it); });
    var shown = compatible.filter(function (it) { return !qv || it._n.indexOf(qv) >= 0; });
    var hidden = (byCat[cat] || []).length - compatible.length;
    var reco = recommend(cat, compatible), low = cheapest(compatible);
    shown.sort(sortBy === "name" ? function (a, b) { return a.n.localeCompare(b.n); } : function (a, b) { return price(a) - price(b); });
    if (reco && sortBy === "price") shown.sort(function (a, b) { return (b.s === reco.s) - (a.s === reco.s); }); // recommandé en tête
    li.querySelector(".cfg-hidden").textContent = compatible.length + " compatible" + (compatible.length > 1 ? "s" : "") +
      (hidden ? " · " + hidden + " masqué" + (hidden > 1 ? "s" : "") + " (incompatibles ou indisponibles)" : "");
    list.innerHTML = "";
    shown.forEach(function (it) {
      var o = offer(it), b = document.createElement("button"); b.type = "button"; b.className = "cfg-item";
      var isReco = reco && reco.s === it.s; if (isReco) b.classList.add("is-reco");
      var img = document.createElement("img"); img.src = ROOT + it.i; img.alt = ""; img.loading = "lazy";
      var mid = document.createElement("span");
      var nm = document.createElement("span"); nm.className = "cfg-item-name"; nm.textContent = it.n;
      var sub = document.createElement("span"); sub.className = "cfg-item-sub"; sub.textContent = spec(it);
      var badges = document.createElement("span"); badges.className = "cfg-badges";
      if (isReco) badges.appendChild(badge("pick-reco", "Recommandé"));
      if (low && low.s === it.s) badges.appendChild(badge("pick-price", "Meilleur prix"));
      if (it.pop) badges.appendChild(badge("pick-pop", "Populaire"));
      mid.appendChild(nm); mid.appendChild(sub); if (badges.childNodes.length) mid.appendChild(badges);
      if (isReco) { var why = document.createElement("span"); why.className = "cfg-reco-why"; why.textContent = reco.why; mid.appendChild(why); }
      var p = document.createElement("span"); p.className = "cfg-item-price"; p.innerHTML = euro(o[0]) + "<small>" + o[1] + " · " + o[2] + "</small>";
      b.appendChild(img); b.appendChild(mid); b.appendChild(p);
      b.addEventListener("click", function () { sel[cat] = it.s; closeAll(); update(); openNext(li); });
      var w = document.createElement("li"); w.appendChild(b); list.appendChild(w);
    });
  }
  function spec(it) {
    var k = it.k;
    switch (it.c) {
      case "cpu": return k.socket + " · " + k.ram.join("/") + " · " + k.power_w + " W max";
      case "motherboard": return k.socket + " · " + k.chipset + " · " + k.form + " · " + k.ram + (k.wifi ? " · Wi-Fi" : "");
      case "ram": return k.ram + " · " + k.gb + " Go · " + k.mhz + " MHz";
      case "gpu": return k.length_mm + " mm · " + k.power_w + " W";
      case "ssd": return k.tb + " To · " + k.interface;
      case "cooler": return (k.kind === "air" ? "Ventirad · " + k.height_mm + " mm" : "AIO " + k.radiator_mm + " mm") + " · " + k.capacity_w + " W";
      case "case": return k.forms.join(", ") + " · GPU " + k.max_gpu_mm + " mm";
      case "psu": return k.watts + " W" + (k.gold ? " · 80+ Gold" : "") + (k.atx3 ? " · ATX 3" : "");
      default: return it.b;
    }
  }
  var steps = Array.prototype.slice.call(document.querySelectorAll(".cfg-step"));
  function closeAll() { steps.forEach(function (li) { li.querySelector(".cfg-picker").hidden = true; li.classList.remove("is-open"); }); }
  function openStep(li) { closeAll(); li.classList.add("is-open"); li.querySelector(".cfg-picker").hidden = false; renderPicker(li); }
  function openNext(li) {
    var i = steps.indexOf(li);
    for (var j = i + 1; j < steps.length; j++) {
      if (!sel[steps[j].getAttribute("data-cat")]) { openStep(steps[j]); steps[j].scrollIntoView({ behavior: "smooth", block: "nearest" }); return; }
    }
  }

  /* ---------- Optimiseur de panier ---------- */
  function shipFor(mi, subtotal) {
    var cost = M[mi][3], free = M[mi][4];
    if (cost === null || cost === undefined) return 0;
    if (free !== null && free !== undefined && subtotal >= free) return 0;
    return cost;
  }
  function evalBasket(chosen, allowed) {
    // Pour chaque pièce, l'offre la moins chère parmi les marchands autorisés ; port compté une fois par marchand
    var lines = [], groups = {};
    for (var i = 0; i < chosen.length; i++) {
      var it = chosen[i], bestO = null;
      it.o.forEach(function (o) { if (allowed[o[0]] && (!bestO || o[1] < bestO[1])) bestO = o; });
      if (!bestO) return null;
      lines.push({ it: it, mi: bestO[0], p: bestO[1], url: bestO[2] });
      groups[bestO[0]] = (groups[bestO[0]] || 0) + bestO[1];
    }
    var total = 0, ship = 0;
    Object.keys(groups).forEach(function (mi) { total += groups[mi]; ship += shipFor(+mi, groups[mi]); });
    return { lines: lines, total: total + ship, ship: ship, merchants: Object.keys(groups).length };
  }
  function optimise(chosen) {
    var pool = [];
    M.forEach(function (m, i) { if (!isFR() || m[2] === "FR") pool.push(i); });
    var out = { cheap: null, two: null, one: null };
    var consider = function (subset) {
      var allowed = {}; subset.forEach(function (i) { allowed[i] = true; });
      var r = evalBasket(chosen, allowed); if (!r) return;
      if (!out.cheap || r.total < out.cheap.total - 0.001) out.cheap = r;
      if (r.merchants <= 2 && (!out.two || r.total < out.two.total - 0.001)) out.two = r;
      if (r.merchants === 1 && (!out.one || r.total < out.one.total - 0.001)) out.one = r;
    };
    consider(pool); // toutes les offres : la moins chère pièce par pièce
    var n = pool.length;
    for (var a = 0; a < n; a++) {
      consider([pool[a]]);
      for (var b = a + 1; b < n; b++) {
        consider([pool[a], pool[b]]);
        for (var c = b + 1; c < n; c++) {
          consider([pool[a], pool[b], pool[c]]);
          for (var d = c + 1; d < n; d++) consider([pool[a], pool[b], pool[c], pool[d]]);
        }
      }
    }
    return out;
  }

  /* ---------- Récapitulatif ---------- */
  function doneSet() { try { return JSON.parse((RH.store && RH.store(DONE)) || "{}") || {}; } catch (e) { return {}; } }
  function update() {
    steps.forEach(renderStep);
    var chosen = [], n = 0, missing = 0, avgSum = 0, checks = [];
    data.steps.forEach(function (st) {
      var it = get(st[0]); if (!it) return;
      n++;
      if (!offer(it) || !it.o.some(function (o) { return !isFR() || M[o[0]][2] === "FR"; })) { missing++; return; }
      chosen.push(it); if (it.a) avgSum += it.a;
      problems(it, sel).forEach(function (p) { checks.push({ ok: false, t: st[1] + " : " + p }); });
    });
    var c = get("cpu"), mb = get("motherboard"), ram = get("ram"), box = get("case"), gpu = get("gpu"), cool = get("cooler"), psu = get("psu");
    if (c && mb && c.k.socket === mb.k.socket) checks.push({ ok: true, t: "Socket " + c.k.socket + " compatible" });
    if (mb && ram && mb.k.ram === ram.k.ram) checks.push({ ok: true, t: "Mémoire " + ram.k.ram + " compatible" });
    if (mb && box && box.k.forms.indexOf(mb.k.form) >= 0) checks.push({ ok: true, t: "Format " + mb.k.form + " accepté par le boîtier" });
    if (gpu && box && gpu.k.length_mm <= box.k.max_gpu_mm) checks.push({ ok: true, t: "Carte graphique : " + gpu.k.length_mm + " / " + box.k.max_gpu_mm + " mm" });
    if (cool && box && !problems(cool, sel).length) checks.push({ ok: true, t: "Refroidissement adapté au boîtier" });
    if (cool && c && cool.k.capacity_w < c.k.power_w) checks.push({ ok: false, t: "Refroidissement un peu juste pour ce processeur (" + cool.k.capacity_w + " W pour " + c.k.power_w + " W)" });
    if (psu && neededPsu() && psu.k.watts >= neededPsu()) checks.push({ ok: true, t: "Alimentation suffisante (" + psu.k.watts + " W)" });
    if (missing) checks.push({ ok: false, t: missing + " pièce(s) indisponible(s) dans la zone choisie" });

    var opt = chosen.length ? optimise(chosen) : { cheap: null, two: null, one: null };
    if (!opt[mode]) mode = "cheap";
    var basket = opt[mode];
    $("cfg-total").textContent = euro(basket ? basket.total : 0);
    var save = basket ? avgSum - (basket.total - basket.ship) : 0;
    $("cfg-save").textContent = basket && save >= 1 ? "Économie de " + euro(save) + " par rapport aux prix moyens 30 jours" : "";
    $("cfg-count").textContent = n + " / " + data.steps.length;
    var w = estimatedWatts(); $("cfg-watts").textContent = w ? w + " W" : "—"; $("cfg-psu").textContent = w ? "≥ " + neededPsu() + " W" : "—";

    // Options de panier
    var bk = $("cfg-basket"); bk.hidden = chosen.length < 2;
    bk.querySelectorAll(".basket-opt").forEach(function (btn) {
      var r = opt[btn.dataset.mode], small = btn.querySelector("small"), val = btn.querySelector(".mono");
      btn.disabled = !r; btn.setAttribute("aria-pressed", btn.dataset.mode === mode ? "true" : "false");
      if (!r) { small.textContent = btn.dataset.mode === "one" ? "Aucun marchand ne propose toutes ces pièces" : "Indisponible"; val.textContent = ""; return; }
      var names = {}; r.lines.forEach(function (l) { names[M[l.mi][1]] = 1; });
      small.textContent = r.merchants + " commande" + (r.merchants > 1 ? "s" : "") + " · " + Object.keys(names).slice(0, 3).join(", ") + (r.merchants > 3 ? "…" : "");
      var delta = opt.cheap ? r.total - opt.cheap.total : 0;
      val.innerHTML = euro(r.total) + (delta >= 0.5 ? '<span class="delta">+' + euro(delta) + "</span>" : '<span class="delta">port inclus</span>');
    });

    // Contrôles
    var ul = $("cfg-checks"); ul.innerHTML = "";
    checks.forEach(function (ch) {
      var li = document.createElement("li"); li.className = ch.ok ? "ok" : "warn";
      li.innerHTML = ch.ok ? '<svg class="ico" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>'
                           : '<svg class="ico" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M12 3 2 20h20L12 3Z"/><path d="M12 10v4M12 17.5v.01"/></svg>';
      var sp = document.createElement("span"); sp.textContent = ch.t; li.appendChild(sp); ul.appendChild(li);
    });
    $("cfg-buy").disabled = $("cfg-share").disabled = !basket;

    // Liste d'achat regroupée par marchand, avec cases « commandé »
    var bl = $("cfg-buylist"); bl.innerHTML = "";
    if (basket) {
      var done = doneSet(), groups = {};
      basket.lines.forEach(function (l) { (groups[l.mi] = groups[l.mi] || []).push(l); });
      var h = document.createElement("h3"); h.textContent = basket.merchants === 1 ? "Une seule commande" : basket.merchants + " commandes à passer"; bl.appendChild(h);
      if (document.body.getAttribute("data-demo")) {
        var dn = document.createElement("p"); dn.className = "cfg-ship";
        dn.textContent = "Mode démonstration : prix estimés, chaque lien ouvre la recherche du marchand où le prix exact fait foi.";
        bl.appendChild(dn);
      }
      Object.keys(groups).forEach(function (mi) {
        var g = groups[mi], sub = g.reduce(function (s, l) { return s + l.p; }, 0), ship = shipFor(+mi, sub);
        var box2 = document.createElement("div"); box2.className = "cfg-merchant";
        var head = document.createElement("div"); head.className = "cfg-merchant-head";
        head.innerHTML = '<span></span><span class="mono"></span>'; head.firstChild.textContent = M[mi][1] + " (" + M[mi][2] + ")"; head.lastChild.textContent = euro(sub + ship);
        box2.appendChild(head);
        var sh = document.createElement("p"); sh.className = "cfg-ship"; sh.textContent = ship ? "Livraison estimée : " + euro(ship) : "Livraison estimée offerte"; box2.appendChild(sh);
        g.forEach(function (l) {
          var lab = document.createElement("label"); if (done[l.url]) lab.className = "done";
          var cb = document.createElement("input"); cb.type = "checkbox"; cb.checked = !!done[l.url]; cb.title = "Marquer comme commandé";
          cb.addEventListener("change", function () { var d = doneSet(); if (cb.checked) d[l.url] = 1; else delete d[l.url]; RH.store && RH.store(DONE, JSON.stringify(d)); lab.className = cb.checked ? "done" : ""; });
          var a = document.createElement("a"); a.href = l.url; a.target = "_blank"; a.rel = "nofollow sponsored noopener";
          a.innerHTML = "<span></span><span></span>"; a.firstChild.textContent = l.it.n; a.lastChild.textContent = euro(l.p);
          lab.appendChild(cb); lab.appendChild(a); box2.appendChild(lab);
        });
        bl.appendChild(box2);
      });
    }
    try { RH.store && RH.store(STORE, JSON.stringify(sel)); } catch (e) { /* ignore */ }
  }

  /* ---------- Événements ---------- */
  steps.forEach(function (li) {
    li.querySelector(".cfg-open").addEventListener("click", function () { if (li.classList.contains("is-open")) closeAll(); else openStep(li); });
    li.querySelector(".cfg-remove").addEventListener("click", function () { delete sel[li.getAttribute("data-cat")]; closeAll(); update(); });
    li.querySelector(".cfg-q").addEventListener("input", function () { renderPicker(li); });
    li.querySelector(".cfg-sort").addEventListener("change", function () { renderPicker(li); });
  });
  document.querySelectorAll(".basket-opt").forEach(function (btn) { btn.addEventListener("click", function () { mode = btn.dataset.mode; update(); }); });
  $("cfg-buy").addEventListener("click", function () { var bl = $("cfg-buylist"); bl.hidden = !bl.hidden; if (!bl.hidden) bl.scrollIntoView({ behavior: "smooth", block: "nearest" }); });
  $("cfg-reset").addEventListener("click", function () { sel = {}; closeAll(); $("cfg-buylist").hidden = true; update(); openStep(steps[0]); });
  $("cfg-share").addEventListener("click", function () {
    var url = location.origin + location.pathname + "?c=" + data.steps.map(function (st) { return sel[st[0]] || ""; }).join(",");
    var toast = $("cfg-toast"), done = function (msg) { toast.textContent = msg; toast.hidden = false; setTimeout(function () { toast.hidden = true; }, 5000); };
    if (navigator.share) { navigator.share({ title: "Ma config BuildRadar", url: url }).catch(function () {}); return; }
    if (navigator.clipboard) navigator.clipboard.writeText(url).then(function () { done("Lien copié dans le presse-papiers."); }, function () { done(url); });
    else done(url);
  });
  if (RH.onRegion) RH.onRegion(function () { update(); steps.forEach(function (li) { if (li.classList.contains("is-open")) renderPicker(li); }); });

  /* ---------- Chargement : config partagée (?c=) ou dernière config ---------- */
  var shared = new URLSearchParams(location.search).get("c");
  if (shared) {
    shared.split(",").forEach(function (sl, i) { if (sl && bySlug[sl] && data.steps[i] && bySlug[sl].c === data.steps[i][0]) sel[data.steps[i][0]] = sl; });
  } else {
    try { var saved = JSON.parse((RH.store && RH.store(STORE)) || "null"); if (saved) Object.keys(saved).forEach(function (k) { if (bySlug[saved[k]]) sel[k] = saved[k]; }); } catch (e) { /* ignore */ }
  }
  update();
  if (!Object.keys(sel).length) openStep(steps[0]);
})();
