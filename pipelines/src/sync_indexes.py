"""Create the Vector Search indexes if missing, otherwise trigger an incremental sync."""

import argparse
import time

from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import BadRequest, NotFound
from databricks.sdk.service.vectorsearch import (
    DeltaSyncVectorIndexSpecRequest,
    EmbeddingSourceColumn,
    PipelineType,
    VectorIndexType,
)

EMBEDDING_ENDPOINT = "databricks-gte-large-en"

# source table -> (primary key, columns returned with results)
INDEXES = {
    "incident_precedents": ("precedent_id", [
        "number", "short_description", "close_notes", "category", "subcategory",
        "assignment_group", "location", "priority_label", "mttr_hours", "kb_reference",
        "occurrences", "last_seen",
    ]),
    "kb_docs": ("number", ["title", "text", "kb_category", "category", "subcategory"]),
}  # fmt: skip


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", default="workspace")
    parser.add_argument("--schema", default="incident_copilot")
    parser.add_argument("--endpoint", default="incident-copilot-vs")
    args = parser.parse_args()

    w = WorkspaceClient()
    for table, (primary_key, columns) in INDEXES.items():
        source = f"{args.catalog}.{args.schema}.{table}"
        index = f"{source}_index"
        try:
            w.vector_search_indexes.get_index(index)
        except NotFound:
            print(f"creating {index}")
            w.vector_search_indexes.create_index(
                name=index,
                endpoint_name=args.endpoint,
                primary_key=primary_key,
                index_type=VectorIndexType.DELTA_SYNC,
                delta_sync_index_spec=DeltaSyncVectorIndexSpecRequest(
                    source_table=source,
                    pipeline_type=PipelineType.TRIGGERED,
                    embedding_source_columns=[
                        EmbeddingSourceColumn(
                            name="embed_text", embedding_model_endpoint_name=EMBEDDING_ENDPOINT
                        )
                    ],
                    columns_to_sync=[primary_key, "embed_text", *columns],
                ),
            )
            continue
        sync_when_idle(w, index)


def sync_when_idle(w: WorkspaceClient, index: str, timeout_s: int = 3600) -> None:
    """An index can only sync once its previous sync (or initial build) has finished."""
    deadline = time.monotonic() + timeout_s
    while True:
        try:
            w.vector_search_indexes.sync_index(index)
            print(f"syncing {index}")
            return
        except BadRequest as e:
            if "not ready to sync" not in str(e) or time.monotonic() > deadline:
                raise
            print(f"{index} busy, waiting: {e}")
            time.sleep(30)


if __name__ == "__main__":
    main()
