#!/usr/bin/env python3
"""Flow Actu — faut-il lancer une mise à jour maintenant ?

GitHub lance ce script toutes les 15 minutes pendant les créneaux (8 h, 14 h, 20 h, heure de Paris).
Il lit seulement la date de la dernière mise à jour sur le site Flow Actu (aucune visite chez Google
ni chez les médias) et répond :
  - oui : premier lancement réussi du créneau → le robot fait la mise à jour ;
  - non : hors créneau, ou créneau déjà fait → tout s'arrête en quelques secondes.
Lancement manuel (« Run workflow ») ou modification du dépôt : toujours oui.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import flow_actu as R  # noqa: E402


def main():
    cfg = R.load_config()
    event = os.environ.get("EVENEMENT", "workflow_dispatch")
    last = None
    if event == "schedule":
        data, _ = R.previous_data(R.Net(cfg["site"]["depot"]))
        last = data.get("genere")
    ok, why = R.should_run(event, R.NOW, cfg["site"]["creneaux"], last)
    print(("✅ " if ok else "⏭️ ") + why)
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write(f"lancer={'true' if ok else 'false'}\n")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary and not ok:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(f"⏭️ Pas de mise à jour : {why}.\n")


if __name__ == "__main__":
    main()
