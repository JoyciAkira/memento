# Design Doc: Memento Conscientia (vNext) - The Neuro-Symbolic Active Memory Engine

## 1. Obiettivo e North Star
Ridefinire lo standard globale della memoria per AI Agents (superando RAG e vector DB tradizionali) attraverso un'architettura basata su **Active Inference** e **Vector Symbolic Architectures (VSA)**. L'obiettivo è risolvere il *catastrophic forgetting* e il *memory bloat* con rigore matematico, garantendo O(1) in composizione logica, ritenzione guidata dalla "sorpresa" (minimizzazione dell'energia libera) e latenza di retrieval deterministica.

Nessuna narrativa, solo ingegneria estrema: il sistema deve essere falsificabile, verificabile formalmente e dominare i benchmark di Continuous Learning (es. LifelongAgentBench).

## 2. Architettura a Triplo Orologio (Ispirazione: Nested Learning / HOPE 2025)
La memoria abbandona il modello "piatto" per adottare un ciclo di consolidamento a 3 velocità (Fast, Medium, Slow), prevenendo la sovrascrittura distruttiva e garantendo efficienza di allocazione:

1. **Fast Memory (L1 - Millisecondi)**: Il contesto immediato. Puramente in-memory, gestisce lo stato dell'azione corrente. Nessun I/O su disco.
2. **Medium Memory (L2 - Episodic / Experience)**: Log delle traiettorie agentiche e variazioni di stato. Utilizza **VSA (Hyperdimensional Computing)** per comprimere le traiettorie in ipervettori sparsi ad alta efficienza.
3. **Slow Memory (L3 - Semantic / World)**: Regole architetturali, invarianti di progetto, credenze cristallizzate. Resiste agli aggiornamenti (integra, non cancella). Salvato su SQLite (WAL mode, lock separati per read/write).

## 3. Ritenzione Guidata dalla Sorpresa (Active Inference)
Per azzerare i "memory leak" cognitivi (database gonfi di log inutili), Memento implementa la ritenzione guidata dal *Free Energy Principle* (Friston / AXIOM):
- **Predictive Coding**: L'agente genera un'aspettativa sull'output di un'azione.
- **Surprise Calculation**: Se il risultato coincide con l'aspettativa, l'evento **non viene memorizzato** (scarto automatico, risparmio I/O).
- **Update**: Se c'è un "prediction error" (sorpresa), l'evento viene consolidato. Memorizziamo solo ciò che altera il modello del mondo.

## 4. Retrieval Neuro-Simbolico via VSA (Vector Symbolic Architectures)
Sostituiamo la similarità coseno O(n²) e il costoso attraversamento dei grafi (N+1 query) con l'algebra degli ipervettori (HDC - Hyperdimensional Computing).
- Le entità e le relazioni del Knowledge Graph vengono mappate in vettori binari ortogonali (es. 10.000 dimensioni).
- **Binding (⊗)** e **Bundling (⊕)** permettono di risolvere query complesse (es. "Qual è il framework preferito dall'utente per il frontend?") con singole operazioni algebriche `O(1)`, senza richiamare l'LLM.
- **Formal Verification**: L'algebra VSA garantisce matematicamente il recupero esatto dei costituenti, rendendo il retrieval formalmente verificabile e deterministico.

## 5. Metacognitive Reflector (Il "300 IQ")
Un demone di background che implementa il ciclo *Monitor -> Evaluate -> Regulate* (ispirato a Metagent-P):
- Valuta l'incertezza (confidence score) dei risultati di retrieval VSA.
- Se l'incertezza supera una soglia, innesca una *Self-Reflective Query* per espandere il contesto prima che l'agente esegua codice.
- Trasforma dinamicamente le deduzioni L2 (Esperienze) in regole L3 (Slow Memory) tramite consolidamento asincrono.

## 6. Memory Manager & Constraints (Hard Engineering)
- **Zero-Allocation Hot Paths**: Le operazioni di algebra VSA saranno implementate via `numpy`/C-extensions per evitare overhead del garbage collector in Python.
- **Thread-Safety & ACID**: Connessioni SQLite rigorosamente isolate per letture e scritture. Nessun lock tenuto durante l'inferenza LLM o calcoli VSA.
- **Active Coercion Integrata**: Le regole cristallizzate in Slow Memory diventano automaticamente hook deterministici (AST/Regex) che bloccano commit o esecuzioni errate.

## 7. Roadmap di Implementazione
1. **Fase 1 (Foundation)**: Refactoring di `NeuroGraphProvider` in 3 moduli isolati (L1, L2, L3) e introduzione dello schema DB per l'Episodic/Semantic split.
2. **Fase 2 (Neuro-Symbolic)**: Sostituzione della cosine similarity con un motore VSA (Hyperdimensional Computing) per binding relazionale O(1).
3. **Fase 3 (Active Inference)**: Implementazione del `Metacognitive Reflector` e logica di ritenzione basata sulla "sorpresa" (calcolo dell'errore di predizione).
4. **Fase 4 (Benchmark)**: Validazione formale e stress test contro benchmark di Continuous Learning.
