from concurrent.futures import ThreadPoolExecutor

from app.models import TriageRequest, TriageSuggestion
from app.services.retrieval import Retriever
from app.services.routing import Router


class TriageService:
    """Routing prediction plus retrieval of precedent, before any LLM is involved."""

    def __init__(self, router: Router, retriever: Retriever, k_incidents: int = 5, k_kb: int = 3):
        self._router = router
        self._retriever = retriever
        self._k_incidents = k_incidents
        self._k_kb = k_kb
        self._pool = ThreadPoolExecutor(max_workers=4)

    def suggest(self, request: TriageRequest) -> TriageSuggestion:
        text = request.text()
        incidents = self._pool.submit(self._retriever.similar_incidents, text, self._k_incidents)
        kb = self._pool.submit(self._retriever.kb_articles, text, self._k_kb)
        routing = self._router.predict(text)
        return TriageSuggestion(
            routing=routing,
            similar_incidents=incidents.result(),
            kb_articles=kb.result(),
        )
