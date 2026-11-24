"""HANDS-ON: model a small healthcare domain as a property graph.

Your job (about 25 minutes; read exercise/README.md first):
  Part A - complete the SCHEMA below (node tables + relationship tables).
  Part B - write the four Cypher queries E1..E4.
Run it as often as you like:   python exercise/starter.py
Stuck? Compare with exercise/solution.py.
"""
from loader import answer, banner, create_db, load

# =============================================================================
# PART A - SCHEMA
# One node table is done for you as an example. Add the rest.
#
#  Nodes you need:        Patient (done), Drug, Condition
#  Relationships needed:  TAKES          Patient -> Drug        props: dose_mg DOUBLE, since INT64
#                         HAS_CONDITION  Patient -> Condition   (no props)
#                         TREATS         Drug    -> Condition   (no props)
#                         INTERACTS_WITH Drug    -> Drug        props: severity STRING, effect STRING
#  Property names must match what loader.py writes (see the README table).
# =============================================================================
SCHEMA = """
CREATE NODE TABLE Patient(id STRING, name STRING, age INT64, PRIMARY KEY(id));

// TODO: CREATE NODE TABLE Drug(...)       columns: id, name, drug_class
// TODO: CREATE NODE TABLE Condition(...)  columns: id, name

// TODO: CREATE REL TABLE TAKES(FROM Patient TO Drug, dose_mg DOUBLE, since INT64);
// TODO: CREATE REL TABLE HAS_CONDITION(...)
// TODO: CREATE REL TABLE TREATS(...)
// TODO: CREATE REL TABLE INTERACTS_WITH(...)
"""

# =============================================================================
# PART B - QUERIES  (replace each "TODO" string with Cypher)
# =============================================================================

# E1  Which drugs does Asha Rao take, and at what dose?
#     Hint: (p:Patient {name: 'Asha Rao'})-[t:TAKES]->(d:Drug)  ... RETURN d.name, t.dose_mg
E1 = "TODO"

# E2  Which patients ALREADY take two drugs that interact with each other?
#     Hint: the patient points to BOTH drugs, and the drugs are linked by INTERACTS_WITH.
#     Interactions go both ways, so leave the arrow off:  (d1)-[i:INTERACTS_WITH]-(d2)
#     Add  WHERE d1.id < d2.id  so each pair is reported only once.
E2 = "TODO"

# E3  The doctor wants to prescribe a NEW drug ($new_drug). Which of each patient's
#     current drugs interact with it?   Use a parameter: {name: $new_drug}
E3 = "TODO"

# E4  Which patients have a condition that NONE of their current drugs treats?
#     Hint: MATCH patient -> condition, then filter with
#           WHERE NOT EXISTS { MATCH (p)-[:TAKES]->(:Drug)-[:TREATS]->(c) }
E4 = "TODO"


if __name__ == "__main__":
    banner("Healthcare graph - YOUR model")
    try:
        conn = create_db(SCHEMA, "starter_db")
        load(conn)
        print("  Schema created and data loaded. Well done - now the queries.")
    except Exception as e:
        print(f"  Schema not complete yet, so loading stopped here:\n  {e}")
        print("  Finish PART A (every TODO in SCHEMA) and run again.")
        raise SystemExit(0)

    answer(conn, "E1  Asha Rao's drugs", E1)
    answer(conn, "E2  Patients already on an interacting pair", E2)
    answer(conn, "E3  Interactions if we prescribe Ibuprofen", E3, {"new_drug": "Ibuprofen"})
    answer(conn, "E4  Untreated conditions", E4)
