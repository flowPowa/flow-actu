#!/usr/bin/env python3
"""Flow Actu — essai technique (prototype jetable, cahier des charges § 6.3 et § 5).

Mesure, sur des articles réels :
  A. si chaque média (favoris + neutres) a un flux RSS trouvable automatiquement ;
  B. combien d'articles de ces flux tombent dans chaque catégorie cochée par défaut
     (classement par mots-clés) → quelles catégories ont besoin de Google ;
  C. si on remonte d'un lien Google Actualités jusqu'à la vraie page de l'article ;
  D. si le statut « payant / gratuit » est détectable (mention isAccessibleForFree) ;
  E. si des sites bloquent la visite ;
  F. si BFMTV et BFM Business partagent la même adresse.

Bibliothèque standard Python uniquement. Le rapport s'affiche dans le résumé
du workflow GitHub (ou dans le terminal si lancé à la main).
"""
import base64
import json
import os
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from html import unescape

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0 Safari/537.36")
PAUSE = 1.0  # secondes entre deux visites, par politesse

# Médias favoris (F) et neutres (N) : (nom, page d'accueil, statut)
MEDIAS = [
    ("Ouest-France", "https://www.ouest-france.fr", "F"),
    ("Mediapart", "https://www.mediapart.fr", "F"),
    ("Courrier international", "https://www.courrierinternational.com", "F"),
    ("Arte", "https://www.arte.tv/fr/", "F"),
    ("Les Echos", "https://www.lesechos.fr", "F"),
    ("Numerama", "https://www.numerama.com", "F"),
    ("Frandroid", "https://www.frandroid.com", "F"),
    ("Korben", "https://korben.info", "F"),
    ("Écran Large", "https://www.ecranlarge.com", "F"),
    ("developpez.com", "https://www.developpez.com", "F"),
    ("Le Monde", "https://www.lemonde.fr", "N"),
    ("Le Figaro", "https://www.lefigaro.fr", "N"),
    ("Libération", "https://www.liberation.fr", "N"),
    ("Le Parisien", "https://www.leparisien.fr", "N"),
    ("franceinfo", "https://www.francetvinfo.fr", "N"),
    ("20 Minutes", "https://www.20minutes.fr", "N"),
    ("L'Humanité", "https://www.humanite.fr", "N"),
    ("Le Point", "https://www.lepoint.fr", "N"),
    ("L'Express", "https://www.lexpress.fr", "N"),
    ("L'Obs", "https://www.nouvelobs.com", "N"),
    ("Marianne", "https://www.marianne.net", "N"),
    ("HuffPost", "https://www.huffingtonpost.fr", "N"),
    ("LCI", "https://www.tf1info.fr", "N"),
    ("France 24", "https://www.france24.com/fr/", "N"),
    ("Europe 1", "https://www.europe1.fr", "N"),
    ("RTL", "https://www.rtl.fr", "N"),
    ("France Inter", "https://www.radiofrance.fr/franceinter", "N"),
    ("RFI", "https://www.rfi.fr/fr/", "N"),
    ("La Tribune", "https://www.latribune.fr", "N"),
    ("Capital", "https://www.capital.fr", "N"),
    ("Challenges", "https://www.challenges.fr", "N"),
    ("Boursorama", "https://www.boursorama.com", "N"),
    ("Investir", "https://investir.lesechos.fr", "N"),
    ("BFM Business", "https://www.bfmtv.com/economie/", "N"),
    ("Presse Océan", "https://www.presseocean.fr", "N"),
    ("France 3 Pays de la Loire", "https://france3-regions.francetvinfo.fr/pays-de-la-loire", "N"),
    ("Actu.fr Pays de la Loire", "https://actu.fr/pays-de-la-loire", "N"),
    ("ici Loire Océan", "https://www.francebleu.fr/loire-ocean", "N"),
    ("Le Télégramme", "https://www.letelegramme.fr", "N"),
    ("Next", "https://next.ink", "N"),
    ("01net", "https://www.01net.com", "N"),
    ("Clubic", "https://www.clubic.com", "N"),
    ("ZDNet", "https://www.zdnet.fr", "N"),
    ("Le Monde Informatique", "https://www.lemondeinformatique.fr", "N"),
    ("Journal du Geek", "https://www.journaldugeek.com", "N"),
    ("Futura", "https://www.futura-sciences.com", "N"),
    ("Sciences et Avenir", "https://www.sciencesetavenir.fr", "N"),
    ("Ciel et Espace", "https://www.cieletespace.fr", "N"),
    ("Pour la Science", "https://www.pourlascience.fr", "N"),
    ("The Conversation", "https://theconversation.com/fr", "N"),
    ("Gamekult", "https://www.gamekult.com", "N"),
    ("Jeuxvideo.com", "https://www.jeuxvideo.com", "N"),
    ("Gameblog", "https://www.gameblog.fr", "N"),
    ("ActuGaming", "https://www.actugaming.net", "N"),
    ("Millenium", "https://www.millenium.org", "N"),
    ("AlloCiné", "https://www.allocine.fr", "N"),
    ("Première", "https://www.premiere.fr", "N"),
    ("Konbini", "https://www.konbini.com", "N"),
    ("Télérama", "https://www.telerama.fr", "N"),
    ("Les Inrocks", "https://www.lesinrocks.com", "N"),
    ("Manga-News", "https://www.manga-news.com", "N"),
    ("Nautiljon", "https://www.nautiljon.com", "N"),
]

