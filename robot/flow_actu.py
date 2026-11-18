#!/usr/bin/env python3
"""Flow Actu — le robot.

Toutes les 3 heures (GitHub Actions), il :
  1. lit les flux RSS des médias favoris et neutres (config/medias.json + config/medias-ajoutes/) ;
  2. complète avec Google Actualités pour les catégories mal couvertes et les médias sans flux ;
  3. range chaque article dans ses catégories, d'après son titre (config/categories.json) ;
  4. fusionne avec les articles du passage précédent (pas de date de péremption, 30 max par catégorie) ;
  5. regroupe les articles qui parlent du même sujet ;
  6. vérifie si les nouveaux articles sont payants ;
  7. écrit data/news.json, lu par la page.

Bibliothèque standard Python uniquement. Cahier des charges : claude/flow-actu-cahier-des-charges.md (v8).
"""
import base64
import email.utils
import glob
import hashlib
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from html import unescape

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA = "Mozilla/5.0 (compatible; FlowActu/1.0; +https://github.com/{depot})"
PAUSE = 1.0
PAUSE_GOOGLE = 1.5
NOW = datetime.now(timezone.utc)


# ====================================================================== outils texte
def norm(s):
    """minuscules, sans accents, apostrophes droites, espaces simples."""
    s = (s or "").replace("’", "'").replace("«", " ").replace("»", " ").lower()
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    return re.sub(r"\s+", " ", s).strip()


def has_phrase(text, phrase):
    return re.search(r"(?<![\w])" + re.escape(phrase) + r"(?![\w])", text) is not None


