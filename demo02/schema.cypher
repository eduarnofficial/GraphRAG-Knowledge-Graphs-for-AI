// =====================================================================
//  Acme procurement graph - PROPERTY GRAPH SCHEMA (Kùzu Cypher DDL)
// =====================================================================
//  Read this file top to bottom before running 01_property_graph.py.
//
//  A property graph has two building blocks:
//    * NODES          - things   (a vendor, a company, a person, an address)
//    * RELATIONSHIPS  - links    (who owns whom, who directs what, ...)
//  Both can carry PROPERTIES (key = value pairs).
//
//  Kùzu is "schema first": every node label and relationship type is declared
//  up front with its properties and data types. Neo4j is "schema optional":
//  you can skip this step there, and add constraints later.
// =====================================================================

// ---------- NODE TABLES (one per label) ------------------------------
// PRIMARY KEY = the unique id used to find a node (like a table's key).

CREATE NODE TABLE Vendor(
    id STRING, name STRING, service STRING, risk STRING, country STRING,
    PRIMARY KEY(id));

CREATE NODE TABLE Company(
    id STRING, name STRING, kind STRING, country STRING,
    sanctioned BOOLEAN, sanctions_list STRING,
    PRIMARY KEY(id));

CREATE NODE TABLE Person(
    id STRING, name STRING, role STRING,
    PRIMARY KEY(id));

// Tip: give EVERY node a human-readable "name", even addresses.
// Paths and query results are then easy to read.
CREATE NODE TABLE Address(
    id STRING, name STRING, line STRING, city STRING, country STRING,
    PRIMARY KEY(id));

// ---------- RELATIONSHIP TABLES (one per type) -----------------------
// FROM X TO Y = which node labels the relationship may connect.
// This is the "domain -> range" rule from the ontology, enforced by the database.
// Relationships carry their OWN properties (share_pct, since, ...).
// That is the big strength of the property graph model.

CREATE REL TABLE OWNED_BY(
    FROM Vendor TO Company,
    FROM Company TO Company,
    share_pct DOUBLE, since INT64);

CREATE REL TABLE DIRECTOR_OF(
    FROM Person TO Company,
    since INT64);

CREATE REL TABLE APPROVED(
    FROM Person TO Vendor,
    approved_on DATE, contract_value DOUBLE);

CREATE REL TABLE REGISTERED_AT(
    FROM Vendor TO Address,
    FROM Company TO Address);
