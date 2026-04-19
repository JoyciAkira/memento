# Adaptive Retrieval v1 + Memory Lifecycle (Soft Delete + Goals Store) Spec

## Why
Memento deve migliorare la qualità del retrieval senza perdere controllabilità, e deve consentire di rendere obsolete (e nascondere) memorie superate, mantenendo un audit locale del perché.

## What Changes
- Introduzione di un retrieval adattivo v1 (query routing deterministico + pesi dinamici per lane + decay temporale), con tracing completo.
- Introduzione di soft delete per memorie con `delete_reason` e (opzionale) `supersedes_id`, escluso dal retrieval e dagli output standard.
- Introduzione di Goals “first-class” (archiviazione separata dalle memorie) con history e reason di sostituzione/archiviazione.
- Aggiornamento dell’injection goals (`get_active_goals`) per leggere dai goals first-class invece che da una search su “obiettivo goal”.

## Impact
- Affected specs: Retrieval, Observability, Safety, Goal Steering.
- Affected code (indicativo): `memento/provider.py`, `memento/retrieval/pipeline.py`, `memento/tools/*`, `memento/tools/utils.py`, test suite `tests/`.

## ADDED Requirements

### Requirement: Soft Delete Memorie (con motivazione)
Il sistema SHALL permettere di rendere una memoria “non attiva” tramite soft delete, senza perdere la motivazione della sostituzione.

#### Scenario: Soft delete con reason e sostituzione
- **WHEN** l’utente invoca un tool di soft delete su una memoria `id`, passando `delete_reason` e opzionalmente `supersedes_id`
- **THEN** la memoria viene marcata come deleted con timestamp e reason
- **AND THEN** la memoria non compare più nei risultati di retrieval standard (FTS, dense, recency, vNext bundle)
- **AND THEN** la memoria resta auditabile localmente (es. list deleted / explain), senza ri-emergere nei risultati standard

#### Scenario: Soft delete sicurezza
- **WHEN** access state è `read-only` o `lockdown`
- **THEN** le operazioni di soft delete SHALL essere bloccate

### Requirement: Goals First-Class (separati dalle memorie)
Il sistema SHALL gestire i goals come entità separate dalle memorie, con storia e sostituzioni.

#### Scenario: Set/Replace goals
- **WHEN** l’utente imposta una lista di goals attivi (eventualmente per contesto)
- **THEN** i goals precedenti vengono archiviati (non attivi) con `delete_reason` che spiega il cambio
- **AND THEN** `get_active_goals()` restituisce solo i goals attivi, in ordine coerente (es. più recenti prima)

#### Scenario: Goals non inquinano il retrieval memorie
- **WHEN** si esegue `memento_search_memory`
- **THEN** i goals non influenzano la ranking delle memorie (a meno di un boost esplicito in retrieval adattivo, tracciato)

### Requirement: Adaptive Retrieval v1 (routing + pesi dinamici + decay)
Il sistema SHALL adattare il retrieval in base al tipo di query con una strategia deterministica e tracciabile.

#### Scenario: Query code-like
- **WHEN** la query contiene pattern code-like (path, identifier, stacktrace, simboli)
- **THEN** il sistema aumenta il peso di FTS e riduce il peso di dense/recency

#### Scenario: Query episodic (recency-biased)
- **WHEN** la query indica esplicitamente timeframe recente (“ieri”, “oggi”, “ultimo commit”, ecc.)
- **THEN** il sistema aumenta il peso della lane recency con decay temporale esplicito

#### Scenario: Trace completo
- **WHEN** viene eseguita una search (legacy o vNext)
- **THEN** viene prodotto un trace che include: classificazione query, pesi per lane, top candidati per lane, lista finale e motivazione delle esclusioni (es. deleted)

## MODIFIED Requirements

### Requirement: Active goals injection
`get_active_goals(ctx, ...)` SHALL ottenere i goals da storage dedicato (goals first-class) invece che da una search su memorie “obiettivo goal”.

## REMOVED Requirements

### Requirement: Goals come memorie ricercate per keyword
**Reason**: La search su keyword genera drift (goals vecchi riemergono) e inquina il retrieval.
**Migration**: Tool di migrazione SHALL permettere di importare goals esistenti (se presenti come memorie) nello storage goals first-class, archiviandoli con reason.
