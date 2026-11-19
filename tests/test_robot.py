"""Tests du robot — critères d'acceptation du cahier des charges (v8).

Lancer : python3 -m unittest discover -s tests -v   (depuis la racine du dépôt)
Aucun accès réseau : un faux réseau renvoie des flux d'exemple (titres réels relevés aux essais).
"""
import json
import os
import sys
import tempfile
import unittest
from email.utils import format_datetime
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "robot"))
import flow_actu as R  # noqa: E402

CFG = R.load_config(ROOT)
CATS = CFG["cats"]
MED = {m["id"]: m for m in R.all_medias(CFG)}
GEN = MED["le-monde"]


def cats(title, media=GEN):
    return R.classify(title, media, CATS)


class Rangement(unittest.TestCase):
    def test_ca20_sonde_voyager_pas_en_voyage(self):
        self.assertNotIn("voyage", cats("La sonde Voyager 1 désormais à un jour-lumière de la Terre"))

    def test_voyage_reste_detecte(self):
        self.assertIn("voyage", cats("Vacances d’hiver : les Français à la recherche de bons plans"))

    def test_ca21_film_marvel_pas_en_bd(self):
        self.assertNotIn("bd-comics", cats("Avengers Doomsday : on connait la durée exacte du film Marvel", MED["ecran-large"]))

    def test_ca22_maison_ecole_pas_en_quotidien(self):
        self.assertNotIn("quotidien", cats("INFOGRAPHIES. De la maison à l’école, les élèves ruraux ont un temps de trajet"))

    def test_ca23_energies_fossiles_pas_en_paleontologie(self):
        self.assertNotIn("paleontologie", cats("Librairies, supérettes, énergies fossiles : Daniel Kretinsky", MED["challenges"]))

    def test_paleontologie_detectee(self):
        self.assertIn("paleontologie", cats("Dinosaures : des traces de sang fossilisées agitent la communauté", MED["sciences-et-avenir"]))

    def test_ca24_ciel_et_espace_en_astronomie(self):
        self.assertIn("astronomie", cats("Un titre sans mot-clé particulier", MED["ciel-et-espace"]))

    def test_jardin_seul_ne_suffit_plus(self):
        self.assertNotIn("jardinage", cats("MÉTÉO. Fortes rafales : des restrictions dans les jardins publics"))

    def test_gouvernement_etranger_pas_en_politique_france(self):
        self.assertNotIn("politique", cats("Les houthistes menacent Aden, capitale du gouvernement yéménite"))

    def test_politique_france_detectee(self):
        self.assertIn("politique", cats("Le Sénat favorable à une carence d’un an pour les allocations"))

    def test_chercheurs_seul_pas_en_sciences(self):
        self.assertNotIn("sciences", cats("Sans héritier, Nvidia face à l’après Jensen Huang : analystes et chercheurs", MED["lexpress"]))

    def test_generaliste_en_a_la_une(self):
        self.assertIn("a-la-une", cats("Un titre quelconque"))

    def test_specialiste_dans_sa_large(self):
        self.assertIn("pop", cats("Critique du film", MED["ecran-large"]))
        self.assertNotIn("a-la-une", cats("Critique du film", MED["ecran-large"]))

    def test_animé_n_est_pas_anime(self):
        self.assertNotIn("anime", cats("Un débat animé à l’Assemblée"))

    def test_source_google_inconnue_pas_en_a_la_une(self):
        self.assertNotIn("a-la-une", R.classify("Un titre quelconque", None, CATS))
        self.assertIn("serigraphie", R.classify("Théâtre, sérigraphie, conférences au programme", None, CATS))

    def test_dragon_quest_pas_dragon_ball(self):
        self.assertNotIn("dragon-ball", cats("Dragon Quest sans Akira Toriyama, ça a déjà trop duré", MED["gamekult"]))


class Medias(unittest.TestCase):
    def test_ca10_bfm_business_vs_bfmtv(self):
        ms = R.all_medias(CFG)
        self.assertEqual(R.media_for_url("https://www.bfmtv.com/economie/entreprises/x.html", ms)["id"], "bfm-business")
        self.assertEqual(R.media_for_url("https://www.bfmtv.com/politique/x.html", ms)["id"], "bfmtv")

    def test_sous_domaine(self):
        ms = R.all_medias(CFG)
        self.assertEqual(R.media_for_url("https://france3-regions.francetvinfo.fr/pays-de-la-loire/x", ms)["id"], "france-3-pdl")
        self.assertEqual(R.media_for_url("https://www.francetvinfo.fr/monde/x", ms)["id"], "franceinfo")
        self.assertEqual(R.media_for_url("https://investir.lesechos.fr/x", ms)["id"], "investir")

    def test_ca25_sites_institutionnels(self):
        s = CFG["site"]
        self.assertTrue(R.is_institutional_or_service("Ville de Lyon", "https://www.lyon.fr", "Direction de l’archéologie", s))
        self.assertTrue(R.is_institutional_or_service("Région Ile-de-France", "", "Les travaux dans les lycées", s))
        self.assertTrue(R.is_institutional_or_service("Boursorama", "", "Bourse en direct, Cours actions et dérivés", s))
        self.assertFalse(R.is_institutional_or_service("Le Journal Des Arts", "", "Ernest Pignon-Ernest retrouve Martigues", s))

    def test_requete_google(self):
        c = {x["id"]: x for x in CATS}
        self.assertEqual(R.google_query(c["serigraphie"]), "serigraphie OR serigraphe OR serigraphies")
        self.assertNotIn("indie", R.google_query(c["jeux-independants"]).split())


