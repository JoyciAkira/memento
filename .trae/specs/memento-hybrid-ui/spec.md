# Memento Hybrid UI & Proactive Proposals Spec

## Why
Attualmente, il server MCP di Memento perde la configurazione del Goal Enforcer (`ENFORCEMENT_CONFIG`) a ogni riavvio del processo. Inoltre, essendo il protocollo MCP puramente "headless", manca un'interfaccia utente per monitorare lo stato e le memorie del Knowledge Graph. Infine, Memento deve evolvere per diventare un "agente di coppia" in grado di proporre autonomamente l'aggiunta di nuove idee o funzionalità discusse nel codice o nella chat, chiedendo all'utente il permesso di memorizzarle.

## What Changes
- **Hybrid Goal Persistence**: Il server MCP, all'avvio, leggerà lo stato dell'enforcer interrogando il database vettoriale. In aggiunta, se nel workspace corrente è presente un file `.mempalace/memento.rules.md`, il server farà override dei settaggi globali con le regole di progetto locali.
- **Local Web Dashboard**: Verrà avviato un mini server web (es. porta `8080` o simile) in un thread separato dal demone MCP. Questa dashboard mostrerà in formato HTML lo stato dei Livelli (1, 2, 3), gli "Active Goals" attuali, e l'elenco delle ultime memorie inserite.
- **Subconscious Feature Proposal**: Il demone `PreCognitiveDaemon` (Watchdog) e il `CognitiveEngine` verranno potenziati per rilevare nel contesto (codice o discussioni) l'intento di costruire "future features". Se rilevato, il server invierà una notifica MCP al client suggerendo di cristallizzare l'idea nel Knowledge Graph.

## Impact
- Affected specs: Nessuna
- Affected code:
  - `memento/mcp_server.py` (Logica di persistenza, boot server UI, invio notifica)
  - `memento/cognitive_engine.py` (Nuovo metodo per rilevare "future features")
  - Creazione di `memento/ui_server.py` (Mini server web in thread)

## ADDED Requirements

### Requirement: Hybrid Persistence
Il sistema SHALL caricare la configurazione persistente da DB o dal workspace locale.
#### Scenario: Override di progetto
- **WHEN** l'utente avvia l'MCP e la directory di progetto contiene `.mempalace/memento.rules.md`
- **THEN** i Goal attivi verranno sovrascritti con il contenuto del file locale.

### Requirement: Web Dashboard
Il sistema SHALL esporre un server HTTP locale non bloccante.
#### Scenario: Accesso alla dashboard
- **WHEN** l'utente naviga all'URL locale della dashboard (es. `http://localhost:8080`)
- **THEN** la pagina mostra la configurazione `ENFORCEMENT_CONFIG` in RAM, le memorie recenti e gli "Active Goals".

### Requirement: Proactive Feature Proposal
Il sistema SHALL analizzare il contesto e suggerire la memorizzazione di nuove idee.
#### Scenario: Idea nel codice
- **WHEN** l'utente scrive un commento come "TODO: in futuro aggiungiamo il login OAuth" e il Watchdog lo analizza
- **THEN** Memento invia una notifica MCP al client chiedendo: "Vuoi memorizzare l'idea del login OAuth?"
