from typing import Any, Protocol

from databricks.sdk import WorkspaceClient

from app.models import KbArticle, SimilarIncident

INCIDENT_COLUMNS = [
    "number", "short_description", "close_notes", "category", "subcategory",
    "assignment_group", "location", "priority_label", "mttr_hours", "kb_reference",
    "occurrences",
]  # fmt: skip
KB_COLUMNS = ["number", "title", "text", "kb_category"]


class Retriever(Protocol):
    def similar_incidents(self, text: str, k: int) -> list[SimilarIncident]: ...

    def kb_articles(self, text: str, k: int) -> list[KbArticle]: ...


class VectorSearchRetriever:
    """Semantic search over resolved incidents and KB articles (Databricks Vector Search)."""

    def __init__(self, client: WorkspaceClient, incident_index: str, kb_index: str) -> None:
        self._client = client
        self._incident_index = incident_index
        self._kb_index = kb_index

    def _query(self, index: str, columns: list[str], text: str, k: int) -> list[dict[str, Any]]:
        resp = self._client.vector_search_indexes.query_index(
            index, columns=columns, query_text=text, num_results=k
        )
        if not resp.manifest or not resp.manifest.columns or not resp.result:
            return []
        names = [c.name or "" for c in resp.manifest.columns]
        return [dict(zip(names, row, strict=True)) for row in resp.result.data_array or []]

    def similar_incidents(self, text: str, k: int) -> list[SimilarIncident]:
        rows = self._query(self._incident_index, INCIDENT_COLUMNS, text, k)
        return [SimilarIncident.model_validate(r) for r in rows]

    def kb_articles(self, text: str, k: int) -> list[KbArticle]:
        rows = self._query(self._kb_index, KB_COLUMNS, text, k)
        return [KbArticle.model_validate(r) for r in rows]
