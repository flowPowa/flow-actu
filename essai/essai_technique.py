#!/usr/bin/env python3
"""Flow Actu — essai technique n° 2 (prototype jetable).

Suite de l'essai n° 1 (cahier des charges § 5 et § 6.3). Mesure :
  A. les flux RSS des ~60 médias, avec des adresses connues pour ceux que
     l'essai n° 1 n'avait pas trouvés ;
  B. le rangement des articles par catégorie, avec les nouvelles règles
     (titre seul, familles de médias, mots d'exclusion), avec 3 exemples
     par catégorie pour juger la qualité ;
  C. si Google Actualités complète bien les catégories trop pauvres ;
  D. le repérage « payant / gratuit », sur un échantillon plus large
     (2 articles par média), résumé média par média.

Bibliothèque standard Python uniquement. Le rapport s'affiche dans le résumé
du workflow GitHub (ou dans le terminal si lancé à la main).
"""
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

# Le robot se présente honnêtement (nom + adresse du projet).
UA = "Mozilla/5.0 (compatible; FlowActu/0.2; +https://github.com/flowPowa/flow-actu)"
PAUSE = 1.0             # secondes entre deux visites, par politesse
PAYWALL_PER_MEDIA = 2   # articles vérifiés par média pour le test « payant »

# ------------------------------------------------------------------ médias
# Familles : actu, local, tech, sciences, jeux, pop, creation, argent, quotidien, voyage
# "*" = média généraliste (peut alimenter toutes les familles, sur le titre seul).
# Pour un média spécialisé, la 1re famille est sa famille principale : tous ses
# articles alimentent la catégorie large de cette famille.
# "feeds" = adresses connues, essayées en premier (à vérifier par l'essai).
MEDIAS = [
    # nom, page d'accueil, statut (F/N), familles, adresses de flux connues
    ("Ouest-France", "https://www.ouest-france.fr", "F", ["*"], []),
    ("Mediapart", "https://www.mediapart.fr", "F", ["*"], ["https://www.mediapart.fr/articles/feed"]),
    ("Courrier international", "https://www.courrierinternational.com", "F", ["*"], []),
    ("Arte", "https://www.arte.tv/fr/", "F", ["*"], ["https://www.arte.tv/fr/rss.xml"]),
    ("Les Echos", "https://www.lesechos.fr", "F", ["argent", "actu", "tech"], [
        "https://services.lesechos.fr/rss/les-echos-economie.xml",
        "https://services.lesechos.fr/rss/les-echos-entreprises.xml",
        "https://services.lesechos.fr/rss/les-echos-tech-medias.xml",
        "https://services.lesechos.fr/rss/les-echos-finance-marches.xml",
        "https://services.lesechos.fr/rss/les-echos-monde.xml",
        "https://services.lesechos.fr/rss/les-echos-politique.xml"]),
    ("Numerama", "https://www.numerama.com", "F", ["tech", "sciences", "pop", "jeux"], []),
    ("Frandroid", "https://www.frandroid.com", "F", ["tech"], []),
    ("Korben", "https://korben.info", "F", ["tech"], []),
    ("Écran Large", "https://www.ecranlarge.com", "F", ["pop"], []),
    ("developpez.com", "https://www.developpez.com", "F", ["tech"], []),
    ("Le Monde", "https://www.lemonde.fr", "N", ["*"], []),
    ("Le Figaro", "https://www.lefigaro.fr", "N", ["*"], ["https://www.lefigaro.fr/rss/figaro_actualites.xml"]),
    ("Libération", "https://www.liberation.fr", "N", ["*"], ["https://www.liberation.fr/arc/outboundfeeds/rss-all/?outputType=xml"]),
    ("Le Parisien", "https://www.leparisien.fr", "N", ["*"], ["https://feeds.leparisien.fr/leparisien/rss"]),
    ("franceinfo", "https://www.francetvinfo.fr", "N", ["*"], ["https://www.francetvinfo.fr/titres.rss"]),
    ("20 Minutes", "https://www.20minutes.fr", "N", ["*"], []),
    ("L'Humanité", "https://www.humanite.fr", "N", ["*"], []),
    ("Le Point", "https://www.lepoint.fr", "N", ["*"], ["https://www.lepoint.fr/24h-infos/rss.xml"]),
    ("L'Express", "https://www.lexpress.fr", "N", ["*"], []),
    ("L'Obs", "https://www.nouvelobs.com", "N", ["*"], []),
    ("Marianne", "https://www.marianne.net", "N", ["*"], ["https://www.marianne.net/rss.xml"]),
    ("HuffPost", "https://www.huffingtonpost.fr", "N", ["*"], []),
    ("LCI", "https://www.tf1info.fr", "N", ["*"], []),
    ("France 24", "https://www.france24.com/fr/", "N", ["*"], []),
    ("Europe 1", "https://www.europe1.fr", "N", ["*"], []),
    ("RTL", "https://www.rtl.fr", "N", ["*"], ["https://www.rtl.fr/rss/une.xml"]),
    ("France Inter", "https://www.radiofrance.fr/franceinter", "N", ["*"], []),
    ("RFI", "https://www.rfi.fr/fr/", "N", ["*"], []),
    ("The Conversation", "https://theconversation.com/fr", "N", ["*"], ["https://theconversation.com/fr/articles.atom"]),
    ("La Tribune", "https://www.latribune.fr", "N", ["argent", "actu", "tech"], []),
    ("Capital", "https://www.capital.fr", "N", ["argent", "actu"], []),
    ("Challenges", "https://www.challenges.fr", "N", ["argent", "actu"], []),
    ("Boursorama", "https://www.boursorama.com", "N", ["argent", "actu"], ["https://www.boursorama.com/rss/actualites/"]),
    ("Investir", "https://investir.lesechos.fr", "N", ["argent"], ["https://investir.lesechos.fr/rss"]),
    ("BFM Business", "https://www.bfmtv.com/economie/", "N", ["argent", "actu"], ["https://www.bfmtv.com/rss/economie/"]),
    ("Presse Océan", "https://www.presseocean.fr", "N", ["local", "*"], ["https://www.presseocean.fr/rss.xml"]),
    ("France 3 Pays de la Loire", "https://france3-regions.francetvinfo.fr/pays-de-la-loire", "N", ["local", "*"], []),
    ("Actu.fr Pays de la Loire", "https://actu.fr/pays-de-la-loire", "N", ["local", "*"], []),
    ("ici Loire Océan", "https://www.francebleu.fr/loire-ocean", "N", ["local", "*"], ["https://www.francebleu.fr/rss/loire-ocean.xml"]),
    ("Le Télégramme", "https://www.letelegramme.fr", "N", ["local", "*"], ["https://www.letelegramme.fr/rss.xml"]),
    ("Next", "https://next.ink", "N", ["tech"], []),
    ("01net", "https://www.01net.com", "N", ["tech", "jeux"], []),
    ("Clubic", "https://www.clubic.com", "N", ["tech", "jeux"], []),
    ("ZDNet", "https://www.zdnet.fr", "N", ["tech"], []),
    ("Le Monde Informatique", "https://www.lemondeinformatique.fr", "N", ["tech"], []),
    ("Journal du Geek", "https://www.journaldugeek.com", "N", ["tech", "sciences", "pop", "jeux"], []),
    ("Futura", "https://www.futura-sciences.com", "N", ["sciences", "quotidien"], []),
    ("Sciences et Avenir", "https://www.sciencesetavenir.fr", "N", ["sciences", "actu"], []),
    ("Ciel et Espace", "https://www.cieletespace.fr", "N", ["sciences"], []),
    ("Pour la Science", "https://www.pourlascience.fr", "N", ["sciences"], []),
    ("Gamekult", "https://www.gamekult.com", "N", ["jeux", "pop"], []),
    ("Jeuxvideo.com", "https://www.jeuxvideo.com", "N", ["jeux", "pop"], ["https://www.jeuxvideo.com/rss/rss.xml"]),
    ("Gameblog", "https://www.gameblog.fr", "N", ["jeux", "pop"], []),
    ("ActuGaming", "https://www.actugaming.net", "N", ["jeux"], []),
    ("Millenium", "https://www.millenium.org", "N", ["jeux"], ["https://www.millenium.org/rss"]),
    ("AlloCiné", "https://www.allocine.fr", "N", ["pop"], ["http://rss.allocine.fr/ac/actualites/cine"]),
    ("Première", "https://www.premiere.fr", "N", ["pop"], ["https://www.premiere.fr/rss/actu-live"]),
    ("Konbini", "https://www.konbini.com", "N", ["pop", "creation"], ["https://www.konbini.com/fr/feed/"]),
    ("Télérama", "https://www.telerama.fr", "N", ["pop", "creation", "actu"], []),
    ("Les Inrocks", "https://www.lesinrocks.com", "N", ["pop", "creation"], ["https://www.lesinrocks.com/feed/"]),
    ("Manga-News", "https://www.manga-news.com", "N", ["pop"], []),
    ("Nautiljon", "https://www.nautiljon.com", "N", ["pop"], ["https://www.nautiljon.com/actualite/rss.php"]),
]

