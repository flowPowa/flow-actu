# Médias ajoutés depuis la page

Ce dossier reçoit les médias ajoutés avec le bouton « Ajouter au robot » de la page (⚙️ Réglages → Médias).
Chaque média est un petit fichier `.json`, créé automatiquement :

```json
{"nom": "Exemple", "site": "https://www.exemple.fr", "statut": "favori"}
```

Au passage suivant (3 h maximum), le robot cherche tout seul le flux RSS du site.
S'il n'en trouve pas, il le signale dans son rapport (onglet Actions → dernière exécution → Summary).
Pour retirer un média : supprimez son fichier (icône poubelle sur GitHub).
