# Autonomous Memory Engine vNext (Retrieval + Knowledge Graph + Agent Loop)

## Overview
This design upgrades Memento from a “store + search” memory server into an autonomous memory engine that continuously improves retrieval quality, converts episodic traces into durable knowledge, and exposes agentic tooling that can plan, evaluate, and consolidate memory with minimal operator effort.

The vNext architecture is built on three pillars:
- Retrieval+Eval: a multi-lane retrieval pipeline with fusion, reranking, and first-class evaluation.
- Knowledge Graph: entity/fact extraction and temporalized facts enabling multi-hop recall and stable “semantic memory”.
- Agent Loop: a background/on-demand loop that runs maintenance, critique, and tuning tasks via MCP tools.

## Goals
- Improve recall and precision for “hard” queries (vague, underspecified, multi-hop, long-tail).
- Provide a durable semantic layer (entities/facts) alongside raw memories, with temporal validity and provenance.
- Add an agentic control surface to run: consolidation, regression evals, and safe auto-tuning.
- Keep the system local-first and developer-friendly: deterministic DB, inspectable artifacts, low operator burden.
- Preserve existing behavior as a baseline, with incremental rollout behind flags.

## Non-Goals
- Multi-user auth, remote hosting, or enterprise RBAC.
- Replacing MCP with a custom protocol.
- Building a full general-purpose autonomous agent; the “agent loop” is scoped to memory operations.
- Requiring GPUs or always-on heavyweight models by default.

## Key Concepts
- **Episodic memory**: raw traces (notes, events, code snippets, tool outputs).
- **Semantic memory**: extracted, deduplicated facts and relations with provenance and validity windows.
- **Working set**: a small, high-quality set of candidates prepared for LLM consumption (reranked and compressed).
- **Eval suite**: curated queries + expected references, used for regression and tuning.

## Architecture

### High-Level Data Flow
1. Ingest memory (manual tool call, daemon watcher, or UI) → persist episodic record.
2. Background/on-demand consolidation:
   - chunk/normalize → extract entities/facts → resolve/merge → update graph + fact timelines.
3. Retrieval for a query:
   - query analysis + optional expansion → multi-lane candidate retrieval → fusion → rerank → assemble context.
4. Evaluation loop:
   - run benchmark queries → compute metrics → generate diffs → (optional) propose parameter updates.

### Modules (Proposed)
- `memento/retrieval/`: query analysis, lane retrievers, fusion, reranking, context assembly.
- `memento/graph/`: entity extraction, resolution, graph storage, traversal, fact timelines.
- `memento/eval/`: datasets, runners, metrics, reports, regression gating.
- `memento/agent/`: orchestrator for background and on-demand runs (safe scheduling, budgets, locking).
- `memento/provider.py` remains the primary façade, delegating to retrieval/graph components.

## Data Model (SQLite)
This is a conceptual schema; exact DDL should be decided during implementation with migrations.

### Episodic Layer
- `memories`
  - `id` (pk), `created_at`, `workspace_root`, `source` (manual/daemon/ui/tool), `content`, `metadata_json`
- `memory_chunks`
  - `id` (pk), `memory_id` (fk), `chunk_index`, `content`, `token_count`, `hash`
- `memory_embeddings`
  - `chunk_id` (fk), `embedding_model`, `vector_blob`, `norm`, `created_at`
- `memory_fts` (FTS5 virtual table)
  - `chunk_id`, `content`

### Graph + Facts Layer
- `entities`
  - `id` (pk), `type` (person/project/file/api/etc), `canonical_name`, `aliases_json`, `fingerprint`, `created_at`, `updated_at`
- `relations`
  - `id` (pk), `src_entity_id`, `dst_entity_id`, `relation_type`, `weight`, `provenance_json`, `created_at`, `updated_at`
- `facts`
  - `id` (pk), `subject_entity_id`, `predicate`, `object_value` (text/json), `confidence`, `created_at`
- `fact_versions`
  - `id` (pk), `fact_id` (fk), `valid_from`, `valid_to` (nullable), `value`, `supporting_memory_ids_json`, `updated_at`

### Eval Layer
- `eval_sets`
  - `id` (pk), `name`, `description`, `created_at`
- `eval_cases`
  - `id` (pk), `eval_set_id` (fk), `query`, `expected_memory_ids_json` (or expected entity/fact refs), `notes`
- `eval_runs`
  - `id` (pk), `eval_set_id`, `started_at`, `ended_at`, `config_json`, `summary_json`
- `eval_results`
  - `id` (pk), `eval_run_id`, `eval_case_id`, `retrieved_ids_json`, `metrics_json`, `artifacts_json`

## Retrieval vNext

### Query Analysis
- Detect intent: “fact lookup” vs “episodic recall” vs “code navigation” vs “task history”.
- Extract entities from query (lightweight, heuristic-first; optional LLM-assisted).
- Generate expanded queries when needed:
  - **HyDE**-style hypothetical answer text (optional, behind a flag).
  - alias expansion from graph (entity aliases).
  - domain hints (workspace, file paths, tool names).

### Multi-Lane Candidate Retrieval
Each lane outputs `(doc_id, score, evidence)`; candidates are later fused.
- **Lane A: FTS (BM25)** over chunks, boosted by recency and workspace scope.
- **Lane B: Dense embeddings** over chunks, cosine similarity with robust filtering.
- **Lane C: Graph-first**:
  - entities/facts matched to query → traverse N hops (bounded) → map back to supporting memories/chunks.
