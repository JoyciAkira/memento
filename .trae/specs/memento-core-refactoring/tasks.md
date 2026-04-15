# Tasks

- [x] Task 1: Refactoring Architettura Full-Async (Event Loop Non-Bloccante)
  - [x] Sostituire le chiamate bloccanti a `sqlite3` in `provider.py` e `knowledge_graph.py` con `aiosqlite` o wrapparle in `asyncio.to_thread()`.
  - [x] Aggiornare `cognitive_engine.py` per usare `AsyncOpenAI` invece del client sincrono.
  - [x] Modificare la firma e l'esecuzione di tutti i tool MCP in `mcp_server.py` affinché beneficino della natura asincrona.
  - [x] Aggiornare e validare l'intera suite di test.

- [x] Task 2: Implementazione MCP Router Refactoring (Tool Registry Pattern)
  - [x] Creare la struttura base del `ToolRegistry` (es. `memento/registry.py` o simile).
  - [x] Estrarre la logica di ogni tool (attualmente in `mcp_server.py`) in classi isolate all'interno di una cartella `memento/tools/`.
  - [x] Sostituire il grande blocco `if/elif` in `mcp_server.py` con una semplice invocazione `registry.execute(name, arguments, ctx)`.
  - [x] Testare che la registrazione e l'invocazione dinamica funzionino come prima.

- [x] Task 3: Estrazione e Versionamento dei Prompt Cognitivi
  - [x] Creare la cartella `memento/prompts/` e inserire file YAML o `.txt` (es. `dream_synthesis.yml`, `goal_alignment.yml`).
  - [x] Aggiornare `cognitive_engine.py` per leggere i prompt dinamicamente (es. tramite `Jinja2` o formattazione standard Python).
  - [x] Verificare che il Cognitive Engine restituisca output corretti.

- [x] Task 4: Ricerca Ibrida Avanzata (Semantic + FTS5 con RRF)
  - [x] Integrare `sqlite-vec` (o `sqlite-vss`) nel `NeuroGraphProvider` (oppure implementare calcolo locale/remoto di embedding via OpenAI/HuggingFace salvato come array BLOB/JSON in SQLite per RRF in RAM se le estensioni SQLite non sono praticabili).
  - [x] Aggiornare la funzione `add()` per generare e salvare l'embedding del testo.
  - [x] Aggiornare la funzione `search()` per eseguire FTS5 e Vector Search contemporaneamente.
  - [x] Implementare l'algoritmo Reciprocal Rank Fusion (RRF) per fondere e restituire i risultati migliori.
  - [x] Aggiungere unit tests per la ricerca ibrida.

# Task Dependencies
- Task 2 dipende da Task 1 (per ereditare l'asincronia).
- Task 3 può essere eseguito in parallelo a Task 1.
- Task 4 dipende da Task 1 (per le API asincrone degli embedding e DB asincrono).
