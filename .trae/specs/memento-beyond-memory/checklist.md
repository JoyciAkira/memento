# Verification Checklist

- [x] L'ambiente di test include la nuova architettura `memento/cognitive_engine.py`
- [x] Il tool MCP `memento_get_warnings(context)` intercetta pattern negativi conosciuti (es. "TimezoneX bug") se lo switch è su `True`
- [x] Il tool MCP `memento_generate_tasks()` genera fisicamente un file strutturato (es. `.todo.md`) basato sui "Diamanti" latenti di refactoring
- [x] I tool MCP `memento_get_warnings` e `memento_generate_tasks` restituiscono messaggi di blocco se i rispettivi switch sono disattivati (`toggle_superpowers(False, False)`)
- [x] Il README è aggiornato e spiega chiaramente la differenza tra il "MemPalace DB passivo" e il "Sistema Nervoso Autonomo" di Memento