- **Lane D: Recency/Session**:
  - most recent memories, pinned memories, and “active goal” context.

### Fusion + Rerank
- Use Reciprocal Rank Fusion (RRF) to combine lanes into a single ranked list.
- Apply a second-stage reranker (configurable):
  - lightweight heuristic rerank (default),
  - optional LLM rerank for the top-K (budgeted, cached, off by default).
- Build a working set:
  - deduplicate near-identical chunks,
  - cap by token budget,
  - attach citations (memory_id, chunk_id, offsets).

### Context Assembly
- Output a structured bundle:
  - top chunks (episodic evidence),
  - relevant facts (semantic summary) with provenance,
  - entity map for disambiguation.

## Knowledge Graph vNext

### Extraction
- Extract candidate entities and relations from new episodic memories:
  - heuristic extractors first (paths, symbols, repo names),
  - optional LLM extractor behind a flag for “hard” content.

### Entity Resolution (Dedup)
- Canonicalize entity names (case, separators, common prefixes).
- Maintain alias sets and a stable fingerprint per entity type.
- Merge policy:
  - conservative auto-merge for high-confidence fingerprints,
  - otherwise keep separate and allow future merge via tooling.

### Fact Timelines (Evolution)
- Facts are temporalized via `fact_versions`:
  - adding a new fact closes the prior `valid_to` window when confident and conflicting,
  - otherwise creates parallel candidate versions with confidence.

### Graph-Aware Retrieval
- Map facts/relations back to the supporting episodic evidence.
- Enable bounded multi-hop expansions (e.g., “project X depends on lib Y, which introduced API Z”).

## Agent Loop vNext

### Modes
- **On-demand**: explicit MCP tool calls (safe defaults).
- **Background**: periodic low-priority tasks triggered by:
  - ingest volume thresholds,
  - schedule,
  - explicit “opt-in” flag.

### Responsibilities
- Consolidation: chunking, extraction, entity resolution, fact updates.
- Maintenance: pruning, compaction, re-embedding on model change, index health checks.
- Evaluation: scheduled regression runs and report generation.
- Tuning (optional): propose parameter changes with rollback support.

### Safety and Budgets
- Strict rate limits on model calls (tokens/time).
- Workspace-scoped locks for DB mutations to avoid concurrency hazards.
- Never auto-delete episodic memories; consolidation only adds derived artifacts and links.

## MCP Tooling (New/Extended)
The exact tool names should follow existing conventions in `memento/tools/`.

### Retrieval
- `memento_search_vnext(query, workspace_root, options)` → returns structured context bundle.
- `memento_explain_retrieval(query, workspace_root)` → returns lane contributions and fusion traces.

### Graph
- `memento_graph_query(workspace_root, query)` → entities/facts traversal results with provenance.
- `memento_graph_merge_entities(workspace_root, entity_ids, canonical_name)` → explicit merge.

### Consolidation
- `memento_consolidate(workspace_root, scope, options)` → runs consolidation pipeline.
- `memento_backfill_graph(workspace_root, since)` → extract graph artifacts from historic memories.

### Eval
- `memento_eval_run(workspace_root, eval_set, options)` → produces run artifacts and summary metrics.
- `memento_eval_report(workspace_root, eval_run_id)` → human-readable report.

### Agent Loop Control
- `memento_agent_status(workspace_root)` → loop state, budgets, last runs.
- `memento_agent_run(workspace_root, task, options)` → runs a single task safely.

## Configuration
- `MEMENTO_VNEXT=1` to enable vNext retrieval pipeline.
- Per-workspace config file (e.g., `.memento/config.json`) to control:
  - enabled lanes, top-K values, RRF parameters,
  - model selection for embeddings/rerank,
  - agent loop scheduling/budgets.
- Defaults must work with no config.

## Security and Privacy
- Ensure UI and tool outputs remain safe for rendering (escape/encode untrusted content).
- Never log raw secrets; reuse the existing redaction strategy and extend it to derived artifacts.
- Keep derived artifacts traceable to sources for auditability (provenance fields).

## Acceptance Criteria
- Retrieval returns a structured bundle that includes:
  - ranked episodic evidence (with citations),
  - relevant facts (with provenance),
  - optional lane traces when requested.
- Graph layer supports:
  - entity extraction + conservative dedup,
  - fact timelines with validity windows,
  - bounded multi-hop traversal that maps back to episodic evidence.
- Agent loop supports:
  - on-demand consolidation and eval runs,
  - background mode behind an explicit opt-in flag,
  - budgets and workspace-scoped locking.
- Eval suite exists with a small but representative set of regression cases and produces stored reports.

## Implementation Plan (Milestones)
1. Retrieval vNext scaffolding
   - introduce retrieval module boundary + structured result bundle
   - add multi-lane candidate retrieval + RRF fusion with tracing
2. Graph foundations
   - entities/facts schema + extraction pipeline + provenance wiring
   - graph-aware retrieval lane
3. Eval harness
   - eval set format + runner + stored metrics + simple report
4. Agent loop
   - task registry + budgets + locking + on-demand tools
   - background mode (opt-in) + maintenance tasks
5. Hardening and rollout
   - feature flags and safe defaults
   - regression gates + docs updates
