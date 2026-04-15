# Memento Beyond Memory Tasks

- [x] Task 1: Progettare l'estensione Architetturale (Cognitive Engine)
  - [x] Creare il modulo `memento/cognitive_engine.py` per isolare la logica proattiva dal core database
  - [x] Aggiornare `memento/access_manager.py` per gestire `toggle_warnings` e `toggle_auto_tasks`
- [x] Task 2: Implementare il "Senso di Ragno" (Proactive Warnings)
  - [x] Scrivere la logica in `cognitive_engine.py` per intercettare i "Diamanti Negativi" (errori o frustrazioni note) in base a parole chiave di contesto
  - [x] Esporre il nuovo tool MCP `memento_get_warnings(context_string)` in `mcp_server.py`
  - [x] Testare la ricezione dell'allarme con un contesto simulato (es. una libreria problematica)
- [x] Task 3: Implementare i Task Auto-Generativi (Subconscio)
  - [x] Scrivere la logica in `cognitive_engine.py` che scansiona memorie isolate con etichette di intenti futuri (es. "to refactor", "to fix")
  - [x] Creare una funzione che impacchetta questi nodi in un file `memento.todo.md` nel workspace
  - [x] Esporre il tool MCP `memento_generate_tasks()` (o integrarlo in un job triggerato periodicamente/all'avvio)
  - [x] Testare che il file `.todo.md` venga creato fisicamente sul disco
- [x] Task 4: Aggiornamento dei Toggle (I Superpoteri)
  - [x] Esporre il tool MCP `memento_toggle_superpowers(warnings: bool, tasks: bool)` per controllare il cognitive engine
  - [x] Verificare che quando disabilitati, `get_warnings` e `generate_tasks` ritornino un messaggio di blocco pulito
- [x] Task 5: Documentazione e Review Finale
  - [x] Aggiornare il README per riflettere i nuovi superpoteri di Memento
  - [x] Assicurarsi che i log del server siano espliciti sulle azioni proattive prese