# Médias testés via Google Actualités (décodage des liens + statut payant)
GOOGLE_SITES = [
    ("Le Monde", "lemonde.fr"), ("Le Figaro", "lefigaro.fr"),
    ("Libération", "liberation.fr"), ("Le Parisien", "leparisien.fr"),
    ("franceinfo", "francetvinfo.fr"), ("20 Minutes", "20minutes.fr"),
    ("Le Point", "lepoint.fr"), ("L'Express", "lexpress.fr"),
    ("Presse Océan", "presseocean.fr"), ("Gamekult", "gamekult.com"),
]

# Mots-clés des catégories cochées par défaut (prototype, à affiner).
# « a+b » = les deux mots doivent être présents. Comparaison sans accents ni majuscules.
CATEGORIES = {
    "International": ["international", "ukraine", "russie", "chine", "etats-unis", "israel", "gaza", "onu", "otan", "diplomatie"],
    "Europe": ["europe", "europeen", "europeenne", "union europeenne", "bruxelles", "commission europeenne"],
    "Politique France": ["gouvernement", "assemblee nationale", "senat", "depute", "ministre", "elysee", "election", "municipales", "presidentielle"],
    "Économie": ["economie", "inflation", "croissance", "chomage", "pib", "budget", "dette publique", "entreprises"],
    "Société": ["societe", "logement", "pauvrete", "immigration", "greve", "manifestation", "laicite"],
    "Environnement et climat": ["climat", "climatique", "rechauffement", "environnement", "biodiversite", "pollution", "secheresse", "canicule"],
    "Santé": ["sante", "hopital", "medecin", "maladie", "vaccin", "epidemie", "cancer", "medicament"],
    "Éducation": ["ecole", "education", "eleves", "enseignants", "lycee", "universite", "college"],
    "Fact-checking": ["fact-checking", "vrai ou faux", "intox", "infox", "desinformation", "fake news"],
    "Toute l'actu locale": ["nantes", "nantais", "nantaise", "loire-atlantique", "saint-nazaire", "reze", "saint-herblain"],
    "Nantes": ["nantes", "nantais", "nantaise"],
    "Culture à Nantes": ["nantes+concert", "nantes+exposition", "nantes+festival", "nantes+spectacle", "nantes+musee", "nantes+theatre", "voyage a nantes", "stereolux"],
    "Toute l'actu tech": ["tech", "smartphone", "apple", "google", "microsoft", "intelligence artificielle", "cybersecurite", "logiciel", "ordinateur"],
    "Intelligence artificielle": ["intelligence artificielle", "ia", "chatgpt", "openai", "anthropic", "mistral ai", "gemini", "llm"],
    "Veille informatique": ["developpeur", "logiciel", "framework", "javascript", "python", "linux", "windows", "navigateur", "cloud", "faille", "open source", "processeur", "carte graphique"],
    "Toute l'actu sciences": ["science", "scientifique", "chercheurs", "etude", "espace", "nasa", "esa", "astronomie", "physique", "fossile"],
    "Astronomie": ["astronomie", "telescope", "comete", "galaxie", "exoplanete", "eclipse", "asteroide", "nebuleuse", "trou noir"],
    "Physique": ["physique", "physicien", "quantique", "particule", "cern", "fusion nucleaire", "photon"],
    "Archéologie": ["archeologie", "archeologue", "archeologues", "fouilles", "vestiges", "sarcophage", "pharaon"],
    "Paléontologie": ["paleontologie", "paleontologue", "dinosaure", "dinosaures", "fossile", "fossiles", "mammouth", "neandertal"],
    "Toute l'actu jeux vidéo": ["jeu video", "jeux video", "nintendo", "playstation", "xbox", "switch 2", "steam", "ps5", "gaming"],
    "Jeux indépendants": ["jeu independant", "jeux independants", "indie", "studio independant"],
    "Toute la pop culture": ["cinema", "film", "serie", "manga", "anime", "bande dessinee", "comics", "musique", "album", "netflix"],
    "Cinéma": ["cinema", "film", "box-office", "realisateur", "realisatrice", "bande-annonce", "festival de cannes"],
    "Séries": ["serie", "saison", "episode", "showrunner"],
    "Anime": ["anime", "animation japonaise", "crunchyroll", "ghibli"],
    "Manga": ["manga", "mangas", "mangaka", "shonen", "one piece"],
    "Dragon Ball": ["dragon ball", "goku", "toriyama"],
    "BD et comics": ["bande dessinee", "bd", "comics", "marvel", "dc comics", "angouleme"],
    "Plateformes de streaming": ["netflix", "disney+", "prime video", "canal+", "apple tv", "crunchyroll"],
    "Musique": ["musique", "album", "concert", "chanteur", "chanteuse", "rappeur", "tournee"],
    "Toute l'actu création": ["illustration", "illustrateur", "illustratrice", "graphisme", "design", "affiche", "street art", "serigraphie", "artisanat"],
    "Sérigraphie": ["serigraphie", "serigraphe"],
    "Street art": ["street art", "graffiti", "fresque", "muraliste", "banksy"],
    "Toute l'actu argent": ["bourse", "cac 40", "banque", "credit", "taux", "epargne", "placement", "bitcoin", "etf", "livret a"],
    "Bourse et CAC 40": ["bourse", "cac 40", "wall street", "nasdaq", "marches financiers", "dividende"],
    "ETF": ["etf", "tracker", "trackers", "fonds indiciel"],
    "Épargne et placements": ["epargne", "livret a", "assurance vie", "pea", "placement", "placements"],
    "Cryptomonnaies": ["bitcoin", "crypto", "cryptomonnaie", "cryptomonnaies", "ethereum", "blockchain"],
    "Tout le quotidien": ["jardin", "jardinage", "potager", "bricolage", "maison", "chien", "chiens", "renovation"],
    "Jardinage et potager": ["jardin", "jardinage", "potager", "semis", "plantes", "tondeuse"],
    "Bricolage": ["bricolage", "diy", "renovation", "perceuse", "outillage"],
    "Chiens": ["chien", "chiens", "chiot", "chiots", "canin", "canine"],
    "Tout le voyage": ["voyage", "voyager", "tourisme", "vacances", "destination", "compagnie aerienne"],
}