class Payant(unittest.TestCase):
    def test_detection(self):
        ld = lambda o: f'<script type="application/ld+json">{json.dumps(o)}</script>'
        self.assertEqual(R.detect_paywall(ld({"isAccessibleForFree": False})), "payant")
        self.assertEqual(R.detect_paywall(ld({"@graph": [{"isAccessibleForFree": "False"}]})), "payant")
        self.assertEqual(R.detect_paywall(ld({"isAccessibleForFree": "true"})), "gratuit")
        self.assertEqual(R.detect_paywall('<meta property="article:content_tier" content="metered">'), "compteur")
        self.assertIsNone(R.detect_paywall("<html></html>"))


class Regroupement(unittest.TestCase):
    def art(self, i, t, h=0):
        return {"id": f"a{i}", "t": t, "d": (datetime(2026, 11, 17, 12, tzinfo=timezone.utc) + timedelta(hours=h)).isoformat()}

    def test_budget_secu(self):
        arts = [self.art(1, "Au Sénat, le budget de la « Sécu » 2027 ramène le déficit à 14 milliards"),
                self.art(2, "Budget de la « Sécu » 2027 : le projet de texte adopté au Sénat en première lecture", 1),
                self.art(3, "Le Sénat adopte le projet de budget de la Sécurité sociale pour 2027", 2),
                self.art(4, "GTA 6 : voici les 55 trophées et succès à décrocher", 1)]
        g = R.group_articles(arts)
        self.assertEqual(g["a1"], g["a2"])
        self.assertEqual(g["a2"], g["a3"])
        self.assertNotIn("a4", g)

    def test_sujets_differents_non_regroupes(self):
        arts = [self.art(1, "Panne mondiale chez Apple : une mise à jour interne paralyse iCloud"),
                self.art(2, "Amazon Family arrive en France : partager Prime avec un adulte")]
        self.assertEqual(R.group_articles(arts), {})

    def test_trop_eloignes_dans_le_temps(self):
        arts = [self.art(1, "Budget de la Sécu 2027 adopté au Sénat en lecture"),
                self.art(2, "Budget de la Sécu 2027 adopté au Sénat en lecture définitive", 100)]
        self.assertEqual(R.group_articles(arts), {})


class Plafond(unittest.TestCase):
    def test_ca32_30_max(self):
        base = datetime(2026, 11, 1, tzinfo=timezone.utc)
        arts = [{"id": f"x{i}", "t": "t", "d": (base + timedelta(hours=i)).isoformat(), "c": ["chiens"]} for i in range(31)]
        out = R.cap_per_category(arts, 30)
        self.assertEqual(len(out), 30)
        self.assertNotIn("x0", {a["id"] for a in out})


# ---------------------------------------------------------------- passage complet avec faux réseau
def rss(items):
    body = "".join(f"<item><title>{t}</title><link>{l}</link><pubDate>{format_datetime(d)}</pubDate></item>" for t, l, d in items)
    return f'<?xml version="1.0"?><rss version="2.0"><channel>{body}</channel></rss>'


