# Tasks

- [x] Task 1: Definire e persistere configurazione Active Coercion per workspace
  - [x] Estendere la lettura/scrittura di `/.memento/settings.json` per includere `active_coercion.enabled` e `active_coercion.rules`
  - [x] Garantire default deterministici (enabled=false, rules=[])

- [x] Task 2: Implementare engine deterministico di regole “hard”
  - [x] Creare un modulo che carica regole, valida schema, e valuta match (glob + regex + override token)
  - [x] Aggiungere output strutturato: lista violazioni con `{rule_id, file, message, severity}`

- [x] Task 3: Esporre i tool MCP per toggle e gestione hook
  - [x] Aggiungere tool `memento_toggle_active_coercion(enabled, workspace_root)`
  - [x] Aggiungere tool `memento_install_git_hooks(workspace_root)` che installa/aggiorna `.git/hooks/pre-commit`
  - [x] Aggiornare `memento_status` per mostrare stato Active Coercion

- [x] Task 4: Integrare Active Coercion nel daemon per notifiche runtime
  - [x] Quando il daemon riceve un evento file-change, se `active_coercion.enabled=true` valutare le regole sul contenuto
  - [x] Se ci sono violazioni con `severity=block`, inviare notifica `memento/active_coercion_block`

- [x] Task 5: Implementare pre-commit hook deterministico
  - [x] Il hook deve validare solo i file staged (non working tree)
  - [x] Il hook deve rispettare `active_coercion.enabled` e l’override token
  - [x] Output chiaro su stderr con regola violata e file

- [x] Task 6: Test
  - [x] Unit test per engine regole (match, no-match, override, path_globs)
  - [x] Test per toggle/persistenza config workspace
  - [x] Test per hook (repo git temporaneo: staged file → commit bloccato/permesso)

# Task Dependencies
- Task 2 dipende da Task 1
- Task 4 dipende da Task 1 e Task 2
- Task 5 dipende da Task 1 e Task 2
- Task 3 dipende da Task 1 (status/toggle) e Task 5 (install hook)
- Task 6 dipende da tutti
