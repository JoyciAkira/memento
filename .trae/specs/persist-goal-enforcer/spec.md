# Persist Goal Enforcer Spec

## Why
Attualmente, quando l'MCP di Memento si riavvia, perde le impostazioni del Goal Enforcer (i livelli di enforcement 1, 2 e 3). Questo costringe l'utente a riconfigurarli manualmente ad ogni sessione. Serve un salvataggio persistente e ibrido che mantenga lo stato sia in un file di macchina (`.memento/settings.json`) sia in un file leggibile e versionabile dall'utente (`.memento.rules.md`) nella root del progetto.

## What Changes
- Creazione del modulo `memento/enforcement_rules.py` per fare il parsing e il rendering di un blocco delimitato in Markdown contenente la configurazione.
- Modifica di `load_enforcement_config()` per leggere le impostazioni da `.memento/settings.json` e sovrascriverle con i valori presenti in `.memento.rules.md` (se esiste).
- Modifica di `save_enforcement_config()` per salvare lo stato sia in `.memento/settings.json` sia, in modo non distruttivo (preservando gli appunti dell'utente), in `.memento.rules.md`.
- Aggiornamento del tool `memento_status` per mostrare la presenza dei file di configurazione.

## Impact
- Affected specs: Goal Enforcer
- Affected code: `memento/mcp_server.py`

## ADDED Requirements
### Requirement: Hybrid Config Persistence
The system SHALL persist the tri-state Goal Enforcer configuration across restarts using a hybrid approach.

#### Scenario: Success case
- **WHEN** the user calls `memento_configure_enforcement`
- **THEN** the configuration is applied in memory, saved to `.memento/settings.json`, and injected/updated in a `<!-- memento:goal-enforcer:start -->` block inside `.memento.rules.md` in the workspace root.
