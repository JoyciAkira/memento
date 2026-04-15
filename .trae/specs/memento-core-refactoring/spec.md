# Memento Core Refactoring Spec

## Why
L'architettura attuale di Memento presenta limiti strutturali legati alla concorrenza (operazioni sincrone bloccanti l'event loop), all'accoppiamento del routing MCP (God function `call_tool`), alla ricerca esclusivamente full-text (mancanza di search semantico nativo in SQLite), e alla gestione dei prompt hardcoded. Risolvere questi limiti trasformerà Memento in un server MCP di livello Enterprise: asincrono, scalabile, semantico e modulare.

## What Changes
- **Full-Async Architecture**: Refactoring del provider e del motore cognitivo per eseguire I/O (SQLite, OpenAI) in thread separati (o tramite aiosqlite/AsyncOpenAI) evitando di bloccare l'event loop MCP.
- **Advanced Hybrid Search (Semantic + FTS5)**: Integrazione di embedding (tramite OpenAI o libreria locale) salvati nel DB SQLite, con algoritmo Reciprocal Rank Fusion (RRF) per combinare match esatti (FTS5) e vicinanza semantica (cosine similarity vettoriale).
- **MCP Router Refactoring (Tool Registry Pattern)**: Smantellamento del "God Block" `if/elif` in `mcp_server.py`. Creazione di una classe `ToolRegistry` e migrazione di ogni tool in classi isolate con schema e metodo `execute()`.
- **Prompt Abstraction**: Estrazione dei prompt di sistema da `cognitive_engine.py` a file esterni (es. YAML o template testuali) nella cartella `memento/prompts/`.
- ****BREAKING****: L'aggiornamento a ricerca ibrida richiederà una migrazione del database SQLite o la generazione asincrona degli embedding per le memorie esistenti.

## Impact
- Affected specs: MCP Router, SQLite Provider, Cognitive Engine.
- Affected code: `memento/mcp_server.py`, `memento/provider.py`, `memento/cognitive_engine.py`, `memento/prompts/*`

## ADDED Requirements
### Requirement: Tool Registry
The system SHALL provide a modular Tool Registry where each MCP tool is self-contained.

#### Scenario: Success case
- **WHEN** the MCP server initializes
- **THEN** it dynamically registers all tools from the `memento/tools/` directory (or a registry map)
- **AND** dispatches `call_tool` directly to the tool's `execute` method.

### Requirement: Hybrid Search
The system SHALL provide hybrid search combining text and vector similarity.

#### Scenario: Success case
- **WHEN** the user searches for a memory
- **THEN** the provider computes the query embedding, runs FTS5 and vector search, fuses results with RRF, and returns the top matches.

## MODIFIED Requirements
### Requirement: Async I/O
The system SHALL perform all OpenAI API calls and SQLite queries asynchronously without blocking the main MCP event loop.

## REMOVED Requirements
Nessuna rimozione funzionale, solo refactoring architetturale.
