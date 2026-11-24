"""SOLUTION - healthcare domain modelled as a property graph.

Run:   python exercise/solution.py
"""
from loader import answer, banner, create_db, load, run

# -----------------------------------------------------------------------------
# PART A - SCHEMA
# -----------------------------------------------------------------------------
SCHEMA = """
// Nodes = the nouns of the domain
CREATE NODE TABLE Patient(id STRING, name STRING, age INT64, PRIMARY KEY(id));
CREATE NODE TABLE Drug(id STRING, name STRING, drug_class STRING, PRIMARY KEY(id));
CREATE NODE TABLE Condition(id STRING, name STRING, PRIMARY KEY(id));

// Relationships = the verbs. Facts ABOUT the link live on the link:
// the dose belongs to "Asha takes Warfarin", not to Asha and not to Warfarin.
CREATE REL TABLE TAKES(FROM Patient TO Drug, dose_mg DOUBLE, since INT64);
CREATE REL TABLE HAS_CONDITION(FROM Patient TO Condition);
CREATE REL TABLE TREATS(FROM Drug TO Condition);

// An interaction is symmetric. We store ONE direction and query without an arrow.
CREATE REL TABLE INTERACTS_WITH(FROM Drug TO Drug, severity STRING, effect STRING);
"""

# -----------------------------------------------------------------------------
# PART B - QUERIES
# -----------------------------------------------------------------------------
E1 = """
MATCH (p:Patient {name: 'Asha Rao'})-[t:TAKES]->(d:Drug)
RETURN d.name AS drug, t.dose_mg AS dose_mg, t.since AS since
"""

E2 = """
MATCH (p:Patient)-[:TAKES]->(d1:Drug)-[i:INTERACTS_WITH]-(d2:Drug)<-[:TAKES]-(p)
WHERE d1.id < d2.id
RETURN p.name AS patient, d1.name AS drug_1, d2.name AS drug_2, i.severity AS severity, i.effect AS effect
"""

E3 = """
MATCH (p:Patient)-[:TAKES]->(current:Drug)-[i:INTERACTS_WITH]-(new:Drug {name: $new_drug})
RETURN p.name AS patient, current.name AS current_drug, i.severity AS severity, i.effect AS effect
ORDER BY severity, patient
"""

E4 = """
MATCH (p:Patient)-[:HAS_CONDITION]->(c:Condition)
WHERE NOT EXISTS { MATCH (p)-[:TAKES]->(:Drug)-[:TREATS]->(c) }
RETURN p.name AS patient, c.name AS untreated_condition
"""

if __name__ == "__main__":
    banner("Healthcare graph - SOLUTION")
    conn = create_db(SCHEMA, "solution_db")
    load(conn)
    for label in ["Patient", "Drug", "Condition"]:
        print(f"  {label}: {run(conn, f'MATCH (n:{label}) RETURN count(n)')[1][0][0]} nodes")

    answer(conn, "E1  Asha Rao's drugs", E1)
    answer(conn, "E2  Patients already on an interacting pair", E2)
    answer(conn, "E3  Interactions if we prescribe Ibuprofen", E3, {"new_drug": "Ibuprofen"})
    answer(conn, "E4  Untreated conditions", E4)

    banner("Discussion points")
    print("""  * Why is dose_mg on TAKES and not on Drug?        (it describes the link, not the drug)
  * Why store INTERACTS_WITH in one direction only?  (it is symmetric; query with -[]- )
  * What would you add next?  Doctor -[:PRESCRIBED]-> ... , Allergy, LabResult, Encounter ...
  * How would this look in RDF?  TAKES with a dose needs a Prescription node, like acme:Ownership.""")
