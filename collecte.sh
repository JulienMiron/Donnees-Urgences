#!/bin/bash
# Collecte horaire des urgences (Mac) : relevé du MSSS, données du site, envoi sur GitHub.
cd "$(dirname "$0")" || exit 1

# Cherche un Python qui a pandas et requests (utilisable aussi depuis cron, qui a un PATH minimal)
PY=""
for p in /opt/homebrew/bin/python3 /usr/local/bin/python3 \
         /Library/Frameworks/Python.framework/Versions/*/bin/python3 \
         /usr/bin/python3 "$(command -v python3)"; do
  if [ -x "$p" ] && "$p" -c "import pandas, requests" 2>/dev/null; then PY="$p"; break; fi
done
if [ -z "$PY" ]; then
  echo "Aucun Python avec pandas et requests trouvé. Installez-les : python3 -m pip install pandas requests"
  exit 1
fi

# --autostash : le fichier .DS_Store (suivi par Git) change souvent et bloquerait le pull
git pull --rebase --autostash --quiet

$PY collecter_urgences.py || exit 1

# Coordonnées des hôpitaux : téléchargées une seule fois (n'empêche pas la suite si ça échoue)
[ -f data/installations.csv ] || $PY coordonnees.py || echo "Coordonnées non chargées, on réessaiera."

$PY construire_site.py

git add data/ docs/data/
git diff --staged --quiet || { git commit -m "Relevé urgences $(date '+%Y-%m-%d %H:%M')"; git push --quiet; }
