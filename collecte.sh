#!/bin/bash
# Collecte horaire des urgences (Mac) : relevé du MSSS, données du site, envoi sur GitHub.
cd "$(dirname "$0")" || exit 1
PY=/Library/Frameworks/Python.framework/Versions/3.13/bin/python3

# --autostash : le fichier .DS_Store (suivi par Git) change souvent et bloquerait le pull
git pull --rebase --autostash --quiet

$PY collecter_urgences.py || exit 1

# Coordonnées des hôpitaux : téléchargées une seule fois (n'empêche pas la suite si ça échoue)
[ -f data/installations.csv ] || $PY coordonnees.py || echo "Coordonnées non chargées, on réessaiera."

$PY construire_site.py

git add data/ docs/data/
git diff --staged --quiet || { git commit -m "Relevé urgences $(date '+%Y-%m-%d %H:%M')"; git push --quiet; }
