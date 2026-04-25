from memento.migrations.versions.v001_initial_schema import up as up_001
from memento.migrations.versions.v002_consolidation_log import up as up_002
from memento.migrations.versions.v003_kg_extraction import up as up_003
from memento.migrations.versions.v004_relevance_tracking import up as up_004
from memento.migrations.versions.v005_cross_workspace import up as up_005
from memento.migrations.versions.v007_performance_indexes import up as up_007
from memento.migrations.versions.v008_kg_schema import up as up_008
from memento.migrations.versions.v009_memory_tiers import up as up_009
from memento.migrations.versions.v010_sessions_handoff import up as up_010

def get_all_migrations():
    return [
        (1, "initial_schema", up_001),
        (2, "consolidation_log", up_002),
        (3, "kg_extraction", up_003),
        (4, "relevance_tracking", up_004),
        (5, "cross_workspace", up_005),
        (7, "performance_indexes", up_007),
        (8, "kg_schema", up_008),
        (9, "memory_tiers", up_009),
        (10, "sessions_handoff", up_010),
    ]