class FakeNet:
    def __init__(self, google_ok=True):
        self.google_ok = google_ok
        self.now = datetime.now(timezone.utc)

    def get(self, url, data=None, headers=None, timeout=20):
        n = self.now
        if "github.io" in url:
            return 404, "", url
        if "open-meteo" in url:
            return 200, json.dumps({"current": {"temperature_2m": 11, "weather_code": 3, "wind_speed_10m": 20},
                                    "daily": {"time": ["2026-11-18"], "weather_code": [3], "temperature_2m_max": [12], "temperature_2m_min": [6]}}), url
        if "news.google.com/rss/search" in url:
            if not self.google_ok:
                return 503, "", url
            return 200, ('<?xml version="1.0"?><rss><channel>'
                         f'<item><title>Direction de l’archéologie - Ville de Lyon</title><link>https://news.google.com/rss/articles/AAA</link><pubDate>{format_datetime(n)}</pubDate><source url="https://www.lyon.fr">Ville de Lyon</source></item>'
                         f'<item><title>Une sérigraphie géante à Lyon - Le Progrès</title><link>https://news.google.com/rss/articles/BBB</link><pubDate>{format_datetime(n)}</pubDate><source url="https://www.leprogres.fr">Le Progrès</source></item>'
                         f'<item><title>Info BFMTV : un fait politique - BFMTV</title><link>https://news.google.com/rss/articles/CCC</link><pubDate>{format_datetime(n)}</pubDate><source url="https://www.bfmtv.com">BFMTV</source></item>'
                         '</channel></rss>'), url
        if "news.google.com" in url:
            return 404, "", url
        if url == "https://www.lemonde.fr/rss/une.xml":
            return 200, rss([("Au Sénat, le budget de la « Sécu » 2027 ramène le déficit à 14 milliards", "https://www.lemonde.fr/a.html", n),
                             ("La sonde Voyager 1 désormais à un jour-lumière de la Terre", "https://www.lemonde.fr/b.html", n),
                             ("", "https://www.lemonde.fr/vide.html", n)]), url
        if url == "https://www.lefigaro.fr/rss/figaro_actualites.xml":
            return 200, rss([("Le Sénat adopte le projet de budget de la Sécurité sociale pour 2027", "https://www.lefigaro.fr/a.html", n),
                             ("Au Sénat, le budget de la « Sécu » 2027 ramène le déficit à 14 milliards", "https://www.lefigaro.fr/doublon.html", n)]), url
        if url == "https://www.cieletespace.fr/rss.xml":
            return 200, rss([("Les Léonides culminent cette nuit", "https://www.cieletespace.fr/a.html", n)]), url
        if url.endswith(".html"):
            if "lemonde" in url:
                return 200, "<html></html>", url
            return 200, '<script type="application/ld+json">{"isAccessibleForFree": false}</script>', url
        if "ouest-france" in url:
            return 403, "", url
        return 404, "", url


class PassageComplet(unittest.TestCase):
    def run_robot(self, google_ok=True):
        tmp = tempfile.mkdtemp()
        return R.run(FakeNet(google_ok), CFG, sleep=lambda s: None, out_path=os.path.join(tmp, "news.json"))

    def test_passage(self):
        data = self.run_robot()
        titles = [a["t"] for a in data["articles"]]
        by_t = {a["t"]: a for a in data["articles"]}
        # CA26 : même titre, liens différents → un seul
        self.assertEqual(titles.count("Au Sénat, le budget de la « Sécu » 2027 ramène le déficit à 14 milliards"), 1)
        # CA36 : sans titre ignoré
        self.assertNotIn("", titles)
        # CA25 : mairie écartée ; source inconnue gardée si catégorie trouvée
        self.assertNotIn("Direction de l’archéologie", titles)
        self.assertIn("serigraphie", by_t["Une sérigraphie géante à Lyon"]["c"])
        # BFMTV via Google, non décodé → exclu
        self.assertFalse(any("BFMTV" in t for t in titles))
        # CA24 : Ciel et Espace → Astronomie
        self.assertIn("astronomie", by_t["Les Léonides culminent cette nuit"]["c"])
        # CA20
        self.assertNotIn("voyage", by_t["La sonde Voyager 1 désormais à un jour-lumière de la Terre"]["c"])
        # regroupement Sécu (Le Monde + Le Figaro)
        g1 = by_t["Au Sénat, le budget de la « Sécu » 2027 ramène le déficit à 14 milliards"].get("g")
        g2 = by_t["Le Sénat adopte le projet de budget de la Sécurité sociale pour 2027"].get("g")
        self.assertIsNotNone(g1)
        self.assertEqual(g1, g2)
        # payant détecté
        self.assertEqual(by_t["Le Sénat adopte le projet de budget de la Sécurité sociale pour 2027"]["p"], "payant")
        # CA35 : erreur 403 signalée, le reste traité
        self.assertTrue(any("Ouest-France" in x and "403" in x for x in data["rapport"]["flux_ko"]))
        self.assertIsNotNone(data["meteo"])

    def test_ca34_google_bloque(self):
        data = self.run_robot(google_ok=False)
        self.assertTrue(data["rapport"]["google"]["bloque"])
        self.assertEqual(data["rapport"]["google"]["recherches"], 1)  # arrêt dès le premier blocage
        self.assertTrue(any(a["s"] == "Le Monde" for a in data["articles"]))

    def test_ca31_memoire(self):
        tmp = tempfile.mkdtemp()
        old = {"articles": [{"id": "ancien1", "t": "Un chiot adopté par une caserne", "u": "https://x.fr/a", "m": None,
                             "s": "X", "d": "2026-11-01T10:00:00+00:00", "v": "google", "p": None, "c": ["chiens"]}]}
        os.makedirs(os.path.join(tmp, "data"))
        prev_path = os.path.join(tmp, "prev.json")
        with open(prev_path, "w") as f:
            json.dump(old, f)

        class N(FakeNet):
            def get(self, url, *a, **k):
                if url.startswith("file://prev"):
                    with open(prev_path) as f:
                        return 200, f.read(), url
                return super().get(url, *a, **k)
        os.environ["FLOWACTU_PRECEDENT"] = "file://prev"
        try:
            data = R.run(N(), CFG, sleep=lambda s: None, out_path=os.path.join(tmp, "news.json"))
        finally:
            del os.environ["FLOWACTU_PRECEDENT"]
        self.assertIn("Un chiot adopté par une caserne", [a["t"] for a in data["articles"]])