# ---------------------------------------------------------------- réseau
def http(url, data=None, headers=None, timeout=20):
    """Renvoie (code HTTP, texte, URL finale). Code 0 = erreur réseau."""
    h = {"User-Agent": UA, "Accept-Language": "fr-FR,fr;q=0.9"}
    h.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read(3_000_000)
            charset = r.headers.get_content_charset() or "utf-8"
            return r.status, raw.decode(charset, "replace"), r.geturl()
    except urllib.error.HTTPError as e:
        return e.code, "", url
    except Exception as e:  # délai dépassé, DNS, TLS…
        return 0, f"{type(e).__name__}: {e}", url


def gnews_search(site, n=1):
    q = urllib.parse.urlencode({"q": f"site:{site} when:2d", "hl": "fr", "gl": "FR", "ceid": "FR:fr"})
    code, text, _ = http(f"https://news.google.com/rss/search?{q}")
    if code != 200:
        return [], code
    items = []
    try:
        root = ET.fromstring(text.encode())
    except ET.ParseError:
        return [], code
    for it in root.iter("item"):
        items.append({"title": (it.findtext("title") or "").strip(),
                      "link": (it.findtext("link") or "").strip()})
        if len(items) >= n:
            break
    return items, code


# ------------------------------------------- décodage Google Actualités
def gnews_id(url):
    m = re.search(r"/articles/([^?/#]+)", url)
    return m.group(1) if m else None


