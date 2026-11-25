/* Radar Hardware Europe — Configurateur PC 100 % côté client.
   Compatibilité : socket CPU/carte mère/refroidissement, type de RAM, format carte mère/boîtier,
   longueur GPU, hauteur ventirad / radiateur AIO, puissance d'alimentation. */
(function () {
  "use strict";
  var RH = window.RH || {}, $ = function (id) { return document.getElementById(id); };
  var body = document.body, ROOT = body.getAttribute("data-root") || "";
  var data; try { data = JSON.parse($("cfg-data").textContent); } catch (e) { return; }
  var euro = RH.euro || function (v) { return v.toFixed(2).replace(".", ",") + " €"; };
  var norm = RH.norm || function (s) { return (s || "").toLowerCase(); };
  var byCat = {}, bySlug = {};
  data.items.forEach(function (it) { (byCat[it.c] = byCat[it.c] || []).push(it); bySlug[it.s] = it; it._n = norm(it.n + " " + it.b); });
  var sel = {};
  var STORE = "radar-config";

  /* --- Prix selon la zone choisie (Europe livré en France / France) --- */
  function offer(it) { return body.getAttribute("data-region") === "fr" ? it.f : it.e; }

  /* --- Puissance --- */
  function estimatedWatts() {
    var c = sel.cpu && bySlug[sel.cpu], g = sel.gpu && bySlug[sel.gpu];
    if (!c && !g) return 0;
    return (c ? c.k.power_w || 0 : 0) + (g ? g.k.power_w || 0 : 0) + 120;
  }
  function neededPsu() { var w = estimatedWatts(); return w ? Math.ceil(w * 1.25) : 0; }

  /* --- Règles de compatibilité : renvoie la liste des raisons d'incompatibilité --- */
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

  /* --- Rendu d'une étape --- */
  function renderStep(li) {
    var cat = li.getAttribute("data-cat"), it = sel[cat] && bySlug[sel[cat]];
    var choice = li.querySelector(".cfg-choice"), price = li.querySelector(".cfg-price"),
        open = li.querySelector(".cfg-open"), rm = li.querySelector(".cfg-remove");
    li.classList.toggle("is-set", !!it);
    if (it) {
      choice.classList.remove("muted"); choice.innerHTML = "";
      var a = document.createElement("a"); a.href = ROOT + it.u; a.textContent = it.n; choice.appendChild(a);
      var o = offer(it);
      price.innerHTML = o ? euro(o[0]) + "<small>" + o[1] + " · " + o[2] + "</small>" : "<small>Indisponible dans cette zone</small>";
      open.querySelector("span").textContent = "Changer"; rm.hidden = false;
    } else {
      choice.classList.add("muted"); choice.textContent = "Aucun composant choisi"; price.innerHTML = "";
      open.querySelector("span").textContent = "Choisir"; rm.hidden = true;
    }
  }

  function renderPicker(li) {
    var cat = li.getAttribute("data-cat"), list = li.querySelector(".cfg-list"),
        qv = norm(li.querySelector(".cfg-q").value), sortBy = li.querySelector(".cfg-sort").value;
    var all = (byCat[cat] || []).filter(function (it) { return !qv || it._n.indexOf(qv) >= 0; });
    var ok = all.filter(function (it) { return !problems(it, sel).length && offer(it); });
    var hidden = all.length - ok.length;
    ok.sort(sortBy === "name" ? function (a, b) { return a.n.localeCompare(b.n); } : function (a, b) { return offer(a)[0] - offer(b)[0]; });
    li.querySelector(".cfg-hidden").textContent = ok.length + " compatible" + (ok.length > 1 ? "s" : "") +
      (hidden ? " · " + hidden + " masqué" + (hidden > 1 ? "s" : "") + " (incompatibles ou indisponibles)" : "");
    list.innerHTML = "";
    ok.forEach(function (it) {
      var o = offer(it), b = document.createElement("button"); b.type = "button"; b.className = "cfg-item";
      var img = document.createElement("img"); img.src = ROOT + it.i; img.alt = ""; img.loading = "lazy";
      var mid = document.createElement("span");
      var nm = document.createElement("span"); nm.className = "cfg-item-name"; nm.textContent = it.n;
      var sub = document.createElement("span"); sub.className = "cfg-item-sub"; sub.textContent = spec(it);
      mid.appendChild(nm); mid.appendChild(sub);
      var pr = document.createElement("span"); pr.className = "cfg-item-price"; pr.innerHTML = euro(o[0]) + "<small>" + o[1] + " · " + o[2] + "</small>";
      b.appendChild(img); b.appendChild(mid); b.appendChild(pr);
      b.addEventListener("click", function () { sel[cat] = it.s; closeAll(); update(); openNext(li); });
      var w = document.createElement("li"); w.appendChild(b); list.appendChild(w);
    });
  }

  function spec(it) {
    var k = it.k;
    switch (it.c) {
      case "cpu": return k.socket + " · " + k.ram.join("/") + " · " + k.power_w + " W max";
      case "motherboard": return k.socket + " · " + k.form + " · " + k.ram;
      case "ram": return k.ram;
      case "gpu": return k.length_mm + " mm · " + k.power_w + " W";
      case "cooler": return k.kind === "air" ? "Ventirad · " + k.height_mm + " mm" : "AIO " + k.radiator_mm + " mm";
      case "case": return k.forms.join(", ") + " · GPU " + k.max_gpu_mm + " mm";
      case "psu": return k.watts + " W";
      default: return it.b;
    }
  }

  var steps = Array.prototype.slice.call(document.querySelectorAll(".cfg-step"));
  function closeAll() { steps.forEach(function (li) { li.querySelector(".cfg-picker").hidden = true; li.classList.remove("is-open"); }); }
  function openStep(li) {
    closeAll(); li.classList.add("is-open"); li.querySelector(".cfg-picker").hidden = false; renderPicker(li);
  }
  function openNext(li) {
    var i = steps.indexOf(li);
    for (var j = i + 1; j < steps.length; j++) {
      if (!sel[steps[j].getAttribute("data-cat")]) { openStep(steps[j]); steps[j].scrollIntoView({ behavior: "smooth", block: "nearest" }); return; }
    }
  }

  /* --- Récapitulatif, contrôles, panier --- */
  function update() {
    steps.forEach(renderStep);
    var total = 0, save = 0, n = 0, missing = 0, checks = [], merchants = {};
    data.steps.forEach(function (st) {
      var it = sel[st[0]] && bySlug[sel[st[0]]]; if (!it) return;
      n++; var o = offer(it);
      if (!o) { missing++; return; }
      total += o[0]; if (it.a && it.a > o[0]) save += it.a - o[0];
      (merchants[o[1]] = merchants[o[1]] || { country: o[2], items: [] }).items.push({ n: it.n, p: o[0], url: o[3] });
      problems(it, sel).forEach(function (p) { checks.push({ ok: false, t: st[1] + " : " + p }); });
    });
    var c = sel.cpu && bySlug[sel.cpu], mb = sel.motherboard && bySlug[sel.motherboard], ram = sel.ram && bySlug[sel.ram],
        box = sel["case"] && bySlug[sel["case"]], gpu = sel.gpu && bySlug[sel.gpu], cool = sel.cooler && bySlug[sel.cooler], psu = sel.psu && bySlug[sel.psu];
    if (c && mb && c.k.socket === mb.k.socket) checks.push({ ok: true, t: "Socket " + c.k.socket + " compatible" });
    if (mb && ram && mb.k.ram === ram.k.ram) checks.push({ ok: true, t: "Mémoire " + ram.k.ram + " compatible" });
    if (mb && box && box.k.forms.indexOf(mb.k.form) >= 0) checks.push({ ok: true, t: "Format " + mb.k.form + " accepté par le boîtier" });
    if (gpu && box && gpu.k.length_mm <= box.k.max_gpu_mm) checks.push({ ok: true, t: "Carte graphique : " + gpu.k.length_mm + " / " + box.k.max_gpu_mm + " mm" });
    if (cool && box && !problems(cool, sel).length) checks.push({ ok: true, t: "Refroidissement adapté au boîtier" });
    if (psu && neededPsu() && psu.k.watts >= neededPsu()) checks.push({ ok: true, t: "Alimentation suffisante (" + psu.k.watts + " W)" });
    if (missing) checks.push({ ok: false, t: missing + " pièce(s) indisponible(s) dans la zone choisie" });

    $("cfg-total").textContent = euro(total);
    $("cfg-save").textContent = save >= 1 ? "Économie de " + euro(save) + " par rapport aux prix moyens 30 jours" : "";
    $("cfg-count").textContent = n + " / " + data.steps.length;
    var w = estimatedWatts(); $("cfg-watts").textContent = w ? w + " W" : "—"; $("cfg-psu").textContent = w ? "≥ " + neededPsu() + " W" : "—";
    var ul = $("cfg-checks"); ul.innerHTML = "";
    checks.forEach(function (ch) {
      var li = document.createElement("li"); li.className = ch.ok ? "ok" : "warn";
      li.innerHTML = ch.ok ? '<svg class="ico" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>'
                           : '<svg class="ico" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M12 3 2 20h20L12 3Z"/><path d="M12 10v4M12 17.5v.01"/></svg>';
      var sp = document.createElement("span"); sp.textContent = ch.t; li.appendChild(sp); ul.appendChild(li);
    });
    $("cfg-buy").disabled = $("cfg-share").disabled = n === 0;
    // Liste d'achat regroupée par marchand
    var bl = $("cfg-buylist"); bl.innerHTML = "";
    var h = document.createElement("h3"); h.textContent = "Acheter au meilleur prix, marchand par marchand"; bl.appendChild(h);
    Object.keys(merchants).sort().forEach(function (m) {
      var g = merchants[m], box2 = document.createElement("div"); box2.className = "cfg-merchant";
      var sub = g.items.reduce(function (s, i) { return s + i.p; }, 0);
      var head = document.createElement("div"); head.className = "cfg-merchant-head";
      head.innerHTML = '<span></span><span class="mono"></span>'; head.firstChild.textContent = m + " (" + g.country + ")"; head.lastChild.textContent = euro(sub);
      box2.appendChild(head);
      g.items.forEach(function (i) {
        var a = document.createElement("a"); a.href = i.url; a.target = "_blank"; a.rel = "nofollow sponsored noopener";
        a.innerHTML = "<span></span><span></span>"; a.firstChild.textContent = i.n; a.lastChild.textContent = euro(i.p);
        box2.appendChild(a);
      });
      bl.appendChild(box2);
    });
    try { RH.store && RH.store(STORE, JSON.stringify(sel)); } catch (e) { /* ignore */ }
  }

  /* --- Événements --- */
  steps.forEach(function (li) {
    li.querySelector(".cfg-open").addEventListener("click", function () { if (li.classList.contains("is-open")) closeAll(); else openStep(li); });
    li.querySelector(".cfg-remove").addEventListener("click", function () { delete sel[li.getAttribute("data-cat")]; closeAll(); update(); });
    li.querySelector(".cfg-q").addEventListener("input", function () { renderPicker(li); });
    li.querySelector(".cfg-sort").addEventListener("change", function () { renderPicker(li); });
  });
  $("cfg-buy").addEventListener("click", function () { var bl = $("cfg-buylist"); bl.hidden = !bl.hidden; if (!bl.hidden) bl.scrollIntoView({ behavior: "smooth", block: "nearest" }); });
  $("cfg-reset").addEventListener("click", function () { sel = {}; closeAll(); $("cfg-buylist").hidden = true; update(); });
  $("cfg-share").addEventListener("click", function () {
    var url = location.origin + location.pathname + "?c=" + data.steps.map(function (st) { return sel[st[0]] || ""; }).join(",");
    var toast = $("cfg-toast");
    var done = function (msg) { toast.textContent = msg; toast.hidden = false; setTimeout(function () { toast.hidden = true; }, 5000); };
    if (navigator.share) { navigator.share({ title: "Ma config PC", url: url }).catch(function () {}); return; }
    if (navigator.clipboard) navigator.clipboard.writeText(url).then(function () { done("Lien copié dans le presse-papiers."); }, function () { done(url); });
    else done(url);
  });
  if (RH.onRegion) RH.onRegion(function () { update(); steps.forEach(function (li) { if (li.classList.contains("is-open")) renderPicker(li); }); });

  /* --- Chargement : config partagée (?c=) ou dernière config --- */
  var shared = new URLSearchParams(location.search).get("c");
  if (shared) {
    shared.split(",").forEach(function (sl, i) { if (sl && bySlug[sl] && data.steps[i] && bySlug[sl].c === data.steps[i][0]) sel[data.steps[i][0]] = sl; });
  } else {
    try { var saved = JSON.parse((RH.store && RH.store(STORE)) || "null"); if (saved) Object.keys(saved).forEach(function (k) { if (bySlug[saved[k]]) sel[k] = saved[k]; }); } catch (e) { /* ignore */ }
  }
  update();
  if (!Object.keys(sel).length) openStep(steps[0]);
})();
