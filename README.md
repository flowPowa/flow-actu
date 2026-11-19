# 📰 Flow Actu

Ma page d'actualités personnelle, façon Google Actualités : https://flowpowa.github.io/flow-actu/

Le cahier des charges complet est dans le projet Claude « Perso » (`flow-actu-cahier-des-charges.md`).

## Comment ça marche

- Un **robot** (GitHub Actions) tourne trois fois par jour, vers 8 h, 14 h et 20 h (heure de Paris). Il lit les flux RSS des médias, complète avec Google Actualités, range les articles par catégorie, regroupe les articles qui parlent du même sujet, repère les articles payants et publie le tout.
- La **page** affiche les catégories que vous cochez, avec vos filtres. Vos réglages restent dans votre navigateur, jamais sur GitHub.

```
config/categories.json     ← les 108 catégories et leurs mots-clés
config/medias.json         ← les médias : favori / neutre / exclu, flux, étiquette gratuit/mixte/payant
config/mots-masques.json   ← les groupes de mots masqués (glauque, spoilers, pièges à clics)
config/site.json           ← réglages généraux (météo, nombre d'articles, Google…)
config/medias-ajoutes/     ← les médias ajoutés depuis la page (bouton « Ajouter au robot »)
robot/flow_actu.py         ← le robot
site/                      ← la page (index.html, app.js, logique.js, style.css)
tests/                     ← les tests automatiques (lancés avant chaque mise à jour)
.github/workflows/         ← la planification
```

## Mise en ligne (une seule fois, tout dans le navigateur)

1. **Supprimer l'essai technique** : dans le dépôt `flow-actu`, ouvrez `essai/essai_technique.py` → icône **poubelle** → **Commit changes**. Faites de même pour `.github/workflows/essai-technique.yml`.
2. **Déposer les fichiers** : page d'accueil du dépôt → **Add file → Upload files** → glissez **le contenu** du dossier `flow-actu-app` (les dossiers `.github`, `config`, `robot`, `site`, `tests` et le fichier `README.md`) → **Commit changes**.
3. **Activer la publication** : **Settings → Pages → Build and deployment → Source : « GitHub Actions »**.
4. **Premier lancement** : onglet **Actions** → **Flow Actu — mise à jour** (colonne de gauche) → bouton **Run workflow** → bouton vert. Comptez 10 à 15 minutes.
5. **C'est en ligne** : https://flowpowa.github.io/flow-actu/

Ensuite, le robot se relance tout seul vers 8 h, 14 h et 20 h. GitHub lance des essais toutes les 15 minutes autour de ces heures, car ses lancements programmés sont souvent retardés ou sautés ; un « portier » (`robot/creneau.py`) ne laisse passer que le premier essai de chaque créneau, les autres s'arrêtent en quelques secondes (ils apparaissent quand même dans l'onglet Actions, c'est normal). Le bouton « Run workflow » force une mise à jour à tout moment. Le premier passage ne contient que les articles du moment ; la page s'enrichit au fil des passages (le robot garde les articles précédents, dans la limite de 30 par catégorie).

## Utilisation

Tout se règle dans la page, bouton ⚙️ :
- **Catégories** : cocher / décocher, avec « Tout cocher » par famille.
- **Ordre des blocs** : flèches ↑ ↓.
- **Mots masqués** : activer / désactiver un groupe, ajouter « Mes mots ».
- **Médias** : ⭐ Favori / Neutre / ⛔ Exclu, et « Ajouter un site ».
- **Articles payants** : masquer les 🔒 (sauf favoris).
- **Mes données** : exporter vos réglages (fichier) puis les importer sur un autre appareil.

### Ajouter un nouveau média au robot
1. Dans la page : ⚙️ → Médias → **Ajouter un site** (ex. `exemple.fr`) → Favori ou Neutre → Ajouter.
2. Cliquez **Ajouter au robot** : GitHub s'ouvre avec un fichier déjà rempli → **Commit changes**.
3. Au passage suivant (créneau de 8 h, 14 h ou 20 h), le robot cherche tout seul le flux du site. S'il n'en trouve pas, il le signale dans son rapport.

### Voir le rapport du robot
Onglet **Actions** → dernière exécution → **Summary** : nombre d'articles, flux en erreur, état de Google, articles par catégorie.

### Modifier une catégorie ou ses mots-clés
Ouvrez `config/categories.json` sur GitHub → crayon ✏️ → modifiez → **Commit changes**. Le robot repart aussitôt (les mots-clés sont sans accents ni majuscules ; `spe:mot` = compte seulement pour les médias spécialisés ; `a+b` = les deux mots ; `exclure` = expressions qui annulent).

## Limites connues
Voir le § 9 du cahier des charges : flux Google non officiels, 14 médias sans flux lisible, rangement par mots-clés imparfait, statut payant approximatif pour les médias mixtes, réglages non synchronisés automatiquement, page publique.