# --------------------------------------------------------------- catégories
# Règles de mots-clés (comparaison sur le TITRE seul, sans accents ni majuscules) :
#   "mot"        → le mot (ou l'expression) doit apparaître en entier ;
#   "a+b"        → les deux doivent apparaître ;
#   "re:..."     → expression régulière ;
#   "spe:mot"    → ne compte que pour les médias spécialisés de la famille.
# "not" : expressions qui annulent la correspondance.
# "all_from_specialists" : catégorie large qui reçoit tous les articles des médias
#   dont c'est la famille principale. "all_from_generalists" : idem pour les généralistes.
C = {}


def cat(name, fam, kw, not_=(), large=False, all_spec=False, all_gen=False):
    C[name] = {"fam": fam, "kw": kw, "not": list(not_), "large": large,
               "all_spec": all_spec, "all_gen": all_gen}


cat("À la une France", "actu", [], large=True, all_gen=True)
cat("International", "actu", ["international", "internationale", "ukraine", "russie", "chine", "etats-unis", "israel", "gaza", "onu", "otan", "diplomatie", "diplomatique"])
cat("Europe", "actu", ["europe", "europeen", "europeenne", "europeens", "union europeenne", "bruxelles", "commission europeenne"], not_=["europe 1"])
cat("Politique France", "actu", ["gouvernement", "assemblee nationale", "senat", "depute", "deputes", "ministre", "elysee", "presidentielle", "municipales", "legislatives"])
cat("Économie", "actu", ["economie", "economique", "inflation", "croissance", "chomage", "pib", "budget", "dette publique", "pouvoir d'achat"])
cat("Société", "actu", ["logement", "pauvrete", "precarite", "immigration", "greve", "manifestation", "manifestations", "laicite", "discriminations"])
cat("Environnement et climat", "actu", ["climat", "climatique", "rechauffement", "environnement", "environnementale", "biodiversite", "pollution", "secheresse", "canicule", "cop31"])
cat("Santé", "actu", ["sante", "hopital", "hopitaux", "medecin", "medecins", "maladie", "vaccin", "epidemie", "cancer", "medicament", "medicaments"])
cat("Éducation", "actu", ["ecole", "ecoles", "education nationale", "eleves", "enseignants", "enseignant", "lycee", "lyceens", "lyceenne", "universite", "college", "baccalaureat", "rentree scolaire"], not_=["college de france"])
cat("Fact-checking", "actu", ["fact-checking", "vrai ou faux", "intox", "infox", "desinformation", "fake news", "fausse information"])

