# Tasks
- [x] Task 1: Create entropy module for hubness detection
  - [x] SubTask 1.1: Implement `detect_dense_rooms` in `mempalace/entropy.py`
  - [x] SubTask 1.2: Add unit tests in `tests/test_entropy.py`
- [x] Task 2: Create crystallize module for intra-room PageRank
  - [x] SubTask 2.1: Implement `find_room_diamonds` in `mempalace/crystallize.py`
  - [x] SubTask 2.2: Add unit tests in `tests/test_crystallize.py`
- [x] Task 3: Create archive module for soft-archiving
  - [x] SubTask 3.1: Implement `archive_noise` in `mempalace/archive.py`
  - [x] SubTask 3.2: Update `knowledge_graph.py` if needed for `has_archive` triples
  - [x] SubTask 3.3: Add unit tests in `tests/test_archive.py`
- [x] Task 4: Update CLI and Searcher
  - [x] SubTask 4.1: Update `search_memories` in `mempalace/searcher.py` to support `deep` flag and exclude `archive` wing by default
  - [x] SubTask 4.2: Add `crystallize` command and `--deep` search flag to `mempalace/cli.py`
  - [x] SubTask 4.3: Ensure 100% tests pass and formatting is correct (ruff)

# Task Dependencies
- [Task 2] depends on [Task 1]
- [Task 3] depends on [Task 2]
- [Task 4] depends on [Task 3]