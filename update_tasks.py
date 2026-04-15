with open('.trae/specs/dependency-tracker/tasks.md', 'r') as f:
    content = f.read()

content = content.replace(
    "- [ ] Task 2: Scanner AST e Modulo Principale\n  - [ ] Creare `memento/dependency_tracker.py`.",
    "- [x] Task 2: Scanner AST e Modulo Principale\n  - [x] Creare `memento/dependency_tracker.py`."
)
content = content.replace(
    "  - [ ] Sviluppare uno scanner asincrono",
    "  - [x] Sviluppare uno scanner asincrono"
)
content = content.replace(
    "  - [ ] Visitare l'AST per intercettare",
    "  - [x] Visitare l'AST per intercettare"
)
content = content.replace(
    "  - [ ] Creare un set unificato di tutti gli import",
    "  - [x] Creare un set unificato di tutti gli import"
)
content = content.replace(
    "- [ ] Task 3: Risoluzione Manifest vs AST (Name Mapping)\n  - [ ] Sviluppare una funzione per leggere il file `pyproject.toml`",
    "- [x] Task 3: Risoluzione Manifest vs AST (Name Mapping)\n  - [x] Sviluppare una funzione per leggere il file `pyproject.toml`"
)
content = content.replace(
    "  - [ ] Utilizzare `importlib.metadata` per fare un mapping",
    "  - [x] Utilizzare `importlib.metadata` per fare un mapping"
)
content = content.replace(
    "  - [ ] Creare la logica di calcolo delle differenze:",
    "  - [x] Creare la logica di calcolo delle differenze:"
)
content = content.replace(
    "  - [ ] Identificare `orphans`",
    "  - [x] Identificare `orphans`"
)
content = content.replace(
    "  - [ ] Scrivere unit test per lo scanner AST",
    "  - [x] Scrivere unit test per lo scanner AST"
)
content = content.replace(
    "  - [ ] Scrivere test per il mapping e la classificazione `orphans` / `ghosts`.",
    "  - [x] Scrivere test per il mapping e la classificazione `orphans` / `ghosts`."
)

with open('.trae/specs/dependency-tracker/tasks.md', 'w') as f:
    f.write(content)
