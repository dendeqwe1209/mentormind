"""Who to ask when the Work Assistant refuses (spec 06 §3 step 2), read from the graph of spec 05."""

from __future__ import annotations

from mentormind.agents.ports import CypherRunner

TOP_CONTRIBUTOR = (
    "MATCH (e:Expert)-[:CONTRIBUTED]->(s:Step)<-[:HAS_STEP]-(:Process {process_id: $process_id}) "
    "RETURN coalesce(e.display_name, e.expert_id) AS name, count(DISTINCT s) AS steps "
    "ORDER BY steps DESC, name LIMIT 1"
)


class GraphExperts:
    """``ExpertDirectory`` over the knowledge graph (``Neo4jGraph`` of spec 05)."""

    def __init__(self, graph: CypherRunner) -> None:
        self.graph = graph

    def top_contributor(self, process_id: str) -> str | None:
        rows = self.graph.run(TOP_CONTRIBUTOR, process_id=process_id)
        return str(rows[0]["name"]) if rows and rows[0].get("name") else None