if __name__ == "__main__":
    unittest.main()


# ---------------------------------------------------------------- correctifs du 19/11
class Diversite(unittest.TestCase):
    def test_3_par_media_max(self):
        base = datetime(2026, 11, 19, tzinfo=timezone.utc)
        arts = [{"id": f"p{i}", "t": "t", "m": "le-parisien", "d": (base + timedelta(minutes=100 + i)).isoformat(), "c": ["a-la-une"]} for i in range(40)]
        arts += [{"id": f"o{i}", "t": "t", "m": f"autre{i}", "d": (base + timedelta(minutes=i)).isoformat(), "c": ["a-la-une"]} for i in range(10)]
        out = R.cap_per_category(arts, 30, 3)
        self.assertEqual(len(out), 30)
        self.assertEqual(sum(1 for a in out if a["m"].startswith("autre")), 10)
        # 10 autres médias gardés ; le Parisien complète les places restantes (20) faute d'autres sources
        self.assertEqual(sum(1 for a in out if a["m"] == "le-parisien"), 20)

    def test_le_parisien_ne_monopolise_plus(self):
        base = datetime(2026, 11, 19, tzinfo=timezone.utc)
        arts = [{"id": f"p{i}", "t": "t", "m": "le-parisien", "d": (base + timedelta(minutes=100 + i)).isoformat(), "c": ["a-la-une"]} for i in range(40)]
        arts += [{"id": f"o{i}", "t": "t", "m": f"autre{i % 15}", "d": (base + timedelta(minutes=i)).isoformat(), "c": ["a-la-une"]} for i in range(45)]
        out = R.cap_per_category(arts, 30, 3)
        self.assertEqual(sum(1 for a in out if a["m"] == "le-parisien"), 3)


class Creneaux(unittest.TestCase):
    C = {"heures_paris": [8, 14, 20], "fenetre_heures": 2}
    U = lambda self, s: datetime.fromisoformat(s)

    def test_hors_creneau(self):
        self.assertFalse(R.should_run("schedule", self.U("2026-11-19T10:30:00+00:00"), self.C, None)[0])  # 11 h 30 Paris

    def test_premier_passage_du_creneau(self):
        ok, why = R.should_run("schedule", self.U("2026-11-19T07:15:00+00:00"), self.C, "2026-11-18T19:05:00+00:00")
        self.assertTrue(ok, why)  # 8 h 15 Paris, dernière mise à jour hier 20 h 05

    def test_creneau_deja_fait(self):
        self.assertFalse(R.should_run("schedule", self.U("2026-11-19T07:45:00+00:00"), self.C, "2026-11-19T07:15:00+00:00")[0])

    def test_heure_d_ete(self):
        self.assertTrue(R.should_run("schedule", self.U("2026-07-01T06:10:00+00:00"), self.C, "2026-06-30T18:30:00+00:00")[0])  # 8 h 10 Paris (été)
        self.assertFalse(R.should_run("schedule", self.U("2026-07-01T05:50:00+00:00"), self.C, None)[0])  # 7 h 50 Paris

    def test_lancement_manuel_toujours(self):
        self.assertTrue(R.should_run("workflow_dispatch", self.U("2026-11-19T03:00:00+00:00"), self.C, "2026-11-19T02:59:00+00:00")[0])
        self.assertTrue(R.should_run("push", self.U("2026-11-19T03:00:00+00:00"), self.C, None)[0])

    def test_repartition_google(self):
        self.assertEqual(R.slot_index(self.U("2026-11-19T07:15:00+00:00"), self.C), 0)
        self.assertEqual(R.slot_index(self.U("2026-11-19T13:15:00+00:00"), self.C), 1)
        self.assertEqual(R.slot_index(self.U("2026-11-19T19:15:00+00:00"), self.C), 2)
