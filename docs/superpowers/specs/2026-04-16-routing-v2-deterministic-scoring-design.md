# Routing v2 Deterministico (Score-Based) — Design

**Obiettivo:** migliorare il routing del retrieval vNext rendendolo più robusto su query miste (codice + descrizione + incident/debug) tramite scoring deterministico, pesi lane continui e parametri espliciti (es. `tau_days` per recency), con tracing completo e test riproducibili.

## Contesto
Lo stato attuale usa una classificazione “a classi” (code_like / episodic / generic) con pesi predefiniti e poche regole. Questo porta a:
- misclassificazioni su query miste (es. error codes + testo),
- eccesso di FTS o eccesso di recency in casi borderline,
- difficoltà di tuning (manca un profilo di segnali chiaro e confrontabile).

Il design qui proposto mantiene tutto **deterministico** (regex + conteggi + funzioni matematiche con clamp), e rende ogni decisione spiegabile tramite trace.

## Non-Goals (in questa iterazione)
- Nessun modello ML/LLM per routing (no chiamate esterne, no training).
- Nessun reranker aggiuntivo.
- Nessun cambio di storage embeddings (resta com’è).
- Nessuna modifica al retrieval legacy, solo vNext.

## Architettura (alto livello)
Il routing v2 è una funzione pura:

1) `extract_signals(query) -> signals`  
2) `route_from_signals(signals) -> routing_decision`  
3) `retrieve_bundle()` usa `routing_decision` per:
   - `lane_weights` (FTS/dense/recency)
   - parametri `tau_days` per lane recency
   - (opzionale) `k_rrf` se in futuro
4) Il bundle include un oggetto `routing` con:
   - `version`
   - `signals`
   - `lane_weights`
   - `recency_tau_days`
   - `confidence`
   - `fallback` (se applicata)

## Routing v2 — Dettagli

### Signals (0..1)
Tutti i segnali sono normalizzati in `[0, 1]`.

#### `code_score`
Obiettivo: riconoscere query con forte presenza di elementi “code-like”.

Evidenze:
- file path: `([A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+`
- estensioni: `.py .ts .js .go .rs .java .kt .cpp .h .md`
- token operator-like: `::`, `->`, `()`
- identificatori lunghi: `[A-Za-z_][A-Za-z0-9_]{6,}`
- stacktrace-ish: `File "…", line …` / `Traceback` / `at Foo.bar(Foo.java:123)`

Normalizzazione (deterministica):
- somma pesata di feature booleane + feature “count” troncate a un massimo,
- poi clamp in `[0,1]`.

#### `time_score`
Obiettivo: riconoscere intenti “episodic/recent”.

Evidenze:
- parole: `ieri`, `oggi`, `stamattina`, `recent`, `yesterday`, `today`, `ultim`, `last`
- pattern: `last \d+ (days|weeks|months)` / `ultimi \d+ (giorni|settimane|mesi)`

Normalizzazione:
- match keyword => boost,
- match numerico => boost addizionale,
- clamp `[0,1]`.

#### `incident_score`
Obiettivo: riconoscere query incident/debug (error code, failure).

Evidenze:
- pattern “Error code” / “code:” con numero
- numero a 3–5 cifre isolato (es. `3003`) con contesto error-like
- parole: `error`, `failed`, `exception`, `traceback`, `stacktrace`, `timeout`, `rate limit`

Normalizzazione:
- keyword fail/error => boost,
- codice numerico con contesto => boost maggiore,
- clamp `[0,1]`.

#### `nl_score`
Obiettivo: riconoscere query “natural language” generiche (spiegazioni, domande).

Evidenze:
- lunghezza parole (più lunga = più NL)
- presenza interrogativi: `come`, `perché`, `spieg`, `how`, `why`, `explain`
- densità simboli bassa (pochi `/:(){}[]`)

Normalizzazione:
- combinazione di:
  - `word_count_score` (saturazione oltre una soglia)
  - `question_word_score`
  - `symbol_density_penalty`
- clamp `[0,1]`.

### Confidence e fallback
`confidence = max(code_score, time_score, incident_score, nl_score)`

Se `confidence < 0.25`:
- `fallback = true`
- si applicano pesi “default” (equivalenti a routing v1 generic) per evitare tuning aggressivo su query troppo corte/ambigue.

### Lane weights (continui, deterministici)
Produciamo pesi continui e clampati, evitando estremi:
- `fts_weight = clamp(1.0 + 0.9*code_score + 0.6*incident_score - 0.4*time_score, 0.2, 2.0)`
- `dense_weight = clamp(1.0 + 0.7*nl_score + 0.5*incident_score - 0.5*code_score, 0.2, 2.0)`
- `recency_weight = clamp(0.5 + 1.2*time_score - 0.4*code_score + 0.2*incident_score, 0.1, 2.0)`

Interpretazione:
- code-like → FTS sale, dense scende un po’, recency scende
- episodic → recency sale e `tau_days` si accorcia
- incident/debug → FTS + dense salgono insieme (match + semantica)
- NL generico → dense sale

### Recency tau_days (deterministico)
`tau_days = clamp(30 - 23*time_score + 40*code_score, 3, 120)`

Interpretazione:
- episodic → `tau_days` basso (recency molto “stretta”)
- code-like → `tau_days` più alto (non penalizzare troppo info storiche su codice)

## Tracing / Explainability
Nel `ContextBundle` vNext, `routing` SHALL includere:

```json
{
  "version": 2,
  "signals": {
    "code": 0.0,
    "time": 0.0,
    "incident": 0.0,
    "nl": 0.0
  },
  "confidence": 0.0,
  "fallback": false,
  "lane_weights": { "fts": 1.0, "dense": 1.0, "recency": 0.5 },
  "recency_tau_days": 30.0
}
```

Il tool `memento_explain_retrieval` deve mostrare almeno `routing` + `traces`.

## Test Plan (deterministico, riproducibile)

### Unit tests segnali
Testare che:
- query con path/estensione -> `code_score` > 0.7
- query con “ieri/oggi/last” -> `time_score` > 0.7
- query con “Error 3003 Model Request failed” -> `incident_score` > 0.7 e `fts_weight` >= `dense_weight` (o comunque entrambi aumentati rispetto al default)
- query lunga “spiegami come…” -> `nl_score` > 0.6 e `dense_weight` > `fts_weight` (salvo code markers)

### Integration tests routing
Testare che `retrieve_bundle(..., trace=True)` ritorni `routing.version==2` e che i pesi rispettino invarianti:
- `fts_weight` più alto per query code-like che per generic
- `recency_weight` più alto per query episodic che per generic
- `tau_days` più basso per episodic che per generic

## Rollout / Compatibilità
- Nessuna breaking change per tool legacy: `memento_search_memory` continua a funzionare.
- vNext: `memento_search_vnext` e `memento_explain_retrieval` tornano `routing` aggiornato.
- `routing.version` permette future evoluzioni senza ambiguità.

## Sicurezza e determinismo
- Nessuna chiamata esterna per routing.
- Nessun uso di randomness.
- Output tracciato e testato: ogni regressione sul routing è riproducibile.