cat("Toute l'actu locale", "local", ["nantes", "nantais", "nantaise", "loire-atlantique", "saint-nazaire", "reze", "saint-herblain"], large=True, all_spec=True)
cat("Nantes", "local", ["nantes", "nantais", "nantaise"])
cat("Culture à Nantes", "local", ["nantes+concert", "nantes+exposition", "nantes+festival", "nantes+spectacle", "nantes+musee", "nantes+theatre", "voyage a nantes", "stereolux", "lieu unique",
                                   "spe:concert", "spe:exposition", "spe:festival", "spe:spectacle", "spe:theatre", "spe:musee"])

cat("Toute l'actu tech", "tech", ["smartphone", "iphone", "apple", "google", "microsoft", "intelligence artificielle", "cybersecurite", "cyberattaque", "logiciel", "numerique"], large=True, all_spec=True)
cat("Intelligence artificielle", "tech", ["ia", "intelligence artificielle", "chatgpt", "openai", "anthropic", "mistral ai", "gemini", "llm", "agent ia", "agents ia"])
cat("Veille informatique", "tech", ["developpeur", "developpeurs", "logiciel", "framework", "javascript", "python", "linux", "windows", "navigateur", "cloud", "faille", "open source", "processeur", "carte graphique", "mise a jour"])

