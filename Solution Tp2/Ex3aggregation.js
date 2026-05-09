
use("medical_db");

print("=== 3.1 : Top diagnostics par wilaya ===");

const diagParWilaya = db.patients.aggregate([

  { $unwind: "$consultations" },
  {
    $group: {
      _id: {
        wilaya: "$adresse.wilaya",
        diagnostic: "$consultations.diagnostic"
      },
      count: { $sum: 1 }
    }
  },

  { $sort: { count: -1 } },

  { $limit: 20 },

  {
    $project: {
      _id: 0,
      wilaya: "$_id.wilaya",
      diagnostic: "$_id.diagnostic",
      count: 1
    }
  }
]).toArray();

printjson(diagParWilaya);

print("\n=== 3.2 : Top médicaments par spécialité ===");

const medsParSpecialite = db.patients.aggregate([
 
  { $unwind: "$consultations" },

  { $unwind: "$consultations.medicaments" },

  {
    $group: {
      _id: {
        specialite: "$consultations.medecin.specialite",
        medicament: "$consultations.medicaments.nom"
      },
      count: { $sum: 1 }
    }
  },

  { $sort: { "_id.specialite": 1, count: -1 } },

  {
    $group: {
      _id: "$_id.specialite",
      topMedicament: { $first: "$_id.medicament" },
      prescriptions: { $first: "$count" }
    }
  },

  { $sort: { _id: 1 } },

  {
    $project: {
      _id: 0,
      specialite: "$_id",
      topMedicament: 1,
      prescriptions: 1
    }
  }
]).toArray();

printjson(medsParSpecialite);

print("\n=== 3.3 : Consultations par mois (12 derniers mois) ===");

const evolutionMensuelle = db.patients.aggregate([
  { $unwind: "$consultations" },
  {
    $match: {
      "consultations.date": {
        $gte: new Date(new Date().setFullYear(new Date().getFullYear() - 1))
      }
    }
  },

  {
    $group: {
      _id: {
        annee: { $year: "$consultations.date" },
        mois:  { $month: "$consultations.date" }
      },
      total: { $sum: 1 }
    }
  },

  { $sort: { "_id.annee": 1, "_id.mois": 1 } },

  {
    $project: {
      _id: 0,
      periode: {
        $concat: [
          { $toString: "$_id.annee" },
          "-",
          {
            $cond: {
              if: { $lt: ["$_id.mois", 10] },
              then: { $concat: ["0", { $toString: "$_id.mois" }] },
              else: { $toString: "$_id.mois" }
            }
          }
        ]
      },
      total: 1
    }
  }
]).toArray();

printjson(evolutionMensuelle);

print("\n=== 3.4 : Profil patients à risque élevé ===");

const patientsRisque = db.patients.aggregate([

  {
    $match: {
      antecedents: { $all: ["Diabète type 2", "HTA"] },
      dateNaissance: {
        $lte: new Date(new Date().setFullYear(new Date().getFullYear() - 60))
      }
    }
  },

  {
    $addFields: {
      age: {
        $floor: {
          $divide: [
            { $subtract: [new Date(), "$dateNaissance"] },
            1000 * 60 * 60 * 24 * 365.25
          ]
        }
      },
      nbConsultations: { $size: "$consultations" }
    }
  },

  {
    $group: {
      _id: null,
      nbPatients:           { $sum: 1 },
      ageMoyen:             { $avg: "$age" },
      consultationsMoyenne: { $avg: "$nbConsultations" },
      wilayas:              { $addToSet: "$adresse.wilaya" }
    }
  },

  {
    $project: {
      _id: 0,
      nbPatients: 1,
      ageMoyen: { $round: ["$ageMoyen", 1] },
      consultationsMoyenne: { $round: ["$consultationsMoyenne", 1] },
      wilayas: 1
    }
  }
]).toArray();

printjson(patientsRisque);

print("\n=== 3.5 : Top 5 médecins & taux de ré-consultation ===");

const rapportMedecins = db.patients.aggregate([
  { $unwind: "$consultations" },

  {
    $group: {
      _id: "$consultations.medecin.nom",
      specialite:           { $first: "$consultations.medecin.specialite" },
      totalConsultations:   { $sum: 1 },
      patientsUniques:      { $addToSet: "$_id" }
    }
  },

  {
    $addFields: {
      nbPatientsUniques: { $size: "$patientsUniques" },
      tauxReconsultation: {
        $multiply: [
          {
            $divide: [
              { $subtract: ["$totalConsultations", { $size: "$patientsUniques" }] },
              { $size: "$patientsUniques" }
            ]
          },
          100
        ]
      }
    }
  },

  { $sort: { totalConsultations: -1 } },

  { $limit: 5 },

  {
    $project: {
      _id: 0,
      medecin: "$_id",
      specialite: 1,
      totalConsultations: 1,
      nbPatientsUniques: 1,
      tauxReconsultation: { $round: ["$tauxReconsultation", 1] }
    }
  }
]).toArray();

printjson(rapportMedecins);