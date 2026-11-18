/* Flow Actu — logique de la page (sans affichage), testable avec Node.
   Cahier des charges v8 : § 5.3 (médias), § 5.5 (sélection), § 6 (filtres, payant). */
(function (root) {
  "use strict";

  const SUFFIXES = ["", "s", "e", "es", "ee", "ees", "er", "x"];
  const FAVORIS_BLOC = "mes-favoris";

  function norm(s) {
    return String(s || "").replace(/[’«»]/g, (c) => (c === "’" ? "'" : " ")).toLowerCase()
      .normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/\s+/g, " ").trim();
  }
  const escRe = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

  /* Mots masqués : chaque mot couvre ses variantes (viol → violé, violée, violer, viols…). */
  function buildMatcher(terms) {
    const single = new Set();
    const multi = [];
    for (const raw of terms) {
      const t = norm(raw);
      if (!t) continue;
      const parts = t.split(" ");
      if (parts.length === 1) SUFFIXES.forEach((s) => single.add(t + s));
      else {
        const last = parts.pop();
        multi.push(new RegExp("(?:^|[^\\w])" + parts.map(escRe).join("\\s+") + "\\s+" + escRe(last) +
          "(?:s|e|es|ee|ees|er|x)?(?![\\w])"));
      }
    }
    return function (title) {
      const n = norm(title);
      if (single.size && n.split(/[^a-z0-9-]+/).some((w) => single.has(w) || w.split("-").some((p) => single.has(p)))) return true;
      return multi.some((re) => re.test(n));
    };
  }

  function hostOf(url) {
    try { return new URL(url).hostname.toLowerCase().replace(/^www\./, ""); } catch (e) { return ""; }
  }
  function normalizeDomain(s) {
    s = String(s || "").trim().toLowerCase();
    if (!s) return "";
    if (!/^https?:\/\//.test(s)) s = "https://" + s;
    return hostOf(s);
  }

  /* ------------------------------------------------------------ réglages */
  function defaultSettings(cfg) {
    const cats = {};
    cfg.categories.forEach((c) => { cats[c.id] = !!c.defaut; });
    const mots = {};
    cfg.motsMasques.forEach((g) => { mots[g.id] = g.actif !== false; });
    return { version: 1, cats, ordre: cfg.categories.map((c) => c.id).concat([FAVORIS_BLOC]), mots, mesMots: [],
             medias: {}, ajouts: [], masquerPayants: false, theme: null, lus: [] };
  }

  function mergeSettings(cfg, saved) {
    const d = defaultSettings(cfg);
    if (!saved || typeof saved !== "object") return d;
    const s = Object.assign({}, d, saved);
    s.cats = Object.assign({}, d.cats, saved.cats || {});
    s.mots = Object.assign({}, d.mots, saved.mots || {});
    const known = new Set(d.ordre);
    const ordre = (Array.isArray(saved.ordre) ? saved.ordre : []).filter((x) => known.has(x));
    d.ordre.forEach((x) => { if (!ordre.includes(x)) ordre.push(x); });
    s.ordre = ordre;
    ["mesMots", "ajouts", "lus"].forEach((k) => { if (!Array.isArray(s[k])) s[k] = []; });
    if (typeof s.medias !== "object" || !s.medias) s.medias = {};
    return s;
  }

  /* ------------------------------------------------------------ médias */
  function makeMediaIndex(cfg, settings) {
    const byId = {};
    cfg.medias.forEach((m) => { byId[m.id] = m; });
    const ajoutsByDomain = {};
    settings.ajouts.forEach((a) => { ajoutsByDomain[a.domaine] = a; });
    return { byId, ajoutsByDomain };
  }

  function mediaOf(a, idx) {
    if (a.m && idx.byId[a.m]) return { kind: "config", media: idx.byId[a.m] };
    const h = hostOf(a.u);
    for (const d in idx.ajoutsByDomain) {
      if (h === d || h.endsWith("." + d)) return { kind: "ajout", media: idx.ajoutsByDomain[d] };
    }
    return null;
  }

  function statutOf(a, idx, settings) {
    const mm = mediaOf(a, idx);
    if (!mm) return "neutre";
    if (mm.kind === "ajout") return mm.media.statut;
    return settings.medias[mm.media.id] || mm.media.statut || "neutre";
  }

  /* 'payant' (🔒), 'incertain' (🔓?) ou null */
  function paywallOf(a, idx) {
    if (a.p === "payant") return "payant";
    if (a.p === "compteur") return "incertain";
    if (a.p === "gratuit") return null;
    const mm = mediaOf(a, idx);
    const label = mm && mm.kind === "config" ? mm.media.etiquette : null;
    if (label === "payant") return "payant";
    if (label === "mixte") return "incertain";
    return null;
  }

  /* ------------------------------------------------------------ sélection (§ 5.5) */
  function computeView(data, cfg, settings, now) {
    now = now || Date.now();
    const idx = makeMediaIndex(cfg, settings);
    const catById = {};
    cfg.categories.forEach((c) => { catById[c.id] = c; });
    const order = {};
    settings.ordre.forEach((id, i) => { order[id] = i; });
    const activeTerms = [];
    cfg.motsMasques.forEach((g) => { if (settings.mots[g.id]) activeTerms.push(...g.mots); });
    activeTerms.push(...settings.mesMots);
    const masked = buildMatcher(activeTerms);

    function blockOf(a, fav) {
      const checked = (a.c || []).filter((c) => settings.cats[c] && catById[c]);
      const fines = checked.filter((c) => !catById[c].large).sort((x, y) => order[x] - order[y]);
      if (fines.length) return fines[0];
      if (fav) return FAVORIS_BLOC;
      const larges = checked.filter((c) => catById[c].large).sort((x, y) => order[x] - order[y]);
      return larges[0] || null;
    }

    // 1-4 : filtres article par article
    const visible = [];
    for (const a of data.articles || []) {
      const statut = statutOf(a, idx, settings);
      if (statut === "exclu") continue;
      if (masked(a.t)) continue;
      const fav = statut === "favori";
      const pay = paywallOf(a, idx);
      if (settings.masquerPayants && pay === "payant" && !fav) continue;
      const block = blockOf(a, fav);
      if (!block) continue;
      visible.push({ a, fav, pay, block, time: Date.parse(a.d) || 0 });
    }

    // regroupement par sujet, puis 5 : une seule fois
    const groups = {};
    for (const v of visible) (groups[v.a.g || v.a.id] = groups[v.a.g || v.a.id] || []).push(v);
    const blocks = {};
    for (const key in groups) {
      const members = groups[key].sort((x, y) => y.time - x.time);
      const favs = members.filter((m) => m.fav);
      const main = favs[0] || members[0];
      const others = members.filter((m) => m !== main);
      const g = { key, main, others, time: main.time, favRecent: main.fav && now - main.time < 24 * 3600e3 };
      (blocks[main.block] = blocks[main.block] || []).push(g);
    }
    const out = [];
    for (const id of settings.ordre) {
      if (!blocks[id]) continue;
      blocks[id].sort((x, y) => (y.favRecent - x.favRecent) || (y.time - x.time));
      out.push({ id, nom: id === FAVORIS_BLOC ? "Mes favoris" : catById[id].nom, groups: blocks[id] });
    }
    return out;
  }

  function search(view, q) {
    const n = norm(q);
    if (!n) return [];
    const res = [];
    for (const b of view) for (const g of b.groups) {
      if ([g.main, ...g.others].some((m) => norm(m.a.t + " " + m.a.s).includes(n))) res.push(Object.assign({ bloc: b.nom }, g));
    }
    return res.sort((x, y) => y.time - x.time);
  }

  /* ------------------------------------------------------------ divers */
  function age(iso, now) {
    const min = Math.round(((now || Date.now()) - Date.parse(iso)) / 60000);
    if (!isFinite(min)) return "";
    if (min < 1) return "à l'instant";
    if (min < 60) return `il y a ${min} min`;
    const h = Math.round(min / 60);
    if (h < 24) return `il y a ${h} h`;
    const d = Math.round(h / 24);
    if (d === 1) return "hier";
    if (d < 14) return `il y a ${d} jours`;
    if (d < 60) return `il y a ${Math.round(d / 7)} semaines`;
    return `il y a ${Math.round(d / 30)} mois`;
  }

  function githubAddUrl(site, ajout) {
    const slug = ajout.domaine.replace(/[^a-z0-9]+/g, "-");
    const value = JSON.stringify({ nom: ajout.nom || ajout.domaine, site: "https://" + ajout.domaine, statut: ajout.statut }, null, 1);
    return `https://github.com/${site.depot}/new/${site.branche}?filename=${encodeURIComponent("config/medias-ajoutes/" + slug + ".json")}&value=${encodeURIComponent(value)}`;
  }

  function exportSettings(settings) {
    return JSON.stringify({ application: "flow-actu", exporte: new Date().toISOString(), reglages: settings }, null, 1);
  }
  function importSettings(cfg, text) {
    const o = JSON.parse(text);
    if (!o || o.application !== "flow-actu" || typeof o.reglages !== "object") throw new Error("Ce fichier n'est pas un export Flow Actu.");
    return mergeSettings(cfg, o.reglages);
  }

  const api = { norm, buildMatcher, hostOf, normalizeDomain, defaultSettings, mergeSettings, makeMediaIndex, mediaOf, statutOf,
                paywallOf, computeView, search, age, githubAddUrl, exportSettings, importSettings, FAVORIS_BLOC };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.FA = api;
})(this);