cat("Toute l'actu sciences", "sciences", ["scientifique", "scientifiques", "chercheurs", "astronomie", "physique quantique", "dinosaure", "nasa", "esa", "spatial", "spatiale"], large=True, all_spec=True)
cat("Astronomie", "sciences", ["astronomie", "astronome", "astronomes", "telescope", "comete", "galaxie", "exoplanete", "eclipse", "asteroide", "nebuleuse", "trou noir", "etoile filante", "aurores boreales"])
cat("Physique", "sciences", ["physique", "physicien", "physiciens", "quantique", "particule", "particules", "cern", "fusion nucleaire", "photon"],
    not_=["activite physique", "condition physique", "exercice physique", "physique et mental", "sante physique", "violences physiques", "aspect physique"])
cat("Archéologie", "sciences", ["archeologie", "archeologue", "archeologues", "archeologique", "fouilles", "vestiges", "sarcophage", "pharaon", "necropole"])
cat("Paléontologie", "sciences", ["paleontologie", "paleontologue", "paleontologues", "dinosaure", "dinosaures", "fossile de", "fossiles de", "mammouth", "neandertal", "prehistorique"],
    not_=["energies fossiles", "energie fossile", "combustibles fossiles", "carburants fossiles"])

cat("Toute l'actu jeux vidéo", "jeux", ["jeu video", "jeux video", "nintendo", "playstation", "xbox", "switch 2", "steam", "ps5", "gta 6"], large=True, all_spec=True)
cat("Jeux indépendants", "jeux", ["jeu independant", "jeux independants", "indie", "studio independant", "spe:independant"])

cat("Toute la pop culture", "pop", ["cinema", "film", "manga", "bande dessinee", "comics", "musique", "album", "netflix", "serie tv"], large=True, all_spec=True)
cat("Cinéma", "pop", ["cinema", "film", "films", "box-office", "realisateur", "realisatrice", "bande-annonce", "festival de cannes", "oscars"])
cat("Séries", "pop", ["serie tv", "series tv", "re:saison \\d+", "showrunner", "spe:serie", "spe:series", "spe:episode"])
cat("Anime", "pop", ["animation japonaise", "crunchyroll", "ghibli", "miyazaki", "spe:anime", "spe:animes"])
cat("Manga", "pop", ["manga", "mangas", "mangaka", "shonen", "seinen", "one piece"])
cat("Dragon Ball", "pop", ["dragon ball", "goku", "toriyama"], not_=["dragon quest"])
cat("BD et comics", "pop", ["bande dessinee", "bandes dessinees", "bd", "comics", "marvel", "dc comics", "angouleme"])
cat("Plateformes de streaming", "pop", ["netflix", "disney+", "prime video", "canal+", "apple tv", "crunchyroll"])
cat("Musique", "pop", ["musique", "musical", "album", "concert", "chanteur", "chanteuse", "rappeur", "rappeuse", "tournee"])

cat("Toute l'actu création", "creation", ["illustration", "illustrateur", "illustratrice", "graphisme", "graphiste", "design", "street art", "serigraphie", "artisanat", "artisan"], large=True)
cat("Sérigraphie", "creation", ["serigraphie", "serigraphe", "serigraphies"])
cat("Street art", "creation", ["street art", "street-art", "graffiti", "graff", "muraliste", "banksy", "fresque murale"])

