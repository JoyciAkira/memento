from memento.migrations.versions.v001_initial_schema import up as up_001
from memento.migrations.versions.v002_consolidation_log import up as up_002
from memento.migrations.versions.v003_kg_extraction import up as up_003

def get_all_migrations():
    return [
        (1, "initial_schema", up_001),
        (2, "consolidation_log", up_002),
        (3, "kg_extraction", up_003),
    ]
