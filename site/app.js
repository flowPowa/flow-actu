/* Flow Actu — affichage et réglages. La logique (filtres, sélection) est dans logique.js. */
(function () {
  "use strict";
  const $ = (s) => document.querySelector(s);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const KEY = "flowactu-reglages";
  const store = {
    get() { try { return JSON.parse(localStorage.getItem(KEY)); } catch (e) { return null; } },
    set(v) { try { localStorage.setItem(KEY, JSON.stringify(v)); } catch (e) { /* stockage indisponible */ } },
  };

  let CFG = null, DATA = null, S = null, VIEW = [], current = "pourvous", catFilter = "", mediaFilter = "", flash = "";
  const POS_KEY = "flowactu-position";
  const fromHash = () => decodeURIComponent(location.hash.slice(1)) || "pourvous";
  function go(view) {
    if (fromHash() === view) { current = view; render(); scrollTo({ top: 0 }); }
    else location.hash = view; // le changement d'adresse déclenche l'affichage (et entre dans l'historique)
  }
  function savePos() { try { sessionStorage.setItem(POS_KEY, JSON.stringify({ v: current, y: Math.round(scrollY) })); } catch (e) {} }
  function restorePos() {
    let p = null; try { p = JSON.parse(sessionStorage.getItem(POS_KEY)); } catch (e) {}
    if (p && p.v === current && p.y > 0) requestAnimationFrame(() => scrollTo(0, p.y));
  }

  /* ---------------------------------------------------------------- utilitaires */
  function save() { store.set(S); }
  function catById(id) { return CFG.categories.find((c) => c.id === id); }
  function lusSet() { return new Set(S.lus); }
  function wmo(c) {
    if (c === 0) return ["☀️", "Ensoleillé"]; if (c <= 2) return ["🌤️", "Éclaircies"]; if (c === 3) return ["☁️", "Couvert"];
    if (c <= 48) return ["🌫️", "Brouillard"]; if (c <= 57) return ["🌦️", "Bruine"]; if (c <= 67) return ["🌧️", "Pluie"];
    if (c <= 77) return ["🌨️", "Neige"]; if (c <= 82) return ["🌧️", "Averses"]; if (c <= 86) return ["🌨️", "Averses de neige"];
    return ["⛈️", "Orage"];
  }
  function faviconHost(a) {
    const mm = FA.mediaOf(a, FA.makeMediaIndex(CFG, S));
    if (mm && mm.media.domaines) return mm.media.domaines[0].split("/")[0];
    if (mm && mm.media.domaine) return mm.media.domaine;
    return FA.hostOf(a.u);
  }
  function applyTheme() {
    const t = S.theme || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    document.documentElement.dataset.theme = t;
  }

  /* ---------------------------------------------------------------- articles */
  function articleHTML(g, lead, bloc) {
    const m = g.main, a = m.a, read = lusSet().has(a.id);
    const host = faviconHost(a);
    const fav = host ? `<img src="https://www.google.com/s2/favicons?domain=${esc(host)}&sz=32" alt="" loading="lazy" onerror="this.remove()">` : "";
    const pay = m.pay === "payant" ? `<span class="pay" title="Article réservé aux abonnés">🔒 Abonnés</span>`
      : m.pay === "incertain" ? `<span class="pay" title="Média mixte : cet article est peut-être réservé aux abonnés">🔓? Peut-être payant</span>` : "";
    const also = g.others.length ? `<div class="also">Aussi chez : ${g.others.map((o) =>
      `<a href="${esc(o.a.u)}" target="_blank" rel="noopener" data-read="${esc(o.a.id)}">${esc(o.a.s)}${o.pay === "payant" ? " 🔒" : ""}</a>`).join(", ")}</div>` : "";
    return `<article class="article${lead ? " lead" : ""}${read ? " read" : ""}">
      <div class="src">${fav}${esc(a.s)}${m.fav ? ' <span class="star" title="Favori">⭐</span>' : ""}</div>
      <a class="t" href="${esc(a.u)}" target="_blank" rel="noopener" data-read="${esc(a.id)}"><h3>${esc(a.t)}</h3></a>
      <div class="meta"><span>${FA.age(a.d)}</span>${pay}${bloc ? `<span class="badge">${esc(bloc)}</span>` : ""}</div>${also}
    </article>`;
  }

  function blockHTML(b, limit) {
    const gs = limit ? b.groups.slice(0, limit) : b.groups;
    const more = limit && b.groups.length > limit ? `<button class="link" data-go="${esc(b.id)}">Tout voir (${b.groups.length})</button>` : "";
    return `<div class="block"><div class="block-head"><h2>${limit ? `<button data-go="${esc(b.id)}">${esc(b.nom)} ›</button>` : esc(b.nom)}</h2>${more}</div>
      ${gs.map((g, i) => articleHTML(g, i === 0)).join("")}</div>`;
  }

  /* ---------------------------------------------------------------- écrans */
  function greeting() {
    const h = new Date().getHours();
    const hello = h < 6 ? "Bonne nuit" : h < 18 ? "Bonjour" : "Bonsoir";
    const d = new Date().toLocaleDateString("fr-FR", { weekday: "long", day: "numeric", month: "long" });
    return `<div class="greeting"><h1>${hello} ${esc(CFG.site.prenom)}</h1><p>${d.charAt(0).toUpperCase() + d.slice(1)} · votre sélection personnalisée</p></div>`;
  }

  function renderContent() {
    const q = $("#q").value.trim();
    let html;
    if (current === "reglages") html = settingsHTML();
    else if (q) {
      const res = FA.search(VIEW, q);
      html = `<div class="block"><div class="block-head"><h2>Résultats pour « ${esc(q)} »</h2></div>
        ${res.length ? res.map((g) => articleHTML(g, false, g.bloc)).join("") : '<p class="empty">Aucun article ne correspond.</p>'}</div>`;
    } else if (current === "pourvous") {
      html = greeting() + (VIEW.length ? VIEW.map((b) => blockHTML(b, 4)).join("")
        : '<p class="empty">Aucun article à afficher. Cochez des catégories dans les réglages ⚙️.</p>');
    } else {
      const b = VIEW.find((x) => x.id === current);
      html = b ? blockHTML(b, 0) : '<p class="empty">Aucun article dans cette rubrique pour le moment.</p>';
    }
    $("#content").innerHTML = html;
  }

  function renderTabs() {
    const tabs = [{ id: "pourvous", nom: "Pour vous" }].concat(VIEW.map((b) => ({ id: b.id, nom: b.nom })));
    $("#tabs").innerHTML = tabs.map((t) => `<button data-go="${esc(t.id)}" class="${t.id === current ? "active" : ""}">${esc(t.nom)}</button>`).join("");
    $("#reglages").classList.toggle("on", current === "reglages");
  }

  function renderSide() {
    let html = "";
    const w = DATA.meteo;
    if (w && w.actuel) {
      const [ico, desc] = wmo(w.actuel.weather_code);
      const days = (w.jours && w.jours.time || []).slice(1, 4).map((d, i) => {
        const [di] = wmo(w.jours.weather_code[i + 1]);
        return `<div>${new Date(d).toLocaleDateString("fr-FR", { weekday: "short" })}<span class="ico">${di}</span>${Math.round(w.jours.temperature_2m_max[i + 1])}° <span style="color:var(--muted)">${Math.round(w.jours.temperature_2m_min[i + 1])}°</span></div>`;
      }).join("");
      html += `<div class="block"><h2>Météo · ${esc(w.ville)}</h2><div class="w-now"><span class="ico">${ico}</span><div>
        <div class="temp">${Math.round(w.actuel.temperature_2m)}°C</div><div class="desc">${desc} · vent ${Math.round(w.actuel.wind_speed_10m)} km/h</div></div></div>
        <div class="forecast">${days}</div></div>`;
    }
    html += `<div class="block"><h2>Mes rubriques</h2><div class="chips">${VIEW.map((b) => `<button class="chip" data-go="${esc(b.id)}">${esc(b.nom)}</button>`).join("")}</div></div>`;
    const total = VIEW.reduce((n, b) => n + b.groups.length, 0);
    html += `<div class="block foot">Mis à jour ${FA.age(DATA.genere)} · ${total} sujets affichés<br>
      Sources : flux RSS des médias et Google Actualités · Météo : Open-Meteo</div>`;
    $("#side").innerHTML = html;
  }

  function render() {
    VIEW = FA.computeView(DATA, CFG, S);
    if (current !== "pourvous" && current !== "reglages" && !VIEW.some((b) => b.id === current)) { current = "pourvous"; history.replaceState(null, "", "#pourvous"); }
    renderTabs(); renderContent(); renderSide();
  }

  /* ---------------------------------------------------------------- réglages */
  function settingsHTML() {
    const f = FA.norm(catFilter);
    const fams = CFG.familles.map((fam) => {
      const cats = CFG.categories.filter((c) => c.famille === fam.id && (!f || FA.norm(c.nom).includes(f)));
      if (!cats.length) return "";
      return `<div class="fam"><div class="fam-head"><strong>${esc(fam.nom)}</strong>
        <button class="link" data-act="fam-on" data-fam="${fam.id}">Tout cocher</button>
        <button class="link" data-act="fam-off" data-fam="${fam.id}">Tout décocher</button></div>
        <div class="grid">${cats.map((c) => `<label class="check"><input type="checkbox" data-act="cat" data-id="${c.id}"${S.cats[c.id] ? " checked" : ""}>
          ${esc(c.nom)}${c.large ? ' <span class="large-tag">large</span>' : ""}</label>`).join("")}</div></div>`;
    }).join("");

    const ordre = S.ordre.filter((id) => id === FA.FAVORIS_BLOC || S.cats[id]);
    const order = ordre.map((id, i) => `<li><span>${esc(id === FA.FAVORIS_BLOC ? "Mes favoris" : catById(id).nom)}</span>
      <button class="btn" data-act="up" data-id="${id}" ${i === 0 ? "disabled" : ""} aria-label="Monter">↑</button>
      <button class="btn" data-act="down" data-id="${id}" ${i === ordre.length - 1 ? "disabled" : ""} aria-label="Descendre">↓</button></li>`).join("");

    const groups = CFG.motsMasques.map((g) => `<div class="fam"><label class="check"><input type="checkbox" data-act="mots" data-id="${g.id}"${S.mots[g.id] ? " checked" : ""}>
      <strong>${esc(g.nom)}</strong>&nbsp;— ${esc(g.description)}</label>
      <details><summary>Voir les ${g.mots.length} mots</summary><div class="wordlist">${g.mots.map(esc).join(", ")}</div></details></div>`).join("");
    const mesMots = S.mesMots.map((w, i) => `<span class="tag">${esc(w)}<button data-act="mot-del" data-i="${i}" aria-label="Retirer">✕</button></span>`).join("");

    const mf = FA.norm(mediaFilter);
    const opt = (v, cur) => ["favori", "neutre", "exclu"].map((s) => `<option value="${s}"${s === v ? " selected" : ""}>${{ favori: "⭐ Favori", neutre: "Neutre", exclu: "⛔ Exclu" }[s]}</option>`).join("");
    const medias = CFG.medias.filter((m) => !mf || FA.norm(m.nom).includes(mf)).map((m) => {
      const st = S.medias[m.id] || m.statut;
      return `<li><span>${esc(m.nom)}${m.etiquette ? ` <small style="color:var(--muted)">· ${esc(m.etiquette)}</small>` : ""}</span>
        <select class="field" data-act="media" data-id="${m.id}">${opt(st)}</select></li>`;
    }).join("");
    const ajouts = S.ajouts.map((a, i) => `<li><span>${esc(a.nom || a.domaine)} <small style="color:var(--muted)">· ${esc(a.domaine)}</small></span>
      <select class="field" data-act="ajout-statut" data-i="${i}">${opt(a.statut)}</select>
      ${a.statut !== "exclu" ? `<a class="btn" href="${esc(FA.githubAddUrl(CFG.site, a))}" target="_blank" rel="noopener">Ajouter au robot</a>` : ""}
      <button class="btn" data-act="ajout-del" data-i="${i}" aria-label="Retirer">✕</button></li>`).join("");

    return `<div class="settings">
      <div class="block"><h2>Catégories</h2><p class="hint">Cochez ce qui vous intéresse. Les changements s'appliquent tout de suite.</p>
        <input class="field" style="width:100%" type="search" placeholder="Chercher une catégorie…" data-act="cat-filter" value="${esc(catFilter)}">${fams}</div>
      <div class="block"><h2>Ordre des blocs</h2><p class="hint">Ordre d'affichage dans « Pour vous ». Il décide aussi où va un article qui correspond à plusieurs catégories (la première l'emporte).</p>
        <ul class="order">${order}</ul></div>
      <div class="block"><h2>Mots masqués</h2><p class="hint">Un article dont le titre contient un de ces mots est masqué partout. Chaque mot couvre ses variantes (« viol » couvre aussi « violé », « violée »…).</p>
        ${groups}<div class="fam"><strong>Mes mots</strong><div class="row">${mesMots || '<span class="hint">Aucun pour le moment.</span>'}</div>
        <form class="row" data-form="mot"><input class="field" name="mot" placeholder="Ajouter un mot ou une expression" required><button class="btn primary">Ajouter</button></form></div></div>
      <div class="block"><h2>Médias</h2><p class="hint">⭐ Favori : étoile et en tête des blocs (articles de moins de 24 h). ⛔ Exclu : n'apparaît nulle part.</p>
        <input class="field" style="width:100%" type="search" placeholder="Chercher un média…" data-act="media-filter" value="${esc(mediaFilter)}">
        <ul class="medias">${medias}</ul>
        <h2 style="margin-top:18px">Ajouter un site</h2><p class="hint">L'exclusion s'applique tout de suite. Pour qu'un favori ou un média neutre soit aussi lu par le robot, cliquez ensuite sur « Ajouter au robot » puis sur « Commit changes » sur GitHub.</p>
        <form class="row" data-form="ajout"><input class="field" name="domaine" placeholder="exemple.fr" required>
          <input class="field" name="nom" placeholder="Nom (facultatif)"><select class="field" name="statut">${opt("favori")}</select>
          <button class="btn primary">Ajouter</button></form>
        ${ajouts ? `<ul class="medias">${ajouts}</ul>` : ""}</div>
      <div class="block"><h2>Articles payants</h2>
        <label class="check"><input type="checkbox" data-act="payants"${S.masquerPayants ? " checked" : ""}> Masquer les articles réservés aux abonnés (🔒), sauf ceux de mes favoris</label>
        <p class="hint">🔓? = média qui publie des articles gratuits et payants, sans indication pour celui-ci : il reste affiché.</p></div>
      <div class="block"><h2>Mes données</h2><p class="hint">Vos réglages restent dans ce navigateur, jamais sur GitHub. Pour les copier sur un autre appareil : exportez ici, puis importez là-bas.</p>
        <div class="row"><button class="btn" data-act="export">Exporter mes réglages</button>
          <label class="btn">Importer des réglages<input type="file" accept="application/json,.json" data-act="import" hidden></label>
          <button class="btn" data-act="lus-reset">Réinitialiser les articles lus</button></div>
        ${flash ? `<p class="${flash.startsWith("✓") ? "ok-msg" : "ko-msg"}">${esc(flash)}</p>` : ""}</div>
      <p class="hint" style="text-align:center"><button class="link" data-go="pourvous">← Retour à mes actus</button></p>
    </div>`;
  }

  function moveOrder(id, dir) {
    const vis = S.ordre.filter((x) => x === FA.FAVORIS_BLOC || S.cats[x]);
    const i = vis.indexOf(id), j = i + dir;
    if (i < 0 || j < 0 || j >= vis.length) return;
    const a = S.ordre.indexOf(vis[i]), b = S.ordre.indexOf(vis[j]);
    [S.ordre[a], S.ordre[b]] = [S.ordre[b], S.ordre[a]];
  }

  /* ---------------------------------------------------------------- évènements */
  document.addEventListener("click", (e) => {
    const goEl = e.target.closest("[data-go]");
    if (goEl) { e.preventDefault(); $("#q").value = ""; flash = ""; go(goEl.dataset.go); return; }
    const rd = e.target.closest("[data-read]");
    if (rd) {
      savePos();
      if (!S.lus.includes(rd.dataset.read)) { S.lus.push(rd.dataset.read); S.lus = S.lus.slice(-3000); save(); }
      const art = rd.closest(".article"); if (art && rd.classList.contains("t")) art.classList.add("read");
      return;
    }
    const act = e.target.closest("[data-act]");
    if (!act || act.tagName === "INPUT" || act.tagName === "SELECT") return;
    const d = act.dataset;
    if (d.act === "fam-on" || d.act === "fam-off") CFG.categories.filter((c) => c.famille === d.fam).forEach((c) => { S.cats[c.id] = d.act === "fam-on"; });
    else if (d.act === "up") moveOrder(d.id, -1);
    else if (d.act === "down") moveOrder(d.id, 1);
    else if (d.act === "mot-del") S.mesMots.splice(+d.i, 1);
    else if (d.act === "ajout-del") S.ajouts.splice(+d.i, 1);
    else if (d.act === "lus-reset") { S.lus = []; flash = "✓ Articles lus réinitialisés."; }
    else if (d.act === "export") {
      const blob = new Blob([FA.exportSettings(S)], { type: "application/json" });
      const link = Object.assign(document.createElement("a"), { href: URL.createObjectURL(blob), download: "flow-actu-reglages.json" });
      document.body.appendChild(link); link.click(); link.remove();
      flash = "✓ Fichier « flow-actu-reglages.json » téléchargé.";
    } else return;
    save(); render();
  });

  document.addEventListener("change", (e) => {
    const d = e.target.dataset;
    if (!d || !d.act) return;
    if (d.act === "cat") S.cats[d.id] = e.target.checked;
    else if (d.act === "mots") S.mots[d.id] = e.target.checked;
    else if (d.act === "media") S.medias[d.id] = e.target.value;
    else if (d.act === "ajout-statut") S.ajouts[+d.i].statut = e.target.value;
    else if (d.act === "payants") S.masquerPayants = e.target.checked;
    else if (d.act === "import") {
      const file = e.target.files[0]; if (!file) return;
      file.text().then((txt) => {
        try { S = FA.importSettings(CFG, txt); save(); applyTheme(); flash = "✓ Réglages importés."; }
        catch (err) { flash = "✗ " + err.message; }
        render();
      });
      return;
    } else return;
    save(); render();
  });

  document.addEventListener("input", (e) => {
    const d = e.target.dataset;
    if (d && (d.act === "cat-filter" || d.act === "media-filter")) {
      if (d.act === "cat-filter") catFilter = e.target.value; else mediaFilter = e.target.value;
      const pos = e.target.selectionStart; renderContent();
      const el = document.querySelector(`[data-act="${d.act}"]`); el.focus(); el.setSelectionRange(pos, pos);
    }
  });

  document.addEventListener("submit", (e) => {
    const form = e.target.closest("[data-form]");
    if (!form) return;
    e.preventDefault();
    const fd = new FormData(form);
    if (form.dataset.form === "mot") {
      const w = String(fd.get("mot")).trim();
      if (w && !S.mesMots.includes(w)) S.mesMots.push(w);
    } else {
      const dom = FA.normalizeDomain(fd.get("domaine"));
      if (!dom || !dom.includes(".")) { flash = "✗ Adresse de site invalide."; render(); return; }
      S.ajouts = S.ajouts.filter((a) => a.domaine !== dom);
      S.ajouts.push({ domaine: dom, nom: String(fd.get("nom")).trim() || dom, statut: fd.get("statut") });
      flash = "";
    }
    save(); render();
  });

  $("#q").addEventListener("input", renderContent);
  $("#theme").addEventListener("click", () => {
    S.theme = document.documentElement.dataset.theme === "dark" ? "light" : "dark"; save(); applyTheme();
  });
  $("#reglages").addEventListener("click", () => { flash = ""; if (current === "reglages") history.back(); else go("reglages"); });
  window.addEventListener("hashchange", () => { current = fromHash(); flash = ""; if (DATA) { render(); scrollTo({ top: 0 }); } });
  window.addEventListener("pagehide", savePos);
  document.addEventListener("visibilitychange", () => { if (document.visibilityState === "hidden") savePos(); });
  if ("scrollRestoration" in history) history.scrollRestoration = "manual";

  /* ---------------------------------------------------------------- chargement */
  const get = (p) => fetch(p + "?t=" + Date.now()).then((r) => { if (!r.ok) throw new Error(p + " : " + r.status); return r.json(); });
  Promise.all([get("config/categories.json"), get("config/medias.json"), get("config/mots-masques.json"), get("config/site.json"), get("data/news.json")])
    .then(([cats, medias, mots, site, data]) => {
      CFG = { familles: cats.familles, categories: cats.categories, medias: medias.medias, motsMasques: mots.groupes, site };
      DATA = data;
      S = FA.mergeSettings(CFG, store.get());
      document.title = site.titre;
      current = fromHash(); applyTheme(); render(); restorePos();
      setInterval(() => { if (current !== "reglages" && !$("#q").value) renderContent(); }, 60000);
    })
    .catch((err) => {
      $("#content").innerHTML = `<div class="error">Impossible de charger les données (${esc(err.message)}).<br>
        Si vous avez ouvert le fichier en double-cliquant dessus, c'est normal : la page doit être servie par GitHub Pages.</div>`;
    });
})();
