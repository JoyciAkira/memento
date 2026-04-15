# Workspace Memory Isolation + Safe Migration Design Spec

## Goal
Garantire che ogni progetto (workspace) abbia un database di memoria separato (`<workspace>/.memento/neurograph_memory.db`) e fornire una migrazione sicura delle memorie già presenti in database “globali” o non correttamente associati.

## User decisioni già confermate
- L’IDE avvia un MCP server separato per ogni workspace con `MEMENTO_DIR` già impostato.
- Migrazione **non distruttiva**: modalità **COPIA** (nessuna cancellazione dal DB sorgente).
- Assegnazione memorie a workspace via **euristica testo** (match su nome repo/path nel contenuto), con report per ambigui/non assegnabili.
- Elenco workspace: **lista manuale** fornita dall’utente.

## Non-goals (per ora)
- Un singolo MCP server che cambia workspace a runtime (nessun `memento_set_workspace`).
- Migrazione “intelligente” via LLM routing (evitiamo non determinismo).
- Cancellazione/dedup distruttivo nel DB sorgente.

## Stato attuale (problema)
- Il server MCP può partire con `workspace` non desiderato (es. home), quindi le memorie finiscono in `/Users/<user>/.memento/neurograph_memory.db`.
- In alcuni casi `.memento` in posizioni non correlate può interferire con la detection del project root.
- Risultato: memorie “di progetto” finiscono nel DB “globale” e appaiono quando l’utente si aspetta isolamento per repo.

## Target behavior
1. Se l’IDE imposta `MEMENTO_DIR=<workspace_root>`, il provider usa sempre `<workspace_root>/.memento/neurograph_memory.db`.
2. Se `MEMENTO_DIR` non è impostato, il project root detection non deve “catturare” la home solo perché esiste `~/.memento/`.
3. È disponibile un comando di migrazione che:
   - copia memorie dal DB “globale” ai DB per-workspace,
   - non perde dati,
   - è idempotente,
   - produce un report verificabile.

## Decisioni di architettura

### A) Workspace binding (hardening)
- Workspace canonico: `workspace = os.environ["MEMENTO_DIR"]` se presente, altrimenti `find_project_root(os.getcwd())`.
- `find_project_root()` deve usare marker “di progetto” (`.git`, `pyproject.toml`, `package.json`, `Cargo.toml`) e NON deve considerare `.memento` come marker del progetto (perché `~/.memento` non è un progetto).
- Il path del DB deve essere calcolato esclusivamente da `workspace` (unico source of truth).

### B) Metadata per future migrazioni
Su `provider.add(...)` aggiungere automaticamente (se non già presenti) metadata:
- `workspace_root`: path assoluto del workspace
- `workspace_name`: basename del workspace

Questi campi non sono richiesti per il retrieval, ma rendono audit e migrazioni future deterministiche.

## Safe migration (COPIA + report)

### Input
- `source_db`: il DB “globale” individuato (tipicamente `~/.memento/neurograph_memory.db`).
- `workspaces`: lista manuale di workspace root.

### Workspace candidates
Ogni workspace root ha:
- `workspace_root` (assoluto)
- `workspace_name` (basename)
- `target_db = <workspace_root>/.memento/neurograph_memory.db` (creato se mancante)

### Assegnazione memoria → workspace
Algoritmo deterministico:
1. Normalizzare `memory_text` in lower.
2. Calcolare match per ogni workspace:
   - match se contiene `workspace_name.lower()` oppure se contiene una variante del path (es. porzioni significative del path).
3. Se match esattamente 1 workspace: assegnare a quel workspace.
4. Se match 0 workspace: `unassigned`.
5. Se match > 1: `ambiguous`.

### Copia e idempotenza
- Copiare una memoria nel DB target solo se `id` non è già presente nel target.
- Non modificare il DB sorgente.
- Eseguire sempre in modo ripetibile: una seconda esecuzione non deve duplicare.

### Report
Generare un file nel workspace del tool runner (o in un path scelto dall’utente), contenente:
- conteggi per workspace (`copied`, `skipped_existing`)
- lista `unassigned` con snippet (safe-truncated)
- lista `ambiguous` con workspace candidati
- summary finale (memorie totali viste, totali copiate, totali non assegnate)

### Safety
- Backup fisico del DB sorgente prima della migrazione (copia file).
- Operazioni su SQLite in transazioni per ogni target.
- No logging di contenuti completi; nel report usare snippet limitati.

## Testing strategy
- Unit test dell’assegnazione (match unico / nessun match / match multiplo).
- Integration test: creare 2 workspace temporanei + un DB sorgente con memorie miste, eseguire migrazione, verificare:
  - ogni target contiene solo ciò che gli appartiene,
  - il sorgente rimane invariato,
  - idempotenza.
- Test di “workspace binding”: con `MEMENTO_DIR` settato, il provider deve scrivere nel DB del workspace; senza `MEMENTO_DIR`, non deve selezionare home solo per presenza di `~/.memento`.

## Success criteria
- Avviando Memento con `MEMENTO_DIR` puntato a una repo, il DB creato/usato è sempre `<repo>/.memento/neurograph_memory.db`.
- Il DB “globale” in home non viene usato quando `MEMENTO_DIR` è settato.
- La migrazione COPIA sposta correttamente le memorie assegnabili e produce un report con ambigui/non assegnati senza perdita di dati.

