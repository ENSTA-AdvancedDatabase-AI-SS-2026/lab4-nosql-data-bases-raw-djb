
MATCH p = shortestPath(
  (a:Etudiant {prenom: "Ahmed"})-[:CONNAIT*..10]-(b:Etudiant {prenom: "Yasmina"})
)
RETURN [n IN nodes(p) | n.prenom + " (" + n.universite + ")"] AS chemin,
       length(p) AS nb_intermediaires;

CALL gds.graph.project(
  'reseau_social',
  'Etudiant',
  {
    CONNAIT: { orientation: 'UNDIRECTED' }   
  }
);

CALL gds.degree.stream('reseau_social')
YIELD nodeId, score
RETURN gds.util.asNode(nodeId).prenom      AS etudiant,
       gds.util.asNode(nodeId).universite  AS universite,
       score                               AS nb_connexions
ORDER BY score DESC
LIMIT 10;


CALL gds.louvain.stream('reseau_social')
YIELD nodeId, communityId
WITH communityId,
     collect(gds.util.asNode(nodeId).prenom)      AS membres,
     collect(gds.util.asNode(nodeId).universite)  AS universites
RETURN communityId,
       size(membres)                                AS taille,
       membres[0..5]                                AS exemple_membres,
       // Université dominante dans la communauté (indicateur de cohésion)
       apoc.coll.frequenciesAsMap(universites)      AS repartition_universites
ORDER BY taille DESC;

CALL gds.louvain.stream('reseau_social')
YIELD nodeId, communityId
WITH communityId, collect(gds.util.asNode(nodeId).prenom) AS membres
RETURN communityId,
       size(membres)   AS taille,
       membres[0..5]   AS exemple_membres
ORDER BY taille DESC;

MATCH (moi:Etudiant {prenom: "Ahmed"})

MATCH (candidat:Etudiant)
WHERE candidat <> moi
  AND NOT (moi)-[:CONNAIT]-(candidat)

OPTIONAL MATCH (moi)-[:CONNAIT]-(ami:Etudiant)-[:CONNAIT]-(candidat)
WITH moi, candidat, count(DISTINCT ami) AS nb_amis_communs

OPTIONAL MATCH (moi)-[:SUIT]->(cours:Cours)<-[:SUIT]-(candidat)
WITH moi, candidat, nb_amis_communs, count(DISTINCT cours) AS nb_cours_communs

WITH moi, candidat, nb_amis_communs, nb_cours_communs,
     CASE WHEN moi.filiere = candidat.filiere THEN 1 ELSE 0 END AS meme_filiere

WITH candidat,
     nb_amis_communs,
     nb_cours_communs,
     meme_filiere,
     (nb_amis_communs * 3 + nb_cours_communs * 2 + meme_filiere) AS score

WHERE score > 0  

RETURN candidat.prenom + " " + candidat.nom   AS suggestion,
       candidat.universite                     AS universite,
       candidat.filiere                        AS filiere,
       nb_amis_communs                         AS amis_communs,
       nb_cours_communs                        AS cours_communs,
       meme_filiere                            AS meme_filiere,
       score
ORDER BY score DESC
LIMIT 5;

MATCH path = (debut:Cours)-[:REQUIERT*]->(but:Competence {nom: "Machine Learning"})
RETURN [n IN nodes(path) |
  CASE WHEN n:Cours THEN n.intitule ELSE n.nom END
] AS parcours_apprentissage;

MATCH (c:Cours)-[:ENSEIGNE]->(comp:Competence {nom: "Machine Learning"})
RETURN c.intitule AS cours_recommande, c.credits AS credits;

MATCH (ml:Competence {nom: "Machine Learning"})
MATCH (c:Cours)-[:ENSEIGNE]->(comp:Competence)
WHERE comp.categorie IN ["Programmation", "Bases de Données", "IA"]
RETURN c.intitule AS cours_utile, comp.nom AS competence_enseignee
ORDER BY c.credits DESC;

CALL gds.graph.drop('reseau_social');
