def test_room_centroids():
    from mempalace.knowledge_graph import KnowledgeGraph
    kg = KnowledgeGraph(db_path=":memory:")
    kg.add_room("engineering", [0.1, 0.2, 0.3])
    rooms = kg.get_all_rooms()
    assert "engineering" in [r["name"] for r in rooms]
    assert rooms[0]["centroid"] == [0.1, 0.2, 0.3]
