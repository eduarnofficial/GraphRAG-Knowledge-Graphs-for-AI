# Hands-on: model a small healthcare domain

**Time:** 20 minutes. Work in pairs.
**Goal:** turn a short description of a domain into a graph schema, load the data, and answer four questions with Cypher.

## The domain

A clinic needs to answer medication-safety questions. It tracks the following:

- **Patients**, each with a name and age
- **Drugs**, each with a name and drug class
- **Conditions** that patients have
- Which drugs a patient **takes**, with the dose and start year
- Which drugs **treat** which conditions
- Which drugs **interact** with each other, with a severity and the effect

## Step 1: Design on paper first (5 minutes)

Draw circles for the things (nodes) and arrows for the relationships. For every property, decide whether it belongs on a node or on a relationship.

> Ask yourself whether the value describes **the thing** or **the link between two things**.
> The dose describes "Asha takes Warfarin", so it goes on the `TAKES` relationship.

## Step 2: Write the schema (7 minutes)

Open `starter.py` and complete **PART A**. Use these names so the provided loader works:

| Kind | Name | From → To | Properties |
|------|------|-----------|------------|
| Node | `Patient` | | id, name, age (done for you) |
| Node | `Drug` | | id, name, drug_class |
| Node | `Condition` | | id, name |
| Relationship | `TAKES` | Patient → Drug | dose_mg DOUBLE, since INT64 |
| Relationship | `HAS_CONDITION` | Patient → Condition | none |
| Relationship | `TREATS` | Drug → Condition | none |
| Relationship | `INTERACTS_WITH` | Drug → Drug | severity STRING, effect STRING |

Run this command after each change:

```powershell
python exercise/starter.py
```

The output tells you whether the schema is complete.

## Step 3: Write the queries (6 minutes)

Complete **PART B** in `starter.py`. Each query has a hint above it.

| # | Question | Expected answer |
|---|----------|-----------------|
| E1 | Which drugs does Asha Rao take, and at what dose? | Warfarin 5 mg, Lisinopril 10 mg |
| E2 | Which patients already take two drugs that interact? | Chen Li: Warfarin + Amiodarone (high) |
| E3 | What would interact if we prescribe Ibuprofen? | Warfarin for Asha and Chen (high); Lisinopril for Asha and Ben (moderate) |
| E4 | Which conditions are not treated by any drug the patient takes? | Chen Li: Osteoarthritis |

## Step 4: Compare and discuss (2 minutes, then group debrief)

```powershell
python exercise/solution.py
```

Discuss these questions:

1. Where did your model differ from the solution? Is your version also valid?
2. `INTERACTS_WITH` is symmetric. Why do we store only one direction?
3. How would you model the same domain in **RDF**? (Hint: a dose needs a `Prescription` node, like `acme:Ownership` in step 2.)
4. What would you add next? For example: Doctor, Allergy, LabResult, Encounter.