cat("Toute l'actu argent", "argent", ["bourse", "cac 40", "banque", "banques", "epargne", "livret a", "bitcoin", "etf", "taux d'interet", "credit immobilier"], large=True, all_spec=True)
cat("Bourse et CAC 40", "argent", ["bourse", "cac 40", "wall street", "nasdaq", "marches financiers", "dividende", "dividendes"], not_=["bourse d'etudes", "bourses d'etudes"])
cat("ETF", "argent", ["etf", "fonds indiciel", "fonds indiciels", "trackers"])
cat("Épargne et placements", "argent", ["epargne", "epargnants", "livret a", "assurance vie", "assurance-vie", "pea", "placer son argent", "placements financiers"])
cat("Cryptomonnaies", "argent", ["bitcoin", "crypto", "cryptos", "cryptomonnaie", "cryptomonnaies", "ethereum", "blockchain"])

cat("Tout le quotidien", "quotidien", ["jardin", "jardinage", "potager", "bricolage", "renovation", "chien", "chiens", "maison"], not_=["maison blanche"], large=True)
cat("Jardinage et potager", "quotidien", ["jardin", "jardins", "jardinage", "jardinier", "potager", "semis", "tondeuse", "pelouse"], not_=["jardin d'enfants"])
cat("Bricolage", "quotidien", ["bricolage", "bricoler", "diy", "renovation", "perceuse", "outillage"])
cat("Chiens", "quotidien", ["chien", "chiens", "chiot", "chiots", "canin", "canine", "toutou"])

cat("Tout le voyage", "voyage", ["voyage", "voyages", "voyager", "tourisme", "touristes", "vacances", "compagnie aerienne", "billet d'avion"], large=True)


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


