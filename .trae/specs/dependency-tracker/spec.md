# Dependency Tracker Deterministico Spec

## Why
I progetti software tendono ad accumulare "dipendenze orfane" (installate ma mai usate) o "ghost dependencies" (usate nel codice ma mancanti nel manifest, importate per puro caso da librerie transitive). L'approccio LLM tradizionale basato su "leggi il codice e dimmi cosa serve" genera innumerevoli allucinazioni e rompe le build.
Creiamo un modulo deterministico in Memento che sfrutta il parsing dell'Abstract Syntax Tree (AST) e la risoluzione dei lockfile per garantire al 100% l'igiene delle dipendenze, rendendolo il primo "Cognitive Package Manager".

## What Changes
- Creazione del modulo `memento/dependency_tracker.py` basato su Python `ast` e `importlib`.
- Aggiunta della configurazione `dependency_tracker.enabled` in `.memento/settings.json` (Default: disabilitato/togglabile per Workspace).
- Creazione dei tool MCP: `memento_toggle_dependency_tracker` e `memento_audit_dependencies`.
- Il tracker scansionerà in modo asincrono i file Python, incrocerà i risultati dell'AST con `pyproject.toml` (o simili) e mapperà correttamente gli `import` ai nomi reali dei pacchetti (es. `yaml` -> `PyYAML`).

## Impact
- Affected specs: `mcp_server.py`, `workspace_context.py`.
- Affected code: Modulo autonomo e tool registry.

## ADDED Requirements

### Requirement: Deterministic AST Scanner
The system SHALL parse `.py` files using the `ast` module to deterministically collect all `import` and `import from` statements, ignoring strings, comments, and docstrings.

#### Scenario: Success case
- **WHEN** the AST parser scans `import yaml; import sys`
- **THEN** it registers `yaml` as a third-party dependency, ignoring built-ins like `sys`.

### Requirement: Name Resolution
The system SHALL map the AST import names to their actual PyPI distribution names using standard library tools or reliable mapping logic.

#### Scenario: Resolving discrepancies
- **WHEN** the code imports `yaml`
- **THEN** the system resolves the dependency to the installed package `PyYAML`.

### Requirement: MCP Audit Tool
The system SHALL expose an MCP tool for LLMs to query the exact state of dependencies.

#### Scenario: Detecting Orphans
- **WHEN** `requests` is in `pyproject.toml` but absent from the AST
- **THEN** `memento_audit_dependencies` returns it as an `orphan`.

## MODIFIED Requirements
### Requirement: Workspace Settings
The workspace settings JSON SHALL be extended to store `dependency_tracker` preferences (e.g. `{ "enabled": true }`).

## REMOVED Requirements
Nessuna rimozione.
