#!/usr/bin/env python3
"""
Télécharge les coordonnées des installations du réseau de la santé (fichier M02).

Source : Données Québec, « Fichiers cartographiques M02 des installations et
établissements » (MSSS). Le champ INSTAL_COD correspond au numéro de permis
(« No_permis_installation ») du relevé horaire des urgences.

Écrit data/installations.csv (permis, nom, municipalité, latitude, longitude).
À relancer rarement : les emplacements des hôpitaux changent peu.
"""
import io
from pathlib import Path

import pandas as pd
import requests

URL = ("https://www.donneesquebec.ca/recherche/dataset/"
       "51998b55-7d4c-4381-8c20-0ac1cd9c1b87/resource/"
       "2aa06e66-c1d0-4e2f-bf3c-c2e413c3f84d/download/installationscsv.csv")
SORTIE = Path("data/installations.csv")
ENTETES = {"User-Agent": "collecte de donnees ouvertes "
                         "(+https://github.com/JulienMiron/Donnees-Urgences)"}


def decoder(brut: bytes) -> str:
    for encodage in ("utf-8-sig", "cp1252"):
        try:
            return brut.decode(encodage)
        except UnicodeDecodeError:
            continue
    raise ValueError("Encodage du fichier M02 non reconnu")


def main() -> None:
    r = requests.get(URL, headers=ENTETES, timeout=120)
    r.raise_for_status()
    df = pd.read_csv(io.StringIO(decoder(r.content)), dtype=str,
                     keep_default_na=False)
    df.columns = [c.strip() for c in df.columns]

    manquantes = {"INSTAL_COD", "INSTAL_NOM", "MUN_NOM", "LATITUDE", "LONGITUDE"} \
        - set(df.columns)
    if manquantes:
        raise SystemExit(f"Colonnes absentes du fichier M02 : {sorted(manquantes)}")

    out = pd.DataFrame({
        "permis": df["INSTAL_COD"].str.strip(),
        "nom": df["INSTAL_NOM"].str.strip(),
        "municipalite": df["MUN_NOM"].str.strip(),
        "latitude": pd.to_numeric(df["LATITUDE"], errors="coerce"),
        "longitude": pd.to_numeric(df["LONGITUDE"], errors="coerce"),
    })
    # On garde seulement des coordonnées plausibles pour le Québec
    ok = out["latitude"].between(44, 63) & out["longitude"].between(-80, -57)
    out = out[ok].drop_duplicates(subset="permis")

    SORTIE.parent.mkdir(exist_ok=True)
    out.to_csv(SORTIE, index=False, encoding="utf-8")
    print(f"{SORTIE} : {len(out)} installations avec coordonnées")


if __name__ == "__main__":
    main()
