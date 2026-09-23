# =============================================================================
# Analyse du relevé horaire de la situation dans les urgences du Québec
# Source : MSSS, Données Québec (CC BY 4.0)
# À lancer depuis la racine du dépôt Donnees-Urgences
# =============================================================================

# install.packages(c("dplyr", "ggplot2", "lubridate", "glmmTMB"))
library(dplyr)
library(ggplot2)
library(lubridate)
library(glmmTMB)

# -----------------------------------------------------------------------------
# 1. Lecture et préparation
# -----------------------------------------------------------------------------
fichiers <- list.files("data", pattern = "^urgences_.*\\.csv$", full.names = TRUE)
brut <- bind_rows(lapply(fichiers, read.csv, colClasses = "character",
                         check.names = FALSE, fileEncoding = "UTF-8"))

names(brut)  # À VÉRIFIER : adaptez les noms ci-dessous s'ils diffèrent

# Certains nombres peuvent avoir une virgule décimale ou « non disponible »
en_nombre <- function(x) suppressWarnings(as.numeric(gsub(",", ".", x)))

# Trouve une colonne par mot-clé, quelle que soit l'orthographe exacte
colonne <- function(motif) {
  n <- grep(motif, names(brut), ignore.case = TRUE, value = TRUE)
  if (length(n) != 1) stop("Motif « ", motif, " » : ", length(n), " colonne(s) trouvée(s) : ",
                           paste(n, collapse = ", "))
  brut[[n]]
}

urg <- tibble(
    rss           = colonne("^RSS$"),
    region        = colonne("^Region"),
    etablissement = colonne("etablissement"),
    installation  = colonne("^Nom_installation"),
    t = ymd_hms(colonne("^horodatage$"), tz = "America/Toronto"),
    civieres  = en_nombre(colonne("fonctionnelles")),
    occupees  = en_nombre(colonne("occupees")),
    plus24    = en_nombre(colonne("24")),
    plus48    = en_nombre(colonne("48")),
    presents  = en_nombre(colonne("presents")),
    attente   = en_nombre(colonne("PEC")),
    dms_civiere     = en_nombre(colonne("^DMS_sur_civiere$")),
    dms_ambulatoire = en_nombre(colonne("^DMS_ambulatoire$"))
  ) |>
  mutate(
    heure       = hour(t),
    jour        = wday(t, label = TRUE, abbr = FALSE, week_start = 1),
    fin_semaine = wday(t, week_start = 1) >= 6,
    taux_occ    = occupees / civieres,        # peut dépasser 100 %
    surcapacite = as.integer(taux_occ > 1)    # variable binaire
  )

# Trois niveaux d'agrégation à ne jamais mélanger dans un même modèle
quebec  <- filter(urg, installation == "Ensemble du Québec")
regions <- filter(urg, installation == "Total régional")
inst    <- filter(urg, !installation %in% c("Ensemble du Québec", "Total régional"),
                  civieres > 0)

# -----------------------------------------------------------------------------
# 2. Qualité des données
# -----------------------------------------------------------------------------
# Heures sans relevé (ordinateur en veille, panne, etc.)
heures_attendues <- seq(floor_date(min(quebec$t), "hour"), max(quebec$t), by = "hour")
cat("Heures manquantes :", length(heures_attendues) - n_distinct(quebec$t),
    "sur", length(heures_attendues), "\n")

# Installations qui ne déclarent pas certaines variables
inst |>
  group_by(installation) |>
  summarise(n_releves = n(),
            pct_attente_manquante = mean(is.na(attente)),
            pct_occ_manquante     = mean(is.na(taux_occ))) |>
  arrange(desc(pct_attente_manquante))

# -----------------------------------------------------------------------------
# 3. Exploration
# -----------------------------------------------------------------------------
# Série complète à l'échelle du Québec
ggplot(quebec, aes(t, attente)) +
  geom_line() +
  labs(x = NULL, y = "Patients en attente de prise en charge",
       title = "Ensemble du Québec")

# Profil journalier moyen
quebec |>
  group_by(heure) |>
  summarise(attente = mean(attente, na.rm = TRUE)) |>
  ggplot(aes(heure, attente)) +
  geom_line() + geom_point() +
  labs(x = "Heure", y = "Patients en attente (moyenne)")

# Carte de chaleur heure × jour du taux d'occupation
quebec |>
  group_by(jour, heure) |>
  summarise(occ = mean(taux_occ, na.rm = TRUE), .groups = "drop") |>
  ggplot(aes(heure, jour, fill = occ)) +
  geom_tile() +
  scale_fill_viridis_c(labels = scales::percent) +
  labs(x = "Heure", y = NULL, fill = "Occupation")

# Comparaison des régions
ggplot(regions, aes(reorder(region, taux_occ, FUN = median, na.rm = TRUE), taux_occ)) +
  geom_boxplot() +
  geom_hline(yintercept = 1, linetype = 2) +
  scale_y_continuous(labels = scales::percent) +
  coord_flip() +
  labs(x = NULL, y = "Taux d'occupation des civières")

# -----------------------------------------------------------------------------
# 4. Modèles (au niveau des installations)
# -----------------------------------------------------------------------------
inst <- inst |>
  mutate(jour_f       = factor(jour, ordered = FALSE),
         installation = factor(installation),
         h_sin = sin(2 * pi * heure / 24),   # effet cyclique de l'heure :
         h_cos = cos(2 * pi * heure / 24))   # 2 paramètres au lieu de 23

# a) Comptage : patients en attente de prise en charge médicale
#    Binomiale négative (surdispersion) + effet aléatoire par installation
m_attente <- glmmTMB(attente ~ h_sin + h_cos + jour_f + (1 | installation),
                     family = nbinom2, data = inst)
summary(m_attente)
exp(fixef(m_attente)$cond)   # rapports de taux

# b) Taux : patients sur civière depuis plus de 24 h, par civière fonctionnelle
#    L'offset ramène le comptage à la taille de l'urgence
m_24h <- glmmTMB(plus24 ~ jour_f + offset(log(civieres)) + (1 | installation),
                 family = nbinom2, data = inst)
summary(m_24h)

# c) Binaire : l'urgence est-elle en surcapacité (occupation > 100 %) ?
m_surcap <- glmmTMB(surcapacite ~ h_sin + h_cos + jour_f + (1 | installation),
                    family = binomial, data = inst)
summary(m_surcap)
exp(fixef(m_surcap)$cond)    # rapports de cotes

# d) Autocorrélation : les relevés d'une même urgence d'une heure à l'autre
#    ne sont pas indépendants. Structure AR(1) par installation.
#    Calcul lourd : commencez avec une seule région, p. ex. Montréal (RSS 06).
mtl <- inst |>
  filter(rss == "06") |>
  mutate(temps = factor(as.numeric(floor_date(t, "hour"))))
m_ar1 <- glmmTMB(attente ~ h_sin + h_cos + jour_f + (1 | installation) +
                   ar1(temps + 0 | installation),
                 family = nbinom2, data = mtl)
summary(m_ar1)

# -----------------------------------------------------------------------------
# 5. Durées moyennes de séjour : une valeur par jour (données de la veille),
#    répétée à chaque heure. On agrège avant de l'analyser.
# -----------------------------------------------------------------------------
dms_jour <- inst |>
  mutate(date = as_date(t)) |>
  group_by(installation, region, date) |>
  summarise(dms_civiere     = first(na.omit(dms_civiere)),
            dms_ambulatoire = first(na.omit(dms_ambulatoire)),
            .groups = "drop")
