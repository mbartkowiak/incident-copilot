# 0003: Index distinct problem statements ("precedents"), not individual tickets

**Status:** Accepted, 2026-09-29

## Context
The first incident index embedded every resolved incident (~8,300 rows). Two problems:
1. Many tickets share the same problem statement, so the top 5 results were often five copies of one case. That gives an agent (or a human) no more precedent than one result.
2. Free Edition rate-limits the managed embedding endpoint to roughly 25 rows/minute, so a full re-embed took hours.

## Decision
`rag_sources.sql` builds `incident_precedents`: one row per distinct (case-insensitive) problem statement. Each row keeps the most recent example ticket, its fix, the team that most often resolved it, the average resolution time, the most common KB reference, and an `occurrences` count. The Vector Search index is built on this table (1,896 rows).

The MERGE only updates a precedent when its example ticket or count changes, so routine refreshes don't re-embed unchanged rows.

## Consequences
- Retrieval returns varied precedents, and "seen 14 times" is itself a useful signal for triage.
- Embedding work dropped ~77%, and incremental syncs stay small.
- Individual incident numbers still resolve through `incident_docs` (the per-ticket table) when the agent needs ticket-level detail.
- With real, free-text tickets, exact-match dedup would collapse little. There, near-duplicate clustering (for example on embedding similarity) would replace the hash key.
