# Pre-cognitive Intervention (Autonomous Daemon) Spec

## Why
Per raggiungere la massima innovazione olistica, Memento deve agire come un "co-pilota fantasma" proattivo. Non vogliamo più che l'utente o l'agente debbano ricordarsi di interrogare la memoria sui problemi passati. Vogliamo che il sistema analizzi costantemente l'ambiente di lavoro in background e interrompa l'utente con "Spider-Sense warnings" quando rileva che si sta ripetendo un anti-pattern o un errore registrato nella memoria del Knowledge Graph.

## What Changes
- Integrazione di `watchdog` per il monitoraggio in tempo reale del filesystem.
- Creazione del modulo `memento/daemon.py` con un loop asincrono in background per processare le modifiche ai file (con meccanismo di debouncing).
- Aggiornamento di `memento/cognitive_engine.py` per esporre un metodo ottimizzato che accetti il testo crudo (diff/code) e restituisca avvisi in caso di similarità coseno con diamanti "negativi" > soglia matematica.
- Aggiornamento di `memento/mcp_server.py` per gestire le comunicazioni Server-Sent Events (SSE) / JSON-RPC verso il client (IDE/Agente) quando il demone lancia un alert.
- Aggiunta di un tool MCP `memento_toggle_precognition` per attivare o disattivare il demone.

## Impact
- Affected specs: Nessuna spec esistente verrà rotta. Aggiunge una capacità passiva/attiva.
- Affected code: `memento/mcp_server.py`, `memento/cognitive_engine.py`. Aggiunta di `memento/daemon.py`. Modifica di `pyproject.toml` per aggiungere `watchdog`.

## ADDED Requirements
### Requirement: Autonomous File Watcher
The system SHALL monitor the specified workspace directory for file changes in the background without blocking the MCP server operations.

#### Scenario: User saves a toxic file
- **WHEN** user modifies and saves a file containing an anti-pattern
- **THEN** the daemon calculates the embedding of the text, compares it against the KG, and pushes an MCP Notification to the client if similarity > threshold.

### Requirement: Debouncing
The system SHALL implement a debounce mechanism (e.g. 5 seconds) to prevent spamming the embedding model and the client with events during active typing.

### Requirement: Toggle Precognition Tool
The system SHALL provide an MCP tool `memento_toggle_precognition` to turn the daemon on and off.