# --------------------------------------------------------- lecture des flux
def _local(tag):
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _strip(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", unescape(s or ""))).strip()


def parse_feed(text):
    """Lit un flux RSS 2.0, RSS 1.0 (RDF) ou Atom. Repli tolérant si le XML est invalide."""
    items = []
    try:
        root = ET.fromstring(text.encode("utf-8", "replace"))
        for el in root.iter():
            if _local(el.tag) not in ("item", "entry"):
                continue
            title, link, date = "", "", ""
            for ch in el:
                n = _local(ch.tag)
                if n == "title":
                    title = _strip("".join(ch.itertext()))
                elif n == "link":
                    link = (ch.get("href") or ch.text or "").strip() or link
                elif n in ("pubDate", "date", "updated", "published") and not date:
                    date = (ch.text or "").strip()
            items.append({"title": title, "link": link, "date": date})
        return items
    except ET.ParseError:
        pass
    for block in re.findall(r"<item\b.*?</item>", text, re.S | re.I):
        t = re.search(r"<title[^>]*>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", block, re.S | re.I)
        l = re.search(r"<link[^>]*>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</link>", block, re.S | re.I)
        items.append({"title": _strip(t.group(1)) if t else "", "link": (l.group(1).strip() if l else ""), "date": ""})
    return items


def looks_like_feed(text):
    return re.search(r"<(rss|feed|rdf:RDF)\b", text[:3000], re.I) is not None


def discover_feeds(home, known):
    """Renvoie (liste d'adresses de flux qui répondent, comment, code HTTP de l'accueil)."""
    good = []
    for url in known:
        c, text, _ = http(url)
        if c == 200 and looks_like_feed(text):
            good.append(url)
        time.sleep(PAUSE / 2)
    if good:
        return good, "adresse connue", None
    code, html, final = http(home)
    if code == 200:
        for tag in re.findall(r"<link\b[^>]*>", html, re.I):
            if re.search(r'rel=["\']?alternate', tag, re.I) and \
               re.search(r'type=["\']application/(rss|atom)\+xml', tag, re.I):
                href = re.search(r'href=["\']([^"\']+)', tag, re.I)
                if href:
                    return [urllib.parse.urljoin(final, unescape(href.group(1)))], "déclaré dans la page", code
    for path in ("rss", "feed", "rss.xml", "feed.xml", "index.rss", "rss/une.xml"):
        url = urllib.parse.urljoin(home if home.endswith("/") else home + "/", path)
        c, text, _ = http(url)
        if c == 200 and looks_like_feed(text):
            return [url], f"adresse courante /{path}", code
    tried = "adresses connues en échec, " if known else ""
    return [], f"{tried}introuvable (accueil HTTP {code})", code


def read_feeds(urls, n=60):
    out, seen = [], set()
    for url in urls:
        c, text, _ = http(url)
        if c != 200:
            continue
        for it in parse_feed(text):
            if it["link"] not in seen:
                seen.add(it["link"])
                out.append(it)
        time.sleep(PAUSE / 2)
    return out[:n * max(1, len(urls))]


# ----------------------------------------------- rangement par mots-clés
def norm(s):
    s = unicodedata.normalize("NFD", (s or "").lower().replace("’", "'"))
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def _has(text, word):
    return re.search(r"(?<![\w])" + re.escape(word) + r"(?![\w])", text) is not None


def _rule_ok(text, rule, specialist):
    if rule.startswith("spe:"):
        if not specialist:
            return False
        rule = rule[4:]
    if rule.startswith("re:"):
        return re.search(rule[3:], text) is not None
    return all(_has(text, norm(p)) for p in rule.split("+"))


def classify(title, families):
    """Renvoie la liste des catégories pour un titre venant d'un média de ces familles."""
    text = norm(title)
    generalist = "*" in families
    primary = None if generalist else families[0]
    if families[0] == "local":
        primary = "local"
    hits = []
    for name, c in C.items():
        fam = c["fam"]
        allowed = generalist or fam in families
        if not allowed:
            continue
        if any(_has(text, norm(x)) for x in c["not"]):
            continue
        if c["all_gen"] and generalist and primary is None:
            hits.append(name)
            continue
        if c["all_spec"] and primary == fam:
            hits.append(name)
            continue
        specialist = (primary == fam)
        if any(_rule_ok(text, r, specialist) for r in c["kw"]):
            hits.append(name)
    return hits


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


# ----------------------------------------------------- Google Actualités
def gnews_search(query, n=3):
    q = urllib.parse.urlencode({"q": f"{query} when:7d", "hl": "fr", "gl": "FR", "ceid": "FR:fr"})
    code, text, _ = http(f"https://news.google.com/rss/search?{q}")
    if code != 200:
        return [], code
    out = []
    try:
        root = ET.fromstring(text.encode())
    except ET.ParseError:
        return [], code
    for it in root.iter("item"):
        src = it.find("source")
        out.append({"title": (it.findtext("title") or "").strip(),
                    "source": (src.text or "").strip() if src is not None else ""})
    return out, code


def google_query(c):
    words = [k for k in c["kw"] if not k.startswith(("spe:", "re:")) and "+" not in k][:4]
    return " OR ".join(f'"{w}"' if " " in w else w for w in words)


# ------------------------------------------------------------ essai
def main():
    t0 = time.time()
    feeds, pool, paywall = [], [], {}
    empty_titles = 0

    print("== A. Flux RSS des médias ==")
    for name, home, statut, fams, known in MEDIAS:
        urls, how, _ = discover_feeds(home, known)
        items = read_feeds(urls) if urls else []
        kept = [it for it in items if it["title"] and not re.fullmatch(r"[\W_]*", it["title"])]
        empty_titles += len(items) - len(kept)
        feeds.append({"media": name, "statut": statut, "feeds": urls, "how": how, "count": len(kept)})
        print(f"  [{statut}] {name}: {len(urls)} flux ({how}) — {len(kept)} articles")
        for it in kept:
            pool.append(dict(it, media=name, fams=fams))
        # D. échantillon « payant »
        res = []
        for it in kept[:PAYWALL_PER_MEDIA]:
            code, html, _ = http(it["link"]) if it["link"] else (0, "", "")
            res.append(detect_paywall(html)[0] if code == 200 else f"Bloqué ({code})")
            time.sleep(PAUSE)
        paywall[name] = res
        time.sleep(PAUSE)

    print("== B. Rangement ==")
    coverage = {c: 0 for c in C}
    examples = {c: [] for c in C}
    unclassified = []
    for it in pool:
        cats = classify(it["title"], it["fams"])
        if not cats:
            unclassified.append(it)
        for c in cats:
            coverage[c] += 1
            if len(examples[c]) < 3:
                examples[c].append(f"{it['title'][:70]} ({it['media']})")

    print("== C. Complément Google pour les catégories faibles ==")
    google = []
    for c, n in sorted(coverage.items(), key=lambda kv: kv[1]):
        if n >= 10:
            continue
        q = google_query(C[c])
        if not q:
            google.append({"cat": c, "query": "—", "count": 0, "examples": []})
            continue
        res, code = gnews_search(q)
        google.append({"cat": c, "query": q, "count": len(res), "code": code,
                       "examples": [f"{r['title'][:70]}" for r in res[:2]]})
        time.sleep(PAUSE)

    report(feeds, coverage, examples, unclassified, google, paywall, len(pool), empty_titles,
           round((time.time() - t0) / 60, 1))


def report(feeds, coverage, examples, unclassified, google, paywall, pool_size, empty_titles, minutes):
    pct = lambda a, b: f"{a}/{b} ({round(100 * a / b)} %)" if b else "0/0"
    esc = lambda s: str(s).replace("|", "/")

    def verdict(n):
        return "Flux suffisants" if n >= 10 else ("Flux + complément Google" if n >= 3 else "Google nécessaire")

    ok_feeds = [f for f in feeds if f["count"]]
    pw_all = [v for vs in paywall.values() for v in vs]
    pw_reached = [v for v in pw_all if not v.startswith("Bloqué")]
    pw_declared = [v for v in pw_reached if v != "Non déclaré"]

    L = ["# Flow Actu — résultats de l'essai technique n° 2", "", f"Durée : {minutes} min", ""]
    L += ["## Résumé", "", "| Question | Résultat |", "|---|---|",
          f"| A. Médias avec au moins un flux lisible | {pct(len(ok_feeds), len(feeds))} |",
          f"| A. Dont trouvés grâce aux adresses connues | {sum(1 for f in ok_feeds if f['how'] == 'adresse connue')} |",
          f"| B. Articles lus / sans catégorie / sans titre (ignorés) | {pool_size} / {len(unclassified)} / {empty_titles} |",
          f"| B. Catégories avec 10 articles ou plus | {pct(sum(1 for n in coverage.values() if n >= 10), len(coverage))} |",
          f"| C. Catégories faibles où Google ramène des articles | {pct(sum(1 for g in google if g['count']), len(google))} |",
          f"| D. Pages d'articles atteintes | {pct(len(pw_reached), len(pw_all))} |",
          f"| D. Statut payant / gratuit déclaré (pages atteintes) | {pct(len(pw_declared), len(pw_reached))} |", ""]

    L += ["## B. Rangement par catégorie (3 exemples pour juger)", "",
          "| Catégorie | Articles | Verdict | Exemples |", "|---|---|---|---|"]
    for c, n in sorted(coverage.items(), key=lambda kv: kv[1]):
        L.append(f"| {c} | {n} | {verdict(n)} | {esc(' ◆ '.join(examples[c]))} |")

    L += ["", "## B. Échantillon d'articles sans catégorie", ""]
    for it in unclassified[:15]:
        L.append(f"- {esc(it['title'][:90])} ({it['media']})")

    L += ["", "## C. Complément Google pour les catégories faibles", "",
          "| Catégorie | Recherche | Résultats (7 jours) | Exemples |", "|---|---|---|---|"]
    for g in google:
        L.append(f"| {g['cat']} | {esc(g['query'])} | {g['count']} | {esc(' ◆ '.join(g['examples']))} |")

    L += ["", "## D. Payant / gratuit, média par média", "",
          "| Média | Résultats (2 articles max) |", "|---|---|"]
    for m, vs in paywall.items():
        if vs:
            L.append(f"| {m} | {esc(', '.join(vs))} |")

    L += ["", "## A. Flux RSS des médias", "", "| Média | Statut | Flux | Comment | Articles |", "|---|---|---|---|---|"]
    for f in feeds:
        L.append(f"| {f['media']} | {'Favori' if f['statut'] == 'F' else 'Neutre'} | "
                 f"{esc('<br>'.join(f['feeds']) or '—')} | {f['how']} | {f['count']} |")
    text = "\n".join(L) + "\n"

    print(text)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write(text)
    with open("resultats-essai.json", "w", encoding="utf-8") as fh:
        json.dump({"flux": feeds, "couverture": coverage, "exemples": examples,
                   "google": google, "payant": paywall}, fh, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