def decode_base64_legacy(aid):
    """Anciens liens : l'adresse réelle est encodée directement dans l'identifiant."""
    try:
        raw = base64.urlsafe_b64decode(aid + "=" * (-len(aid) % 4))
    except Exception:
        return None
    m = re.search(rb"https?://[\x21-\x7e]+", raw)
    if m and b"news.google" not in m.group(0):
        return m.group(0).decode("ascii", "replace")
    return None


def decode_batchexecute(aid):
    """Liens récents : on demande à Google l'adresse réelle (méthode non officielle)."""
    code, html, _ = http(f"https://news.google.com/articles/{aid}")
    if code != 200:
        code, html, _ = http(f"https://news.google.com/rss/articles/{aid}")
    sg = re.search(r'data-n-a-sg="([^"]+)"', html)
    ts = re.search(r'data-n-a-ts="([^"]+)"', html)
    if not (sg and ts):
        return None, f"signature introuvable (HTTP {code})"
    inner = ('["garturlreq",[["X","X",["X","X"],null,null,1,1,"US:en",null,1,null,null,'
             'null,null,null,0,1],"X","X",1,[1,1,1],1,1,null,0,0,null,0],'
             f'"{aid}",{ts.group(1)},"{sg.group(1)}"]')
    body = "f.req=" + urllib.parse.quote(json.dumps([[["Fbv4je", inner]]]))
    code, text, _ = http("https://news.google.com/_/DotsSplashUi/data/batchexecute",
                         data=body.encode(),
                         headers={"Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"})
    if code != 200:
        return None, f"batchexecute HTTP {code}"
    try:
        parsed = json.loads(text.split("\n\n")[1])[:-2]
        return json.loads(parsed[0][2])[1], None
    except Exception:
        m = re.search(r'https?://(?!(?:[a-z]+\.)?google)[^"\\\s]+', text)
        if m:
            return m.group(0), None
        return None, "réponse illisible"


def resolve(link):
    """Renvoie (adresse réelle ou None, méthode ou motif d'échec)."""
    if "news.google.com" not in link:
        return link, "lien direct"
    aid = gnews_id(link)
    if not aid:
        return None, "identifiant introuvable"
    url = decode_base64_legacy(aid)
    if url:
        return url, "base64"
    url, err = decode_batchexecute(aid)
    return (url, "batchexecute") if url else (None, err)


# -------------------------------------------- détection « payant »
def _walk(obj, key):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == key:
                yield v
            yield from _walk(v, key)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk(v, key)


def _as_bool(v):
    if isinstance(v, bool):
        return v
    if isinstance(v, str) and v.strip().lower() in ("true", "false"):
        return v.strip().lower() == "true"
    return None


def detect_paywall(html):
    """Renvoie (verdict, indice). Verdicts : Payant, Gratuit, Compteur, Non déclaré."""
    flags = []
    for block in re.findall(r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
                            html, re.S | re.I):
        try:
            data = json.loads(unescape(block.strip()))
        except Exception:
            continue
        flags += [b for b in (_as_bool(v) for v in _walk(data, "isAccessibleForFree")) if b is not None]
    tier = re.search(r'<meta[^>]+property=["\']article:content_tier["\'][^>]+content=["\']([^"\']+)', html, re.I) \
        or re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']article:content_tier', html, re.I)
    tier = tier.group(1).lower() if tier else None
    if False in flags or tier == "locked":
        return "Payant", "isAccessibleForFree=false" if False in flags else "content_tier=locked"
    if tier == "metered":
        return "Compteur", "content_tier=metered"
    if True in flags or tier == "free":
        return "Gratuit", "isAccessibleForFree=true" if True in flags else "content_tier=free"
    return "Non déclaré", "aucune mention"


