
-- NetworkTopologyStrategy pour la production multi-datacenter.
-- En TP local (nœud unique) on utilise SimpleStrategy avec RF=1.

-- Version production (3 nœuds dans le DC "datacenter1") :
CREATE KEYSPACE IF NOT EXISTS smartgrid
  WITH replication = {
    'class'              : 'NetworkTopologyStrategy',
    'datacenter1'        : 3
  }
  AND durable_writes = true;

-- Version TP local (nœud unique) :
-- CREATE KEYSPACE IF NOT EXISTS smartgrid
--   WITH replication = { 'class': 'SimpleStrategy', 'replication_factor': 1 };

USE smartgrid;

-- Requête cible : "Mesures du capteur X entre T1 et T2"
--
-- Stratégie anti-hot-partition :
--   On bucket par (capteur_id, date_jour) au lieu de juste (capteur_id).
--   Chaque partition couvre une seule journée → taille maîtrisée.
--   10 000 capteurs × 288 mesures/j (toutes les 5 min) = ~2,9 M rows/j
--   mais réparties sur 10 000 partitions distinctes.
--
-- Clustering sur timestamp DESC → les mesures récentes arrivent en tête,
-- parfait pour les lectures "dernières N mesures".

CREATE TABLE IF NOT EXISTS mesures_par_capteur (
  capteur_id   UUID,
  date_jour    DATE,        -- bucket journalier
  timestamp    TIMESTAMP,
  wilaya       TEXT,
  commune      TEXT,
  tension_v    FLOAT,
  courant_a    FLOAT,
  puissance_kw FLOAT,
  frequence_hz FLOAT,
  temperature  FLOAT,
  alerte       BOOLEAN,
  code_alerte  TEXT,
  PRIMARY KEY ((capteur_id, date_jour), timestamp)
) WITH CLUSTERING ORDER BY (timestamp DESC)
  AND default_time_to_live = 7776000;   -- 90 jours en secondes

-- Requête cible : "Alertes de la wilaya X le jour Y"
--
-- Partition = (wilaya, date_jour) : toutes les alertes d'une wilaya
-- sur une journée dans la même partition → lectures séquentielles rapides.
-- Clustering sur timestamp DESC : les alertes les plus récentes en premier.
-- capteur_id en clustering secondaire pour unicité si même milliseconde.

CREATE TABLE IF NOT EXISTS alertes_par_wilaya (
  wilaya       TEXT,
  date_jour    DATE,
  timestamp    TIMESTAMP,
  capteur_id   UUID,
  code_alerte  TEXT,
  description  TEXT,
  gravite      INT,     -- 1=info, 2=warning, 3=critique
  resolue      BOOLEAN,
  PRIMARY KEY ((wilaya, date_jour), timestamp, capteur_id)
) WITH CLUSTERING ORDER BY (timestamp DESC, capteur_id ASC)
  AND default_time_to_live = 31536000;  -- 1 an

-- Requête cible : "Consommation moyenne par heure pour le dashboard wilaya"
--
-- Partition = wilaya : toutes les heures d'une wilaya ensemble.
-- Pour éviter une partition illimitée on peut aussi bucketer par (wilaya, année)
-- mais sur 5 ans de TTL la taille reste raisonnable (wilaya ~ 5*365*24 = 43 800 rows).
-- Clustering sur date_heure DESC : l'heure la plus récente en tête (dashboard live).

CREATE TABLE IF NOT EXISTS agregats_horaires (
  wilaya            TEXT,
  date_heure        TIMESTAMP,    -- tronqué à l'heure (ex: 2024-06-15 14:00:00)
  nb_capteurs       INT,
  puissance_moy_kw  FLOAT,
  puissance_max_kw  FLOAT,
  puissance_min_kw  FLOAT,
  nb_alertes        INT,
  PRIMARY KEY (wilaya, date_heure)
) WITH CLUSTERING ORDER BY (date_heure DESC)
  AND default_time_to_live = 157680000;  -- 5 ans


-- Vérification
DESCRIBE TABLES;
