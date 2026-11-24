"""GraphRAG: retrieval = entity linking + graph traversal over the knowledge graph.

  question -> link entities -> traverse relations (multi-hop) -> subgraph
           -> serialise subgraph as triples (the LLM context) -> answer with citations
"""
from kg import build_from_documents, to_cypher, to_json
from reasoner import answer


class GraphRAG:
    def __init__(self, documents, ontology):
        self.ontology = ontology
        self.G, self.facts, self.extractor = build_from_documents(documents, ontology)

    def ask(self, question):
        result = answer(question, self.G, self.ontology)
        # What would be sent to an LLM as context: the retrieved triples, not raw text.
        result["context"] = [
            f"({e['source']})-[:{e['rel']}]->({e['target']})" for e in result["edges"]
        ] + [
            f"({n}) {self.G.nodes[n]['props']}" for n in result["nodes"] if self.G.nodes[n]["props"]
        ]
        return result

    def stats(self):
        types, rels = {}, {}
        for _, d in self.G.nodes(data=True):
            types[d["type"]] = types.get(d["type"], 0) + 1
        for _, _, d in self.G.edges(data=True):
            rels[d["rel"]] = rels.get(d["rel"], 0) + 1
        return {"nodes": self.G.number_of_nodes(), "edges": self.G.number_of_edges(),
                "facts_extracted": len(self.facts), "node_types": types, "relation_types": rels}

    def export_json(self):
        return to_json(self.G)

    def export_cypher(self):
        return to_cypher(self.G)