# ----------------------------------------- découverte et lecture des flux
def discover_feed(home):
    code, html, final = http(home)
    if code == 200:
        for tag in re.findall(r"<link\b[^>]*>", html, re.I):
            if re.search(r'rel=["\']?alternate', tag, re.I) and \
               re.search(r'type=["\']application/(rss|atom)\+xml', tag, re.I):
                href = re.search(r'href=["\']([^"\']+)', tag, re.I)
                if href:
                    return urllib.parse.urljoin(final, unescape(href.group(1))), "déclaré dans la page"
    for path in ("rss", "feed", "rss.xml", "feed.xml", "index.rss", "rss/une.xml"):
        url = urllib.parse.urljoin(home if home.endswith("/") else home + "/", path)
        c, text, _ = http(url)
        if c == 200 and re.search(r"<(rss|feed)\b", text[:2000], re.I):
            return url, f"adresse courante /{path}"
    return None, f"introuvable (accueil HTTP {code})"


def _strip_tags(s):
    return re.sub(r"<[^>]+>", " ", unescape(s or ""))


def read_feed(feed_url, n=60):
    code, text, _ = http(feed_url)
    if code != 200:
        return []
    try:
        root = ET.fromstring(text.encode())
    except ET.ParseError:
        return []
    out = []
    for it in root.iter("item"):
        out.append({"title": (it.findtext("title") or "").strip(),
                    "link": (it.findtext("link") or "").strip(),
                    "extra": " ".join([_strip_tags(it.findtext("description"))[:300]]
                                      + [c.text or "" for c in it.findall("category")])})
    atom = "{http://www.w3.org/2005/Atom}"
    for en in root.iter(atom + "entry"):
        lk = en.find(atom + "link")
        out.append({"title": (en.findtext(atom + "title") or "").strip(),
                    "link": lk.get("href", "") if lk is not None else "",
                    "extra": _strip_tags(en.findtext(atom + "summary"))[:300]})
    return out[:n]


