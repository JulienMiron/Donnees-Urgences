#!/usr/bin/env python3
"""
Construit les fichiers de données du site (docs/data/*.json) à partir des
relevés horaires archivés dans data/urgences_AAAA-MM.csv.

  actuel.json      dernière situation connue : Québec, régions, installations
  historique.json  7 derniers jours, heure par heure : Québec et régions
  profil.json      occupation moyenne par jour de semaine et par heure (Québec)

Les coordonnées viennent de data/installations.csv (voir coordonnees.py).
"""
import json
import re
from pathlib import Path

import pandas as pd

DATA = Path("data")
SORTIE = Path("docs/data")
QUEBEC = "Ensemble du Québec"
REGIONAL = "Total régional"
JOURS_HISTORIQUE = 7

COLONNES = {
    "civieres": "Nombre_de_civieres_fonctionnelles",
    "occupees": "Nombre_de_civieres_occupees",
    "plus24": "Nombre_de_patients_sur_civiere_plus_de_24_heures",
    "plus48": "Nombre_de_patients_sur_civiere_plus_de_48_heures",
    "presents": "Nombre_total_de_patients_presents_a_lurgence",
    "attente": "Nombre_total_de_patients_en_attente_de_PEC",
    "dms_civiere": "DMS_sur_civiere",
}


def nombre(serie: pd.Series) -> pd.Series:
    return pd.to_numeric(serie.str.replace(",", ".", regex=False), errors="coerce")


def charger() -> pd.DataFrame:
    fichiers = sorted(DATA.glob("urgences_*.csv"))
    if not fichiers:
        raise SystemExit("Aucun fichier data/urgences_*.csv")
    brut = pd.concat([pd.read_csv(f, dtype=str, keep_default_na=False)
                      for f in fichiers], ignore_index=True)
    manquantes = [c for c in COLONNES.values() if c not in brut.columns]
    if manquantes:
        raise SystemExit(f"Colonnes absentes : {manquantes}")

    df = pd.DataFrame({
        "t": pd.to_datetime(brut["horodatage"], errors="coerce"),
        "rss": brut["RSS"],
        "region": brut["Region"],
        "etablissement": brut["Nom_etablissement"],
        "installation": brut["Nom_installation"],
        "permis": brut["No_permis_installation"].str.strip(),
    })
    for court, long in COLONNES.items():
        df[court] = nombre(brut[long])
    df = df.dropna(subset=["t"]).drop_duplicates(
        subset=["t", "rss", "installation", "permis"], keep="last")
    df["taux"] = (df["occupees"] / df["civieres"] * 100).where(df["civieres"] > 0)
    return df


def valeur(x):
    """Convertit en type JSON (NaN -> null, entiers sans décimale)."""
    if pd.isna(x):
        return None
    return int(x) if float(x).is_integer() else round(float(x), 1)


def ligne(r: pd.Series, champs: list[str]) -> dict:
    return {c: valeur(r[c]) for c in champs}


def coordonnees() -> pd.DataFrame | None:
    f = DATA / "installations.csv"
    if not f.exists():
        print("Avertissement : data/installations.csv absent, aucune coordonnée.")
        return None
    return pd.read_csv(f, dtype={"permis": str}).set_index("permis")


def main() -> None:
    df = charger()
    SORTIE.mkdir(parents=True, exist_ok=True)

    qc = df[df["installation"] == QUEBEC].sort_values("t")
    reg = df[df["installation"] == REGIONAL]
    inst = df[~df["installation"].isin([QUEBEC, REGIONAL]) & (df["civieres"] > 0)]
    if qc.empty:
        raise SystemExit("Aucune ligne « Ensemble du Québec » dans les données")

    derniere = qc["t"].max()

    # ---- actuel.json -------------------------------------------------------
    coords = coordonnees()
    champs = ["civieres", "occupees", "taux", "plus24", "plus48", "presents",
              "attente", "dms_civiere"]
    liste = []
    sans_coord = 0
    for _, r in inst[inst["t"] == derniere].iterrows():
        d = {"nom": r["installation"], "etablissement": r["etablissement"],
             "region": r["region"], "rss": r["rss"], **ligne(r, champs),
             "lat": None, "lon": None, "municipalite": None}
        if coords is not None and r["permis"] in coords.index:
            c = coords.loc[r["permis"]]
            d.update(lat=round(float(c["latitude"]), 5),
                     lon=round(float(c["longitude"]), 5),
                     municipalite=c["municipalite"])
        else:
            sans_coord += 1
        liste.append(d)
    liste.sort(key=lambda d: (d["taux"] is None, -(d["taux"] or 0)))

    regions = [{"region": r["region"], "rss": r["rss"], **ligne(r, champs)}
               for _, r in reg[reg["t"] == derniere].iterrows()]
    regions.sort(key=lambda d: (d["taux"] is None, -(d["taux"] or 0)))

    actuel = {
        "mis_a_jour": derniere.strftime("%Y-%m-%d %H:%M"),
        "quebec": ligne(qc[qc["t"] == derniere].iloc[-1], champs),
        "regions": regions,
        "installations": liste,
    }
    (SORTIE / "actuel.json").write_text(
        json.dumps(actuel, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    # ---- historique.json ---------------------------------------------------
    debut = derniere - pd.Timedelta(days=JOURS_HISTORIQUE)
    q7 = qc[qc["t"] > debut]
    temps = list(q7["t"])
    r7 = reg[reg["t"] > debut]
    par_region = {}
    for nom, bloc in r7.groupby("region"):
        s = bloc.set_index("t")["taux"].reindex(temps)
        par_region[nom] = [valeur(x) for x in s]
    historique = {
        "t": [x.strftime("%Y-%m-%d %H:%M") for x in temps],
        "quebec": {"taux": [valeur(x) for x in q7["taux"]],
                   "attente": [valeur(x) for x in q7["attente"]],
                   "plus24": [valeur(x) for x in q7["plus24"]]},
        "regions": par_region,
    }
    (SORTIE / "historique.json").write_text(
        json.dumps(historique, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    # ---- profil.json -------------------------------------------------------
    p = qc.dropna(subset=["taux"]).copy()
    p["jour"] = p["t"].dt.weekday          # 0 = lundi
    p["heure"] = p["t"].dt.hour
    grille = p.groupby(["jour", "heure"])["taux"].agg(["mean", "count"])
    profil = {
        "n_releves": int(len(p)),
        "jours_couverts": int(p["t"].dt.date.nunique()),
        "cellules": [{"jour": int(j), "heure": int(h), "taux": valeur(v["mean"]),
                      "n": int(v["count"])} for (j, h), v in grille.iterrows()],
    }
    (SORTIE / "profil.json").write_text(
        json.dumps(profil, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    print(f"Dernier relevé : {actuel['mis_a_jour']} | installations : {len(liste)} "
          f"(sans coordonnées : {sans_coord}) | régions : {len(regions)} | "
          f"points d'historique : {len(temps)} | jours dans le profil : "
          f"{profil['jours_couverts']}")


if __name__ == "__main__":
    main()
