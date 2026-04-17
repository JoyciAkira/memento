from memento.migrations.versions.v001_initial_schema import up as up_001
from memento.migrations.versions.v002_consolidation_log import up as up_002

def get_all_migrations():
    return [
        (1, "initial_schema", up_001),
        (2, "consolidation_log", up_002),
    ]
