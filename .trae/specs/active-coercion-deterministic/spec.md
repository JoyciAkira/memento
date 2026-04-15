# Active Coercion Deterministica (Notifiche IDE + Blocco Commit) Spec

## Why
Gli agenti LLM possono reintrodurre anti-pattern, bug storici o violare standard architetturali senza accorgersene. Serve un sistema che impedisca regressioni in modo affidabile e ripetibile, senza dipendere da inferenza LLM.

## What Changes
- Introduzione di **Active Coercion** come enforcement **deterministico** basato su regole “hard” (regex + path_globs + override token).
- Aggiunta di un toggle per workspace: `active_coercion.enabled` persistito in `/.memento/settings.json`.
- Invio di notifiche MCP in IDE quando una regola viene violata durante la modifica di un file (runtime).
- Blocco deterministico dei commit tramite `pre-commit hook` installabile automaticamente (per workspace) e disattivabile via toggle.
- (Non obiettivo) Non blocchiamo fisicamente il salvataggio del file nell’editor; blocchiamo solo il commit e notifichiamo l’utente.

## Impact
- Affected specs: precognitive daemon, workspace settings, MCP tool surface, git hooks.
- Affected code:
  - `memento/workspace_context.py` (persistenza config per workspace)
  - `memento/daemon.py` (integrazione enforcement su file change)
  - `memento/mcp_server.py` (nuovi tool MCP + notifiche)
  - Nuovi moduli per Active Coercion e hook pre-commit (da definire in implementazione)

## ADDED Requirements

### Requirement: Toggle Active Coercion
Il sistema SHALL permettere di abilitare/disabilitare Active Coercion per workspace tramite un tool MCP, persistendo la configurazione.

#### Scenario: Success case
- **WHEN** l’utente invoca `memento_toggle_active_coercion` con `enabled=true`
- **THEN** Active Coercion risulta attivo per quel workspace e viene salvato in `/.memento/settings.json`
- **AND** la chiamata successiva a `memento_status` riporta lo stato attivo

#### Scenario: Disable case
- **WHEN** l’utente invoca `memento_toggle_active_coercion` con `enabled=false`
- **THEN** l’enforcement non produce blocchi né notifiche e l’hook pre-commit (se presente) non blocca commit

### Requirement: Hard Rules Deterministiche
Il sistema SHALL valutare violazioni esclusivamente con logica deterministica:
- matching per file tramite `path_globs`
- matching per contenuto tramite `regex`
- override tramite token testuale configurabile (es. `memento-override`)

#### Scenario: Rule match blocks commit
- **GIVEN** `active_coercion.enabled=true` e una regola `severity=block`
- **WHEN** un commit contiene un file staged che matcha la regola e non contiene override token
- **THEN** il pre-commit hook termina con exit code `1` e stampa un errore che include `rule_id` e `message`

#### Scenario: Override allows commit
- **GIVEN** una regola `severity=block` matcha un file staged
- **WHEN** il file contiene l’override token (es. `memento-override`)
- **THEN** il commit non viene bloccato da quella regola

### Requirement: IDE Notifications (Runtime)
Il sistema SHALL inviare una notifica MCP quando una violazione viene rilevata dal daemon durante la modifica di un file.

#### Scenario: Runtime block notification
- **GIVEN** `active_coercion.enabled=true`
- **WHEN** un file modificato matcha una regola `severity=block`
- **THEN** il server invia una notifica `memento/active_coercion_block` con `{file, rule_id, message}`

### Requirement: Hook Installation
Il sistema SHALL fornire un modo deterministico e ripetibile per installare/aggiornare un `pre-commit hook` nel repository git del workspace.

#### Scenario: Hook install success
- **WHEN** l’utente invoca `memento_install_git_hooks`
- **THEN** viene creato/aggiornato `.git/hooks/pre-commit` con permessi eseguibili
- **AND** il hook esegue la validazione Active Coercion sui file staged

## MODIFIED Requirements

### Requirement: Pre-Cognitive Daemon
Il daemon SHALL supportare anche la generazione di notifiche Active Coercion, mantenendo debounce e isolamento per workspace.

## REMOVED Requirements
Nessuna.
