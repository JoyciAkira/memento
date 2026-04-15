# Tasks

- [x] Task 1: Implementare Hybrid Goal Persistence
  - [x] SubTask 1.1: Aggiornare `mcp_server.py` per caricare lo stato iniziale dei Livelli 1, 2, e 3 leggendo una memoria speciale "SYSTEM_ENFORCEMENT_STATE" dal database FTS5 al boot.
  - [x] SubTask 1.2: Aggiungere logica di override in `mcp_server.py` che controlla l'esistenza di `.mempalace/memento.rules.md` nel `workspace_path` (se fornito) per settare i Goal correnti.
  - [x] SubTask 1.3: Aggiornare `memento_configure_enforcement` per salvare il nuovo stato nel DB in modo da renderlo persistente tra un riavvio e l'altro.

- [x] Task 2: Creare la Web Dashboard Locale
  - [x] SubTask 2.1: Creare `memento/ui_server.py` con una classe/funzione che avvia un `http.server` base in un `threading.Thread` per non bloccare `stdio`.
  - [x] SubTask 2.2: L'interfaccia HTTP deve rispondere in GET alla root (`/`) restituendo un HTML dinamico che legge lo stato di `ENFORCEMENT_CONFIG`, l'output di `get_active_goals()` e le ultime 10 memorie.
  - [x] SubTask 2.3: Integrare l'avvio del thread del server UI in `mcp_server.py` durante l'inizializzazione del server MCP.

- [x] Task 3: Implementare la Proactive Feature Proposal
  - [x] SubTask 3.1: Aggiungere il metodo `detect_latent_features(context: str)` in `CognitiveEngine` che usa l'LLM per estrarre proposte (se esistono) o restituisce una stringa vuota.
  - [x] SubTask 3.2: Aggiornare la callback `on_danger_detected` in `mcp_server.py` per chiamare `detect_latent_features` oltre a controllare bug/warning.
  - [x] SubTask 3.3: Se una feature viene rilevata, inviare una notifica MCP (es. evento `memento/feature_proposal`) all'IDE con il testo del suggerimento.

# Task Dependencies
- Nessuna dipendenza bloccante tra i tre task.
- [Task 1] e [Task 2] e [Task 3] possono essere implementati e testati in parallelo.