def strip_tags(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", unescape(s or ""))).strip()


def article_id(title):
    key = re.sub(r"[^\w]+", " ", norm(title)).strip()
    return hashlib.sha1(key.encode()).hexdigest()[:12]


# ====================================================================== configuration
def load_config(root=ROOT):
    def rd(p):
        with open(os.path.join(root, p), encoding="utf-8") as f:
            return json.load(f)
    cfg = {"site": rd("config/site.json"), "cats": rd("config/categories.json")["categories"],
           "medias": rd("config/medias.json")["medias"], "ajouts": []}
    for path in sorted(glob.glob(os.path.join(root, "config/medias-ajoutes/*.json"))):
        try:
            with open(path, encoding="utf-8") as f:
                a = json.load(f)
            host = urllib.parse.urlparse(a["site"] if "://" in a["site"] else "https://" + a["site"]).netloc
            host = host.lower().removeprefix("www.")
            cfg["ajouts"].append({"id": "ajout-" + re.sub(r"[^a-z0-9]+", "-", host), "nom": a.get("nom") or host,
                                  "domaines": [host], "statut": a.get("statut", "neutre"), "familles": ["*"],
                                  "accueil": a["site"] if "://" in a["site"] else "https://" + a["site"], "flux": []})
        except Exception as e:  # fichier mal rempli : signalé, pas bloquant
            print(f"  ! média ajouté illisible {os.path.basename(path)} : {e}", file=sys.stderr)
    return cfg


def all_medias(cfg):
    return cfg["medias"] + cfg["ajouts"]


def media_for_url(url, medias):
    """Média correspondant à une adresse (correspondance la plus précise : domaine + chemin)."""
    p = urllib.parse.urlparse(url or "")
    host = p.netloc.lower().removeprefix("www.")
    full = host + p.path
    best, best_len = None, -1
    for m in medias:
        for d in m["domaines"]:
            d = d.lower()
            dhost, _, dpath = d.partition("/")
            if not (host == dhost or host.endswith("." + dhost)):
                continue
            if dpath and not p.path.lstrip("/").startswith(dpath):
                continue
            if len(d) > best_len:
                best, best_len = m, len(d)
    return best


# ====================================================================== rangement
def _rule_ok(text, rule, specialist):
    if rule.startswith("spe:"):
        if not specialist:
            return False
        rule = rule[4:]
    if rule.startswith("re:"):
        return re.search(rule[3:], text) is not None
    return all(has_phrase(text, norm(part)) for part in rule.split("+"))


def classify(title, media, cats):
    """Catégories d'un titre. media = entrée de config ou None (source inconnue, via Google)."""
    text = norm(title)
    fams = media["familles"] if media else ["*?"]
    generalist = "*" in fams or "*?" in fams
    pure_generalist = fams == ["*"]
    primary = fams[0] if fams[0] not in ("*", "*?") else None
    hits = []
    for c in cats:
        f = c["famille"]
        if not (generalist or f in fams):
            continue
        if any(has_phrase(text, norm(x)) for x in c["exclure"]):
            continue
        if c["tout_generalistes"] and pure_generalist:
            hits.append(c["id"])
            continue
        if c["tout_specialistes"] and primary == f:
            hits.append(c["id"])
            continue
        if any(_rule_ok(text, r, primary == f) for r in c["mots"]):
            hits.append(c["id"])
    if media and media.get("fine_defaut") and media["fine_defaut"] not in hits:
        hits.append(media["fine_defaut"])
    return hits


# ====================================================================== réseau
class Net:
    """Accès réseau, remplaçable dans les tests."""

    def __init__(self, depot):
        self.ua = UA.format(depot=depot)

    def get(self, url, data=None, headers=None, timeout=20):
        h = {"User-Agent": self.ua, "Accept-Language": "fr-FR,fr;q=0.9"}
        h.update(headers or {})
        req = urllib.request.Request(url, data=data, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read(3_000_000)
                return r.status, raw.decode(r.headers.get_content_charset() or "utf-8", "replace"), r.geturl()
        except urllib.error.HTTPError as e:
            return e.code, "", url
        except Exception as e:
            return 0, f"{type(e).__name__}: {e}", url


# ====================================================================== flux RSS
def _local(tag):
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def parse_date(s):
    if not s:
        return None
    try:
        d = email.utils.parsedate_to_datetime(s)
    except (TypeError, ValueError, IndexError):
        try:
            d = datetime.fromisoformat(s.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return min(d.astimezone(timezone.utc), NOW)


def parse_feed(text):
    """Flux RSS 2.0, RSS 1.0 (RDF) ou Atom ; repli tolérant si le XML est invalide."""
    items = []
    try:
        root = ET.fromstring(text.encode("utf-8", "replace"))
        for el in root.iter():
            if _local(el.tag) not in ("item", "entry"):
                continue
            it = {"title": "", "link": "", "date": "", "source": "", "source_url": ""}
            for ch in el:
                n = _local(ch.tag)
                if n == "title":
                    it["title"] = strip_tags("".join(ch.itertext()))
                elif n == "link":
                    it["link"] = (ch.get("href") or ch.text or "").strip() or it["link"]
                elif n in ("pubDate", "date", "updated", "published") and not it["date"]:
                    it["date"] = (ch.text or "").strip()
                elif n == "source":
                    it["source"] = (ch.text or "").strip()
                    it["source_url"] = ch.get("url", "")
            items.append(it)
        return items
    except ET.ParseError:
        pass
    for block in re.findall(r"<item\b.*?</item>", text, re.S | re.I):
        t = re.search(r"<title[^>]*>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", block, re.S | re.I)
        l = re.search(r"<link[^>]*>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</link>", block, re.S | re.I)
        d = re.search(r"<pubDate[^>]*>(.*?)</pubDate>", block, re.S | re.I)
        items.append({"title": strip_tags(t.group(1)) if t else "", "link": l.group(1).strip() if l else "",
                      "date": d.group(1).strip() if d else "", "source": "", "source_url": ""})
    return items


def looks_like_feed(text):
    return re.search(r"<(rss|feed|rdf:RDF)\b", text[:3000], re.I) is not None


def discover_feed(net, home):
    code, html, final = net.get(home)
    if code == 200:
        for tag in re.findall(r"<link\b[^>]*>", html, re.I):
            if re.search(r'rel=["\']?alternate', tag, re.I) and re.search(r'type=["\']application/(rss|atom)\+xml', tag, re.I):
                href = re.search(r'href=["\']([^"\']+)', tag, re.I)
                if href:
                    return urllib.parse.urljoin(final, unescape(href.group(1))), None
    for path in ("rss", "feed", "rss.xml", "feed.xml", "index.rss"):
        url = urllib.parse.urljoin(home if home.endswith("/") else home + "/", path)
        c, text, _ = net.get(url)
        if c == 200 and looks_like_feed(text):
            return url, None
    return None, f"flux introuvable (accueil HTTP {code})"


# ====================================================================== Google Actualités
def google_query(cat):
    simple = [r for r in cat["mots"] if not r.startswith(("spe:", "re:")) and "+" not in r]
    words = simple[:4]
    if not words:
        plus = [r for r in cat["mots"] if "+" in r and not r.startswith(("spe:", "re:"))]
        return plus[0].replace("+", " ") if plus else ""
    return " OR ".join(f'"{w}"' if " " in w else w for w in words)


def google_search(net, query, site_cfg):
    q = urllib.parse.urlencode({"q": f"{query} {site_cfg['fraicheur']}", "hl": "fr", "gl": "FR", "ceid": "FR:fr"})
    code, text, _ = net.get(f"https://news.google.com/rss/search?{q}")
    if code != 200 or not looks_like_feed(text):
        return None, code
    out = []
    for it in parse_feed(text)[: site_cfg["resultats_par_recherche"]]:
        title = it["title"]
        if it["source"] and title.endswith(" - " + it["source"]):
            title = title[: -(len(it["source"]) + 3)]
        it["title"] = title.strip()
        out.append(it)
    return out, code


def is_institutional_or_service(source, source_url, title, site_cfg):
    s = norm(source)
    host = urllib.parse.urlparse(source_url or "").netloc.lower()
    if any(s.startswith(w) for w in site_cfg["sites_institutionnels"]):
        return True
    if host.endswith(".gouv.fr") or re.match(r"^(www\.)?(ville|mairie|region|departement|agglo)[-.]", host):
        return True
    t = norm(title)
    return any(p in t for p in site_cfg["titres_de_service"])


def gnews_id(url):
    m = re.search(r"/articles/([^?/#]+)", url)
    return m.group(1) if m else None


def decode_google_link(net, link):
    """Adresse réelle d'un lien Google Actualités (méthode non officielle, vérifiée aux essais 1 et 2)."""
    aid = gnews_id(link)
    if not aid:
        return None
    try:
        raw = base64.urlsafe_b64decode(aid + "=" * (-len(aid) % 4))
        m = re.search(rb"https?://[\x21-\x7e]+", raw)
        if m and b"news.google" not in m.group(0):
            return m.group(0).decode("ascii", "replace")
    except Exception:
        pass
    code, html, _ = net.get(f"https://news.google.com/articles/{aid}")
    if code != 200:
        code, html, _ = net.get(f"https://news.google.com/rss/articles/{aid}")
    sg = re.search(r'data-n-a-sg="([^"]+)"', html)
    ts = re.search(r'data-n-a-ts="([^"]+)"', html)
    if not (sg and ts):
        return None
    inner = ('["garturlreq",[["X","X",["X","X"],null,null,1,1,"US:en",null,1,null,null,'
             'null,null,null,0,1],"X","X",1,[1,1,1],1,1,null,0,0,null,0],'
             f'"{aid}",{ts.group(1)},"{sg.group(1)}"]')
    body = "f.req=" + urllib.parse.quote(json.dumps([[["Fbv4je", inner]]]))
    code, text, _ = net.get("https://news.google.com/_/DotsSplashUi/data/batchexecute", data=body.encode(),
                            headers={"Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"})
    if code != 200:
        return None
    try:
        parsed = json.loads(text.split("\n\n")[1])[:-2]
        return json.loads(parsed[0][2])[1]
    except Exception:
        m = re.search(r'https?://(?!(?:[a-z]+\.)?google)[^"\\\s]+', text)
        return m.group(0) if m else None


# ====================================================================== payant / gratuit
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
    """'payant', 'gratuit', 'compteur' ou None (rien de déclaré)."""
    flags = []
    for block in re.findall(r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html, re.S | re.I):
        try:
            data = json.loads(unescape(block.strip()))
        except Exception:
            continue
        flags += [b for b in (_as_bool(v) for v in _walk(data, "isAccessibleForFree")) if b is not None]
    tier = re.search(r'<meta[^>]+property=["\']article:content_tier["\'][^>]+content=["\']([^"\']+)', html, re.I) \
        or re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']article:content_tier', html, re.I)
    tier = tier.group(1).lower() if tier else None
    if False in flags or tier == "locked":
        return "payant"
    if tier == "metered":
        return "compteur"
    if True in flags or tier == "free":
        return "gratuit"
    return None


# ====================================================================== regroupement par sujet
STOP = set("""alors apres aussi autre avant avec avoir cela cette ceux chez comme comment dans depuis deux dont elle elles encore
entre etre fait faut leur leurs mais meme moins nous notre pour plus pourquoi quand quel quelle quels sans selon sera sont sous
suite tout tous toute toutes tres vers voici voila votre vous apres contre premier premiere dernier derniere direct video photos
quoi faire veut peut doit selon ainsi avoir etait""".split())


def sig_words(title):
    return {w for w in re.findall(r"[a-z0-9]+", norm(title)) if (len(w) >= 4 or w.isdigit() and len(w) == 4) and w not in STOP}


def group_articles(articles, min_common=3, min_overlap=0.4, window_h=48):
    """Regroupe les articles du même sujet (mots importants communs). Renvoie {id: id_du_groupe}."""
    words = {a["id"]: sig_words(a["t"]) for a in articles}
    dates = {a["id"]: a["d"] for a in articles}
    parent = {a["id"]: a["id"] for a in articles}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    index = {}
    for a in articles:
        for w in words[a["id"]]:
            index.setdefault(w, []).append(a["id"])
    for a in articles:
        cand = {}
        for w in words[a["id"]]:
            for o in index[w]:
                if o != a["id"]:
                    cand[o] = cand.get(o, 0) + 1
        for o, common in cand.items():
            if common < min_common or o < a["id"]:
                continue
            small = min(len(words[a["id"]]), len(words[o])) or 1
            if common / small < min_overlap:
                continue
            da, do = datetime.fromisoformat(dates[a["id"]]), datetime.fromisoformat(dates[o])
            if abs((da - do).total_seconds()) > window_h * 3600:
                continue
            parent[find(a["id"])] = find(o)
    groups = {}
    for a in articles:
        groups.setdefault(find(a["id"]), []).append(a["id"])
    out = {}
    for members in groups.values():
        if len(members) > 1:
            gid = min(members)
            for m in members:
                out[m] = gid
    return out


# ====================================================================== fusion et plafond
def cap_per_category(articles, max_n):
    by_cat = {}
    for a in articles:
        for c in a["c"]:
            by_cat.setdefault(c, []).append(a)
    keep = {}
    for c, lst in by_cat.items():
        lst.sort(key=lambda a: a["d"], reverse=True)
        for a in lst[:max_n]:
            keep.setdefault(a["id"], set()).add(c)
    out = []
    for a in articles:
        if a["id"] in keep:
            a["c"] = [c for c in a["c"] if c in keep[a["id"]]]
            out.append(a)
    return out


# ====================================================================== météo
def fetch_weather(net, m):
    url = "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode({
        "latitude": m["lat"], "longitude": m["lon"], "current": "temperature_2m,weather_code,wind_speed_10m",
        "daily": "temperature_2m_max,temperature_2m_min,weather_code", "timezone": "Europe/Paris", "forecast_days": 4})
    code, text, _ = net.get(url)
    if code != 200:
        return None
    try:
        d = json.loads(text)
        return {"ville": m["ville"], "actuel": d.get("current"), "jours": d.get("daily")}
    except ValueError:
        return None


