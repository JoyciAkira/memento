# Memento Beyond Memory Spec

## Why
I sistemi di memoria AI attuali (incluso Mem0) sono archivi passivi: aspettano di essere interrogati per fornire risposte. Memento (ex NeuroGraph) deve diventare il primo "Sistema Nervoso Autonomo" per l'AI. Per raggiungere la vera "Agenticità", Memento non deve limitarsi a ricordare, ma deve **agire proattivamente** per proteggere lo sviluppatore dai suoi stessi errori ciclici e organizzare il suo subconscio lavorativo in task azionabili.

## What Changes
- Creazione del modulo `Proactive Warnings`: intercetta il contesto corrente e genera allarmi ("senso di ragno") se rileva pattern negativi o bug già sperimentati nel passato (identificati come "Diamanti" di attenzione).
- Creazione del modulo `Auto-Generative Tasks`: un worker asincrono (o triggerato) che analizza i pensieri/frustrazioni sparsi nei log di memoria e genera file `.todo.md` (o task strutturati).
- Estensione del `MementoAccessManager` per supportare il toggle dinamico di questi "Superpoteri" (`toggle_proactive_warnings`, `toggle_auto_tasks`), mantenendo il totale controllo nelle mani dell'utente.
- Esposizione del tool `memento_get_warnings` per permettere all'IDE (Cursor/Claude) di leggere proattivamente i pericoli associati al contesto corrente.

## Impact
- Affected specs: Nessuna.
- Affected code:
  - `memento/mcp_server.py` (Aggiunta dei nuovi tool e toggle)
  - `memento/cognitive_engine.py` (Nuovo modulo per l'analisi proattiva e l'estrazione di warning/task dai "Diamanti")
  - `memento/access_manager.py` (Nuovi toggle)

## ADDED Requirements

### Requirement: Proactive Warnings ("Senso di Ragno")
Il sistema SHALL analizzare il contesto inviato dall'agente e restituire avvisi se ci sono conflitti noti o "memorie di dolore" nel grafo locale.

#### Scenario: Prevenire un errore noto
- **WHEN** l'agente inizia a scrivere codice che usa la libreria "TimezoneX" e interroga Memento
- **THEN** Memento estrae un Diamante negativo ("Daniele ha perso 3 ore su un bug UTC di TimezoneX") e spara un Proactive Warning all'agente.

### Requirement: Task Auto-Generativi ("Subconscio Organizzativo")
Il sistema SHALL tradurre flussi di pensieri o frustrazioni latenti (es. "questo file fa schifo, prima o poi lo refattorizzo") in Task formali.

#### Scenario: Da pensiero a Task
- **WHEN** l'utente attiva la generazione automatica dei task
- **THEN** Memento analizza i nodi isolati/orfani legati a debiti tecnici, li clusterizza tramite PageRank, e genera un file strutturato `.todo.md` nel workspace corrente.

### Requirement: Super-Toggle
Il sistema SHALL permettere di abilitare o disabilitare l'agenticità estrema in qualsiasi momento.

#### Scenario: Controllo utente
- **WHEN** l'utente chiama `memento_toggle_superpowers(warnings=False, auto_tasks=False)`
- **THEN** Memento smette di analizzare in background e ritorna a comportarsi come un "semplice" (ma potente) database cognitivo ibrido.