# ----------------------------------------------- classement par mots-clés
def norm(s):
    s = unicodedata.normalize("NFD", (s or "").lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def _has(text, word):
    return re.search(r"(?<![\w])" + re.escape(word) + r"(?![\w])", text) is not None


def classify(title, extra=""):
    text = norm(title + " " + extra)
    hits = []
    for cat, rules in CATEGORIES.items():
        for rule in rules:
            if all(_has(text, norm(part)) for part in rule.split("+")):
                hits.append(cat)
                break
    return hits


# ------------------------------------------------------------ essai
def check_article(media, origin, title, link):
    row = {"media": media, "origin": origin, "title": title[:70]}
    url, how = resolve(link)
    if origin == "Google":
        time.sleep(PAUSE)
    row["resolved"] = url
    row["resolve_how"] = how
    if not url:
        row.update(reached="—", verdict="—", hint=how)
        return row
    code, html, final = http(url)
    time.sleep(PAUSE)
    row["final"] = final
    if code != 200:
        row.update(reached=f"Non (HTTP {code})" if code else "Non (erreur réseau)", verdict="—",
                   hint=html[:60] if code == 0 else "")
        return row
    verdict, hint = detect_paywall(html)
    row.update(reached="Oui", verdict=verdict, hint=hint)
    return row


def main():
    t0 = time.time()
    rows, feeds, bfm, pool = [], [], [], []

    print("== A. Flux RSS des médias ==")
    for name, home, statut in MEDIAS:
        feed, how = discover_feed(home)
        items = read_feed(feed) if feed else []
        feeds.append({"media": name, "statut": statut, "feed": feed, "how": how, "count": len(items)})
        print(f"  [{statut}] {name}: {feed} ({how}) — {len(items)} articles")
        for it in items:
            pool.append(dict(it, media=name))
        if statut == "F" and items:
            rows.append(check_article(name, "Flux direct", items[0]["title"], items[0]["link"]))
        time.sleep(PAUSE)

    print("== B. Classement des articles des flux ==")
    coverage = {c: 0 for c in CATEGORIES}
    examples = {c: "" for c in CATEGORIES}
    unclassified = 0
    for it in pool:
        cats = classify(it["title"], it.get("extra", ""))
        if not cats:
            unclassified += 1
        for c in cats:
            coverage[c] += 1
            if not examples[c]:
                examples[c] = f"{it['title'][:60]} ({it['media']})"

    print("== C-E. Articles via Google Actualités ==")
    for name, site in GOOGLE_SITES:
        items, code = gnews_search(site)
        if not items:
            rows.append({"media": name, "origin": "Google", "title": "(aucun résultat)", "resolved": None,
                         "resolve_how": f"recherche HTTP {code}", "reached": "—", "verdict": "—", "hint": ""})
        for it in items:
            rows.append(check_article(name, "Google", it["title"], it["link"]))
        time.sleep(PAUSE)

    print("== F. BFMTV / BFM Business ==")
    for label, query_site in (("BFM Business", "bfmtv.com/economie"), ("BFMTV", "bfmtv.com")):
        items, code = gnews_search(query_site, n=3)
        for it in items:
            url, how = resolve(it["link"])
            bfm.append({"label": label, "title": it["title"][:60], "url": url or f"non résolu ({how})"})
            time.sleep(PAUSE)
        if not items:
            bfm.append({"label": label, "title": "(aucun résultat)", "url": f"HTTP {code}"})

    report(rows, feeds, bfm, coverage, examples, len(pool), unclassified, round((time.time() - t0) / 60, 1))


def report(rows, feeds, bfm, coverage, examples, pool_size, unclassified, minutes):
    g = [r for r in rows if r["origin"] == "Google" and r["title"] != "(aucun résultat)"]
    reached = [r for r in rows if r.get("reached") == "Oui"]
    declared = [r for r in reached if r["verdict"] != "Non déclaré"]
    tried = [r for r in rows if r.get("resolved")]
    blocked = [r for r in tried if str(r.get("reached", "")).startswith("Non")]
    pct = lambda a, b: f"{a}/{b} ({round(100 * a / b)} %)" if b else "0/0"
    ok_feeds = [f for f in feeds if f["count"]]

    def verdict(n):
        if n >= 10:
            return "Flux suffisants"
        if n >= 3:
            return "Flux + complément Google"
        return "Google nécessaire"

    L = ["# Flow Actu — résultats de l'essai technique", "", f"Durée : {minutes} min", ""]
    L += ["## Résumé", "",
          "| Question | Résultat |", "|---|---|",
          f"| A. Médias avec un flux RSS trouvé et lisible | {pct(len(ok_feeds), len(feeds))} |",
          f"| B. Articles lus dans les flux / non classés | {pool_size} / {unclassified} |",
          f"| B. Catégories couvertes par les flux seuls (≥ 10 articles) | "
          f"{pct(sum(1 for n in coverage.values() if n >= 10), len(coverage))} |",
          f"| C. Liens Google Actualités décodés | {pct(sum(1 for r in g if r['resolved']), len(g))} |",
          f"| D. Statut payant / gratuit détectable (pages atteintes) | {pct(len(declared), len(reached))} |",
          f"| E. Pages bloquées ou en erreur | {pct(len(blocked), len(tried))} |",
          ""]
    L += ["## B. Couverture des catégories par les flux RSS", "",
          "| Catégorie | Articles trouvés | Verdict | Exemple |", "|---|---|---|---|"]
    for c, n in sorted(coverage.items(), key=lambda kv: kv[1]):
        L.append(f"| {c} | {n} | {verdict(n)} | {examples[c].replace('|', '/')} |")
    L += ["", "## C-E. Articles testés (payant / gratuit)", "",
          "| Média | Origine | Décodage | Page atteinte | Statut détecté | Indice | Titre |",
          "|---|---|---|---|---|---|---|"]
    for r in rows:
        dec = r.get("resolve_how", "") if r["origin"] == "Google" else "—"
        L.append(f"| {r['media']} | {r['origin']} | {dec} | {r.get('reached', '—')} | {r.get('verdict', '—')} "
                 f"| {str(r.get('hint', '')).replace('|', '/')} | {r['title'].replace('|', '/')} |")
    L += ["", "## F. BFMTV / BFM Business", "", "| Recherche | Adresse réelle | Titre |", "|---|---|---|"]
    for b in bfm:
        L.append(f"| {b['label']} | {b['url']} | {b['title'].replace('|', '/')} |")
    L += ["", "## A. Flux RSS des médias", "", "| Média | Statut | Flux | Comment | Articles |", "|---|---|---|---|---|"]
    for f in feeds:
        L.append(f"| {f['media']} | {'Favori' if f['statut'] == 'F' else 'Neutre'} | {f['feed'] or '—'} "
                 f"| {f['how']} | {f['count']} |")
    text = "\n".join(L) + "\n"

    print(text)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write(text)
    with open("resultats-essai.json", "w", encoding="utf-8") as fh:
        json.dump({"articles": rows, "flux": feeds, "bfm": bfm, "couverture": coverage},
                  fh, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
