# Tasks

- [x] Task 1: Architettura Settings Workspace per Dependency Tracker
  - [x] Aggiungere un dizionario di default per `dependency_tracker` (`{ "enabled": False }`) in `memento/workspace_context.py`.
  - [x] Assicurarsi che `load` e `save` includano correttamente questi dati nel `settings.json` senza sovrascrivere `active_coercion`.
  - [x] Aggiungere `memento_toggle_dependency_tracker` come tool MCP nel `ToolRegistry`.

- [x] Task 2: Scanner AST e Modulo Principale
  - [x] Creare `memento/dependency_tracker.py`.
  - [x] Sviluppare uno scanner asincrono (`asyncio.to_thread` se usa `ast`) che legge iterativamente i file `.py` della directory di lavoro ignorando directory tipiche (`.git`, `.venv`, `.memento`).
  - [x] Visitare l'AST per intercettare i nodi `Import` e `ImportFrom`.
  - [x] Creare un set unificato di tutti gli import top-level rilevati (escludendo import di sistema come `os`, `sys`, ecc., grazie a `sys.stdlib_module_names`).

- [x] Task 3: Risoluzione Manifest vs AST (Name Mapping)
  - [x] Sviluppare una funzione per leggere il file `pyproject.toml` (usando `tomllib` o un regex sicuro) per estrarre il blocco `[project.dependencies]`.
  - [x] Utilizzare `importlib.metadata` per fare un mapping (es. `yaml` -> `PyYAML`) tra moduli trovati e pacchetti installati nell'ambiente corrente.
  - [x] Creare la logica di calcolo delle differenze: Set A (PyProject) vs Set B (Moduli risolti dall'AST).
  - [x] Identificare `orphans` (Dichiarati ma non usati) e `ghosts` (Usati ma non dichiarati).

- [x] Task 4: Creazione Tool MCP `memento_audit_dependencies`
  - [x] Implementare `DependencyAuditTool` in `memento/tools/`.
  - [x] Formattare i risultati dell'analisi in un JSON leggibile dall'LLM, che indichi chiaramente i nomi dei pacchetti e i file in cui sono stati trovati.
  - [x] Aggiornare `memento_status` per mostrare se il Tracker è attivo o meno.

- [x] Task 5: Testing e Validazione
  - [x] Scrivere unit test per lo scanner AST (simulare un file con falsi positivi come `import` dentro una stringa, e veri positivi).
  - [x] Scrivere test per il mapping e la classificazione `orphans` / `ghosts`.

# Task Dependencies
- Task 2 dipende da Task 1.
- Task 3 dipende da Task 2 (per avere il set di import pulito).
- Task 4 dipende da Task 1 (per le flag toggle) e Task 3 (motore logico).
- Task 5 è trasversale.