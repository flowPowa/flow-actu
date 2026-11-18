/* Tests de la logique de la page — critères d'acceptation (cahier des charges v8).
   Lancer : node --test tests/   (depuis la racine du dépôt) */
"use strict";
const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const FA = require("../site/logique.js");

const ROOT = path.join(__dirname, "..");
const rd = (p) => JSON.parse(fs.readFileSync(path.join(ROOT, p), "utf8"));
const cfg = {
  categories: rd("config/categories.json").categories,
  medias: rd("config/medias.json").medias,
  motsMasques: rd("config/mots-masques.json").groupes,
  site: rd("config/site.json"),
};
const NOW = Date.parse("2026-11-18T12:00:00Z");
const h = (n) => new Date(NOW - n * 3600e3).toISOString();
let n = 0;
const art = (t, o = {}) => Object.assign({ id: "a" + n++, t, u: "https://www.lemonde.fr/x" + n, m: "le-monde", s: "Le Monde", d: h(1), c: ["a-la-une"], p: null, v: "rss" }, o);
const view = (articles, s) => FA.computeView({ articles }, cfg, s || FA.defaultSettings(cfg), NOW);
const titles = (v) => v.flatMap((b) => b.groups.map((g) => g.main.a.t));
const blockOf = (v, t) => (v.find((b) => b.groups.some((g) => g.main.a.t === t)) || {}).id;

test("CA1 : catégories par défaut", () => {
  const s = FA.defaultSettings(cfg);
  assert.strictEqual(Object.values(s.cats).filter(Boolean).length, 45);
  assert.ok(view([art("Un titre")]).some((b) => b.id === "a-la-une"));
});

test("CA4-CA7 : filtre glauque, variantes, désactivation", () => {
  const A = [art("Un meurtre à Lyon"), art("Paris : un chirurgien soupçonné d'avoir violé des patientes"),
             art("Ouverture d'une enquête pour agression sexuelle"), art("Des vents violents attendus"), art("Une violence verbale")];
  const v = view(A);
  assert.deepStrictEqual(titles(v).sort(), ["Des vents violents attendus", "Une violence verbale"]);
  const s = FA.defaultSettings(cfg); s.mots.glauque = false;
  assert.strictEqual(titles(view(A, s)).length, 5);
});

test("CA8 : spoilers", () => {
  assert.strictEqual(titles(view([art("Dune 3 : la fin expliquée")])).length, 0);
});

test("CA9-CA10 : médias exclus (config) et BFM Business visible", () => {
  const v = view([art("Info CNews", { m: "cnews", u: "https://www.cnews.fr/a" }),
                  art("Info BFM Business", { m: "bfm-business", u: "https://www.bfmtv.com/economie/a", c: ["economie"] })]);
  assert.deepStrictEqual(titles(v), ["Info BFM Business"]);
});

test("CA11 : passer un média neutre en exclu", () => {
  const s = FA.defaultSettings(cfg); s.medias["le-monde"] = "exclu";
  assert.strictEqual(titles(view([art("Un titre")], s)).length, 0);
});

test("CA12 : site ajouté en exclu", () => {
  const s = FA.defaultSettings(cfg); s.ajouts.push({ domaine: "exemple.fr", nom: "Exemple", statut: "exclu" });
  assert.strictEqual(titles(view([art("Un titre", { m: null, u: "https://www.exemple.fr/a", s: "Exemple" })], s)).length, 0);
});

test("CA13 : lien « Ajouter au robot »", () => {
  const u = FA.githubAddUrl(cfg.site, { domaine: "exemple.fr", nom: "Exemple", statut: "favori" });
  assert.ok(u.startsWith("https://github.com/flowPowa/flow-actu/new/main?filename=config%2Fmedias-ajoutes%2Fexemple-fr.json&value="));
  assert.ok(decodeURIComponent(u).includes('"statut": "favori"'));
});

test("CA14 : favori récent en tête de bloc", () => {
  const v = view([art("Récent neutre", { d: h(0.5), c: ["ia"] }),
                  art("Favori un peu plus ancien", { m: "numerama", s: "Numerama", u: "https://www.numerama.com/a", d: h(5), c: ["ia", "tech"] })]);
  assert.strictEqual(v.find((b) => b.id === "ia").groups[0].main.a.t, "Favori un peu plus ancien");
});

