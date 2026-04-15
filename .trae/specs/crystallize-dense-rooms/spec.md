# Organic Archive (Cognitive Crystallization) Spec

## Why
Rooms with >100 drawers suffer from the "hubness problem" where a handful of high-frequency concept vectors dominate retrieval results, obscuring query intent. An archival lifecycle mitigates this by soft-archiving stale/noisy drawers, reducing the neighborhood radius while keeping core concepts (Diamonds) in the primary room.

## What Changes
- Add `mempalace.entropy` to detect rooms exceeding the 100-drawer threshold.
- Add `mempalace.crystallize` to apply intra-room PageRank and identify top K core drawers.
- Add `mempalace.archive` to move non-core drawers to an `archive` wing while creating an `has_archive` bridge in the Knowledge Graph.
- Update `mempalace.cli` with a `crystallize` command.
- Update `mempalace.searcher` to exclude the `archive` wing by default and include a `--deep` flag.

## Impact
- Affected specs: Retrieval accuracy, background optimization
- Affected code: `mempalace/cli.py`, `mempalace/searcher.py`, `mempalace/knowledge_graph.py`, plus 3 new modules.

## ADDED Requirements
### Requirement: Hubness Detection
The system SHALL identify rooms containing more than a configurable threshold of vectors (default 100).
#### Scenario: Success case
- **WHEN** user runs `mempalace crystallize`
- **THEN** the system lists rooms with >100 drawers.

### Requirement: Cognitive Crystallization
The system SHALL use vector similarity to compute intra-room PageRank and identify the top K core pillars.
#### Scenario: Success case
- **WHEN** a dense room is processed
- **THEN** it returns a list of diamond IDs and a list of noise IDs.

### Requirement: Soft Archiving
The system SHALL move noise IDs to a soft-archive wing and link the original room to the archive room in the Knowledge Graph.
#### Scenario: Success case
- **WHEN** noise vectors are archived
- **THEN** their wing metadata is updated to "archive" and a `has_archive` triple is added to the SQLite KG.

### Requirement: Deep Search
The system SHALL exclude the "archive" wing from standard searches but include it when a `--deep` flag is provided.
#### Scenario: Success case
- **WHEN** user searches without `--deep`
- **THEN** archived vectors are not returned.
