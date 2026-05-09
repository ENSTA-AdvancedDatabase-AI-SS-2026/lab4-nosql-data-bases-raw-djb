
use("medical_db");

db.patients.createIndex(
  { "adresse.wilaya": 1, antecedents: 1 },
  { name: "idx_wilaya_antecedents" }
);

db.patients.createIndex(
  { "consultations.date": -1 },
  { name: "idx_consultations_date" }
);

db.patients.createIndex(
  { "consultations.diagnostic": "text" },
  { name: "idx_text_diagnostic", default_language: "french" }
);

db.analyses.createIndex(
  { patient_id: 1 },
  { name: "idx_analyses_patient" }
);

db.analyses.createIndex(
  { date: -1 },
  { name: "idx_analyses_date" }
);

const requeteTest = {
  "adresse.wilaya": "Alger",
  antecedents: "Diabète type 2"
};

print("=== APRÈS index (executionStats) ===");
const explainResult = db.patients.find(requeteTest).explain("executionStats");

const stats = explainResult.executionStats;
printjson({
  nReturned:             stats.nReturned,
  totalDocsExamined:     stats.totalDocsExamined,
  totalKeysExamined:     stats.totalKeysExamined,
  executionTimeMillis:   stats.executionTimeMillis,

  indexUsed: explainResult.queryPlanner.winningPlan.inputStage?.indexName ?? "COLLSCAN (pas d'index)"
});

print("\n=== Recherche full-text sur diagnostics ===");
const fullTextResult = db.patients.find(
  { $text: { $search: "hypertension" } },
  { score: { $meta: "textScore" }, nom: 1, prenom: 1 }
).sort({ score: { $meta: "textScore" } }).toArray();

printjson(fullTextResult);

db.analyses.createIndex(
  { date: 1 },
  {
    expireAfterSeconds: 157_766_400,   
    name: "idx_ttl_analyses_5ans"
  }
);

print("\n Tous les index créés.");
print("Index sur patients :", db.patients.getIndexes().map(i => i.name));
print("Index sur analyses :", db.analyses.getIndexes().map(i => i.name));