test("CA15-CA16 : mots masqués pour les favoris et « Mes mots »", () => {
  assert.strictEqual(titles(view([art("Twist final", { m: "numerama", u: "https://www.numerama.com/b", c: ["tech"] })])).length, 0);
  const s = FA.defaultSettings(cfg); s.mesMots = ["kardashian"];
  assert.strictEqual(titles(view([art("Les Kardashian en vacances")], s)).length, 0);
});

test("CA17-CA19 : payant, incertain, masquer les payants sauf favoris", () => {
  const idx = FA.makeMediaIndex(cfg, FA.defaultSettings(cfg));
  assert.strictEqual(FA.paywallOf(art("x", { p: "payant", m: "le-figaro" }), idx), "payant");
  assert.strictEqual(FA.paywallOf(art("x", { p: null, m: "le-monde" }), idx), "incertain");
  assert.strictEqual(FA.paywallOf(art("x", { p: null, m: "numerama" }), idx), null);
  const s = FA.defaultSettings(cfg); s.masquerPayants = true;
  const v = view([art("Payant Figaro", { m: "le-figaro", p: "payant" }), art("Payant Mediapart", { m: "mediapart", p: "payant" })], s);
  assert.deepStrictEqual(titles(v), ["Payant Mediapart"]);
});

test("CA27 : favori sans catégorie fine → Mes favoris", () => {
  const v = view([art("Un titre Ouest-France", { m: "ouest-france", u: "https://www.ouest-france.fr/a", c: ["a-la-une"] })]);
  assert.strictEqual(blockOf(v, "Un titre Ouest-France"), "mes-favoris");
});

test("CA28-CA30 : une seule fois, ordre des blocs, fine avant large", () => {
  const A = [art("IA et veille", { c: ["ia", "veille-informatique", "tech", "a-la-une"] })];
  assert.strictEqual(blockOf(view(A), "IA et veille"), "ia");
  assert.strictEqual(titles(view(A)).length, 1);
  const s = FA.defaultSettings(cfg); s.cats.ia = false;
  assert.strictEqual(blockOf(view(A, s), "IA et veille"), "veille-informatique");
  s.cats["veille-informatique"] = false;
  assert.strictEqual(blockOf(view(A, s), "IA et veille"), "a-la-une");
});

test("CA33 : ordre des blocs réglable", () => {
  const A = [art("Info nantaise", { c: ["nantes"] }), art("Info IA", { c: ["ia"] })];
  const s = FA.defaultSettings(cfg);
  s.ordre = s.ordre.filter((x) => x !== "nantes").concat(["nantes"]);
  const ids = view(A, s).map((b) => b.id);
  assert.ok(ids.indexOf("nantes") > ids.indexOf("ia"));
});

test("Regroupement : un article principal + « Aussi chez »", () => {
  const A = [art("Budget Sécu Le Monde", { g: "G1", d: h(1), c: ["economie"] }),
             art("Budget Sécu Ouest-France", { g: "G1", m: "ouest-france", u: "https://www.ouest-france.fr/z", s: "Ouest-France", d: h(3), c: ["economie"] }),
             art("Budget Sécu Figaro", { g: "G1", m: "le-figaro", u: "https://www.lefigaro.fr/z", s: "Le Figaro", d: h(2), c: ["economie"] })];
  const v = view(A);
  const b = v.find((x) => x.id === "economie");
  assert.strictEqual(b.groups.length, 1);
  assert.strictEqual(b.groups[0].main.a.s, "Ouest-France"); // favori prioritaire
  assert.strictEqual(b.groups[0].others.length, 2);
});

test("CA38 : recherche parmi les articles visibles", () => {
  const v = view([art("Nantes : le tram arrêté", { c: ["nantes"] }), art("Un meurtre à Nantes", { c: ["nantes"] }), art("Autre sujet")]);
  assert.deepStrictEqual(FA.search(v, "nantes").map((g) => g.main.a.t), ["Nantes : le tram arrêté"]);
});

test("CA40 : export puis import", () => {
  const s = FA.defaultSettings(cfg); s.mesMots = ["test"]; s.medias.lci = "favori"; s.cats.sport = true;
  const back = FA.importSettings(cfg, FA.exportSettings(s));
  assert.deepStrictEqual(back.mesMots, ["test"]);
  assert.strictEqual(back.medias.lci, "favori");
  assert.strictEqual(back.cats.sport, true);
  assert.throws(() => FA.importSettings(cfg, '{"autre":1}'));
});

test("Ancienneté", () => {
  assert.strictEqual(FA.age(h(2), NOW), "il y a 2 h");
  assert.strictEqual(FA.age(h(24 * 21), NOW), "il y a 3 semaines");
});
