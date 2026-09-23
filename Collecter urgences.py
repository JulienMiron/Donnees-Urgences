#!/usr/bin/env python3
"""
Collecte du relevé horaire de la situation dans les urgences du Québec (MSSS).

Source : Données Québec, « Fichier horaire des données de la situation à l'urgence »
Licence : CC BY 4.0 — Ministère de la Santé et des Services sociaux (MSSS)

Chaque exécution télécharge le fichier, l'ajoute aux données déjà collectées
et retire les doublons (même installation, même heure d'extraction).
Les données sont rangées par mois : data/urgences_AAAA-MM.csv
"""
import io
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

URL = ("https://www.msss.gouv.qc.ca/professionnels/statistiques/documents/"
       "urgences/Releve_horaire_urgences_7jours_nbpers.csv")
DOSSIER = Path("data")
ENTETES = {
    # Identifiez-vous poliment ; remplacez l'adresse par celle de votre dépôt.
    "User-Agent": "Mozilla/5.0 (collecte de donnees ouvertes; "
                  "+https://github.com/VOTRE_COMPTE/urgences-qc)"
}
CLES = ["Nom_etablissement", "Nom_installation", "heure_extraction"]


def telecharger() -> pd.DataFrame:
    r = requests.get(URL, headers=ENTETES, timeout=60)
    r.raise_for_status()
    return lire_csv(r.content)


def lire_csv(brut: bytes) -> pd.DataFrame:
    """Décode le fichier (UTF-8 ou Windows-1252) et détecte le séparateur."""
    for encodage in ("utf-8-sig", "cp1252"):
        try:
            texte = brut.decode(encodage)
            break
        except UnicodeDecodeError:
            continue
    df = pd.read_csv(io.StringIO(texte), sep=None, engine="python", dtype=str)
    return normaliser(df)


def normaliser(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = [c.strip() for c in df.columns]
    # La colonne « Heure_de_l'extraction_(image) » a un nom peu pratique
    col = next((c for c in df.columns if "extraction" in c.lower()), None)
    if col is None:
        sys.exit(f"Colonne d'extraction introuvable : {list(df.columns)}")
    df = df.rename(columns={col: "heure_extraction"})
    for c in df.columns:
        df[c] = df[c].str.strip()
    df["collecte_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return df


def fusionner(nouveau: pd.DataFrame) -> None:
    DOSSIER.mkdir(exist_ok=True)
    dates = pd.to_datetime(nouveau["heure_extraction"], errors="coerce")
    mois = dates.dt.strftime("%Y-%m").fillna(
        datetime.now(timezone.utc).strftime("%Y-%m"))

    cles = [c for c in CLES if c in nouveau.columns]
    for m, bloc in nouveau.groupby(mois):
        fichier = DOSSIER / f"urgences_{m}.csv"
        if fichier.exists():
            ancien = pd.read_csv(fichier, dtype=str, keep_default_na=False)
            bloc = pd.concat([ancien, bloc], ignore_index=True)
        avant = len(bloc)
        bloc = (bloc.drop_duplicates(subset=cles, keep="last")
                    .sort_values(["heure_extraction", "Nom_installation"]))
        bloc.to_csv(fichier, index=False, encoding="utf-8")
        print(f"{fichier} : {len(bloc)} lignes ({avant - len(bloc)} doublons retirés)")


if __name__ == "__main__":
    fusionner(telecharger())