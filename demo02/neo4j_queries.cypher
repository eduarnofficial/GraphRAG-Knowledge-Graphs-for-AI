// =====================================================================
//  The same query tour, written for NEO4J (Desktop, Aura Free or Browser)
// =====================================================================
//  1. Run  python 01_property_graph.py  - it writes output/neo4j_load.cypher
//  2. In Neo4j Browser paste output/neo4j_load.cypher and run it
//     (enable "multi-statement query editor" in Browser settings).
//  3. Run the queries below one at a time.
//
//  Most Cypher is identical in Kùzu and Neo4j. The differences are marked "NEO4J:".
// =====================================================================

// Q1 - every vendor
MATCH (v:Vendor)
RETURN v.name AS vendor, v.risk AS risk, v.country AS country
ORDER BY vendor;

// Q2 - high-risk vendors
MATCH (v:Vendor)
WHERE v.risk = 'high'
RETURN v.name AS vendor, v.service AS service;

// Q3 - relationship properties
MATCH (v:Vendor)-[o:OWNED_BY]->(c:Company)
RETURN v.name AS vendor, c.name AS owner, o.share_pct AS share_pct, o.since AS since;

// Q4 - aggregation
MATCH (p:Person)-[a:APPROVED]->(v:Vendor)
RETURN p.name AS approver, count(v) AS vendors, sum(a.contract_value) AS total_value
ORDER BY total_value DESC;

// Q5 - variable-length ownership chain
// NEO4J: length() takes the PATH variable, so name the path p.
MATCH p = (v:Vendor {name: 'Apex Logistics'})-[:OWNED_BY*1..5]->(owner:Company)
RETURN owner.name AS owner, length(p) AS hops
ORDER BY hops;

// Q6 - director in the chain who also sits on a sanctioned board
MATCH (v:Vendor)-[:OWNED_BY*1..5]->(c:Company)<-[:DIRECTOR_OF]-(p:Person)-[:DIRECTOR_OF]->(s:Company)
WHERE s.sanctioned = true
RETURN v.name AS vendor, c.name AS owner_in_chain, p.name AS director, s.name AS sanctioned_company;

// Q7 - shared registered address
MATCH (v:Vendor)-[:REGISTERED_AT]->(a:Address)<-[:REGISTERED_AT]-(s:Company)
WHERE s.sanctioned = true
RETURN v.name AS vendor, a.name AS shared_address, s.name AS sanctioned_company;

// Q8 - shortest path to a sanctioned company
// NEO4J: shortestPath(...) and a list comprehension instead of Kùzu's [* SHORTEST] and properties()
MATCH (s:Company {sanctioned: true}), (v:Vendor)
MATCH p = shortestPath((v)-[:OWNED_BY|DIRECTOR_OF|REGISTERED_AT*..6]-(s))
RETURN v.name AS vendor, length(p) AS hops, [n IN nodes(p) | n.name] AS path;

// Q9 - vendors with no owner record
// NEO4J also allows the shorter form:  WHERE NOT (v)-[:OWNED_BY]->()
MATCH (v:Vendor)
OPTIONAL MATCH (v)-[:OWNED_BY]->(c:Company)
WITH v, c
WHERE c IS NULL
RETURN v.name AS vendor_without_owner_record;

// Q10 - MERGE (idempotent create)
MERGE (p:Person {id: 'P6'})
ON CREATE SET p.name = 'Grace Kim', p.role = 'Procurement analyst'
RETURN p.id AS id, p.name AS name, p.role AS role;

// Bonus - see the whole graph as a picture in Neo4j Browser
MATCH (n)-[r]->(m) RETURN n, r, m;