# ====================================================================== passage complet
def previous_data(net):
    local = os.path.join(ROOT, "data/news.json")
    url = os.environ.get("FLOWACTU_PRECEDENT")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if not url and "/" in repo:
        owner, name = repo.split("/", 1)
        url = f"https://{owner.lower()}.github.io/{name}/data/news.json"
    if url:
        code, text, _ = net.get(url + "?t=" + str(int(time.time())))
        if code == 200:
            try:
                return json.loads(text), "site publié"
            except ValueError:
                pass
    if os.path.exists(local):
        with open(local, encoding="utf-8") as f:
            return json.load(f), "fichier local"
    return {"articles": []}, "aucune (premier passage)"


def run(net, cfg, sleep=time.sleep, out_path=None, write_summary=False):
    site = cfg["site"]
    cats = cfg["cats"]
    medias = all_medias(cfg)
    rapport = {"flux_ok": [], "flux_ko": [], "google": {"recherches": 0, "ok": 0, "bloque": False},
               "nouveaux": 0, "payant_verifies": 0, "decodes": 0}
    collected = []  # {t, u, m(id|None), s, d(datetime|None), v}

    # ---- 1. flux RSS
    for m in medias:
        if m["statut"] == "exclu":
            continue
        urls = list(m.get("flux", []))
        if not urls and m.get("accueil"):
            found, err = discover_feed(net, m["accueil"])
            if found:
                urls = [found]
            else:
                rapport["flux_ko"].append(f"{m['nom']} : {err}")
        n = 0
        for u in urls:
            code, text, _ = net.get(u)
            sleep(PAUSE)
            if code != 200 or not looks_like_feed(text):
                rapport["flux_ko"].append(f"{m['nom']} : HTTP {code} sur {u}")
                continue
            for it in parse_feed(text):
                if it["title"] and not re.fullmatch(r"[\W_]*", it["title"]):
                    collected.append({"t": it["title"], "u": it["link"], "m": m["id"], "s": m["nom"],
                                      "d": parse_date(it["date"]), "v": "rss"})
                    n += 1
        if n:
            rapport["flux_ok"].append(m["nom"])

    # ---- 2. Google Actualités
    rotation = max(1, site["google"]["rotation_non_cochees"])
    slot = (NOW.hour // 3) % rotation
    targets = []
    for i, c in enumerate([c for c in cats if c["google"]]):
        if c["defaut"] or i % rotation == slot:
            q = google_query(c)
            if q:
                targets.append(q)
    for m in medias:
        if m["statut"] != "exclu" and not m.get("flux") and m.get("domaines") and "/" not in m["domaines"][0]:
            targets.append(f"site:{m['domaines'][0]}")
    by_id = {m["id"]: m for m in medias}
    for q in targets:
        if rapport["google"]["bloque"]:
            break
        res, code = google_search(net, q, site["google"])
        rapport["google"]["recherches"] += 1
        sleep(PAUSE_GOOGLE)
        if res is None:
            if code in (429, 503, 403):
                rapport["google"]["bloque"] = True
            continue
        rapport["google"]["ok"] += 1
        for it in res:
            if not it["title"] or is_institutional_or_service(it["source"], it["source_url"], it["title"], site):
                continue
            media = media_for_url(it["source_url"], medias)
            collected.append({"t": it["title"], "u": it["link"], "m": media["id"] if media else None,
                              "s": media["nom"] if media else (it["source"] or "?"), "d": parse_date(it["date"]),
                              "v": "google", "su": it["source_url"]})

    # ---- 3. dédoublonnage du lot (même titre) : le flux direct l'emporte sur Google
    lot = {}
    for a in collected:
        aid = article_id(a["t"])
        if aid not in lot or (lot[aid]["v"] == "google" and a["v"] == "rss"):
            lot[aid] = dict(a, id=aid)

    # ---- 4. fusion avec le passage précédent
    prev, prev_src = previous_data(net)
    rapport["precedent"] = prev_src
    known = {a["id"]: a for a in prev.get("articles", [])}
    merged = {}
    for aid, a in known.items():
        merged[aid] = a
    for aid, a in lot.items():
        if aid in merged:
            continue
        rapport["nouveaux"] += 1
        merged[aid] = {"id": aid, "t": a["t"], "u": a["u"], "m": a["m"], "s": a["s"],
                       "d": (a["d"] or NOW).isoformat(timespec="seconds"), "v": a["v"], "p": None, "new": True}

    # ---- 5. décodage des nouveaux liens Google (BFM en priorité), puis exclusions
    gnew = [a for a in merged.values() if a.get("new") and a["v"] == "google" and "news.google.com" in (a["u"] or "")]
    gnew.sort(key=lambda a: 0 if (by_id.get(a["m"]) or {}).get("id") == "bfmtv" else 1)
    for a in gnew[: site["google"]["max_decodages_par_passage"]]:
        if rapport["google"]["bloque"]:
            break
        real = decode_google_link(net, a["u"])
        sleep(PAUSE)
        if real:
            rapport["decodes"] += 1
            a["u"] = real
            media = media_for_url(real, medias)
            if media:
                a["m"], a["s"] = media["id"], media["nom"]

    articles = []
    for a in merged.values():
        media = by_id.get(a["m"])
        if media and media["statut"] == "exclu":
            continue  # médias exclus par défaut : jamais conservés (BFMTV non décodé compris)
        a["c"] = classify(a["t"], media, cats)  # rangement refait à chaque passage (règles à jour)
        if a["c"]:
            articles.append(a)

    # ---- 6. plafond par catégorie
    articles = cap_per_category(articles, site["max_par_categorie"])

    # ---- 7. statut payant des nouveaux articles
    todo = [a for a in articles if a.get("new") and a["u"] and "news.google.com" not in a["u"]]
    for a in todo[: site["payant"]["max_verifications_par_passage"]]:
        code, html, _ = net.get(a["u"])
        sleep(PAUSE / 2)
        rapport["payant_verifies"] += 1
        if code == 200:
            a["p"] = detect_paywall(html)

    # ---- 8. regroupement par sujet
    groups = group_articles(articles)
    for a in articles:
        a.pop("new", None)
        a.pop("g", None)
        if a["id"] in groups:
            a["g"] = groups[a["id"]]

    articles.sort(key=lambda a: a["d"], reverse=True)
    data = {"titre": site["titre"], "genere": NOW.isoformat(timespec="seconds"),
            "meteo": fetch_weather(net, site["meteo"]), "articles": articles, "rapport": rapport}
    out_path = out_path or os.path.join(ROOT, "data/news.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    if write_summary:
        write_report(data, cats)
    return data


def write_report(data, cats):
    r = data["rapport"]
    counts = {}
    for a in data["articles"]:
        for c in a["c"]:
            counts[c] = counts.get(c, 0) + 1
    names = {c["id"]: c["nom"] for c in cats}
    L = ["# Flow Actu — rapport du robot", "",
         f"- Articles publiés : **{len(data['articles'])}** (nouveaux : {r['nouveaux']})",
         f"- Passage précédent : {r['precedent']}",
         f"- Flux lus : {len(r['flux_ok'])} médias",
         f"- Google : {r['google']['ok']}/{r['google']['recherches']} recherches"
         + (" — **Google a bloqué le robot, suite de Google ignorée**" if r["google"]["bloque"] else ""),
         f"- Liens Google décodés : {r['decodes']} · Pages vérifiées (payant) : {r['payant_verifies']}", ""]
    if r["flux_ko"]:
        L += ["## Flux en erreur", ""] + [f"- {x}" for x in r["flux_ko"]] + [""]
    L += ["## Articles par catégorie", "", "| Catégorie | Articles |", "|---|---|"]
    for cid, n in sorted(counts.items(), key=lambda kv: kv[1]):
        L.append(f"| {names.get(cid, cid)} | {n} |")
    text = "\n".join(L) + "\n"
    print(text)
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(text)


def main():
    cfg = load_config()
    data = run(Net(cfg["site"]["depot"]), cfg, write_summary=True)
    if not data["articles"]:
        print("Aucun article : publication annulée.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
