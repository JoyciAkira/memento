# Tasks

- [x] Task 1: Introdurre storage lifecycle (memory_meta + goals) nel DB workspace
  - [x] SubTask 1.1: Estendere `NeuroGraphProvider.initialize()` per creare tabelle `memory_meta` e `goals` (id, timestamps, active/is_deleted, delete_reason, supersedes/replaced_by)
  - [x] SubTask 1.2: Aggiungere metodi provider per:
    - soft delete memory (`soft_delete_memory(id, delete_reason, supersedes_id=None)`)
    - list deleted memories (limit/offset)
    - set goals (replace/append con archiviazione e delete_reason)
    - list goals (attivi + archivio)
  - [x] SubTask 1.3: Test DB schema: inizializzazione crea tabelle e vincoli minimi (pytest)

- [x] Task 2: Soft delete end-to-end (tool MCP + filtri retrieval)
  - [x] SubTask 2.1: Aggiungere tool MCP `memento_soft_delete_memory` (write-gated) con input: `memory_id`, `delete_reason`, `supersedes_id?`
  - [x] SubTask 2.2: Aggiungere tool MCP `memento_list_deleted_memories` (read) per audit locale (no contenuti se richiesto, almeno id+reason+timestamp)
  - [x] SubTask 2.3: Modificare retrieval legacy (`NeuroGraphProvider.search`) per escludere `is_deleted=1` di default
  - [x] SubTask 2.4: Modificare retrieval vNext (`memento/retrieval/*`) per escludere `is_deleted=1` di default in tutte le lane
  - [x] SubTask 2.5: Aggiornare `memento_explain_search` / trace per indicare esclusioni per deleted (senza re-iniettare testo cancellato)
  - [x] SubTask 2.6: Test: dopo soft delete, la memoria non compare in `memento_search_memory` e `search_vnext_bundle`, ma compare in list deleted

- [x] Task 3: Goals first-class (tool MCP + injection)
  - [x] SubTask 3.1: Aggiungere tool MCP:
    - `memento_set_goals(goals: [string], delete_reason?: string, context?: string)`
    - `memento_list_goals(active_only?: bool, context?: string)`
  - [x] SubTask 3.2: Aggiornare `get_active_goals(ctx, ...)` per leggere dallo storage goals (non più search su memorie)
  - [x] SubTask 3.3: Aggiornare UI endpoint `/api/goals` (se necessario) per usare la nuova sorgente
  - [x] SubTask 3.4: Test: set goals sostituisce i precedenti con history + delete_reason; get_active_goals ritorna solo attivi

- [x] Task 4: Adaptive Retrieval v1 (routing deterministico + pesi dinamici + decay)
  - [x] SubTask 4.1: Implementare “query classifier” deterministico in `memento/retrieval/pipeline.py` (code-like / episodic / generic)
  - [x] SubTask 4.2: Usare classifier per impostare `lane_weights` e parametri (es. recency decay) in `retrieve_bundle()`
  - [x] SubTask 4.3: Esporre un output di tracing che includa: tipo query, pesi scelti, e top per lane (riusando `traces`)
  - [x] SubTask 4.4: Aggiungere (o estendere) tool MCP `memento_search_vnext` / `memento_explain_retrieval` senza breaking changes ai tool esistenti
  - [x] SubTask 4.5: Test: per query code-like, trace mostra pesi FTS più alti; per query episodic, recency più alta

- [x] Task 5: Safety & regression gates
  - [x] SubTask 5.1: Assicurare che soft delete e set goals rispettino `access_manager` (write-gated)
  - [x] SubTask 5.2: Aggiornare/aggiungere smoke test tool per includere nuovi tool (e garantire che non crashino offline)
  - [x] SubTask 5.3: Eseguire: `uv run pytest -q` e `uv run ruff check .`

# Task Dependencies
- Task 2 dipende da Task 1
- Task 3 dipende da Task 1
- Task 4 dipende da Task 2 (per garantire esclusione deleted in retrieval adattivo)
- Task 5 dipende da Task 2–4
