"""Project Memory Graph: semantic relationships between project entities using the existing KG."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

logger = logging.getLogger("memento-pmg")


class ProjectMemoryGraph:
    """
    Wraps the existing MementoGraphProvider to provide project-level semantic relationships.
    Entities: files, components, decisions, bug_fixes, features, sessions.
    Relations: depends_on, blocks, implements, breaks, supersedes, relates_to.
    """

    def __init__(self, kg_provider: Any):
        self.kg = kg_provider

    async def add_entity(
        self,
        name: str,
        entity_type: str,
        properties: dict[str, Any] | None = None,
    ) -> bool:
        props = properties or {}
        props["entity_type"] = entity_type
        props["updated_at"] = datetime.now().isoformat()
        try:
            await self.kg.add_triple(
                subject=name,
                predicate="is_a",
                object_=entity_type,
                metadata=json.dumps(props),
            )
            return True
        except Exception as e:
            logger.warning(f"Failed to add entity {name}: {e}")
            return False

    async def add_relation(
        self,
        subject: str,
        predicate: str,
        object_: str,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        meta = metadata or {}
        meta["added_at"] = datetime.now().isoformat()
        try:
            await self.kg.add_triple(
                subject=subject,
                predicate=predicate,
                object_=object_,
                metadata=json.dumps(meta),
            )
            return True
        except Exception as e:
            logger.warning(f"Failed to add relation {subject} {predicate} {object_}: {e}")
            return False

    async def get_entity_context(self, entity_name: str, depth: int = 1) -> str:
        """Get a summary of an entity and its direct relationships."""
        try:
            triples = await self.kg.query(subject=entity_name)
            if not triples:
                return f"No context found for entity: {entity_name}"

            lines = [f"[ENTITY CONTEXT: {entity_name}]"]
            seen = set()
            for t in triples:
                s = t.get("subject", "")
                p = t.get("predicate", "")
                o = t.get("object", "")
                key = f"{s}-{p}-{o}"
                if key not in seen:
                    seen.add(key)
                    lines.append(f"  {s} --{p}--> {o}")

            if depth > 1:
                for t in triples:
                    obj = t.get("object", "")
                    if obj and obj != entity_name:
                        sub_triples = await self.kg.query(subject=obj)
                        for st in sub_triples[:5]:
                            s2 = st.get("subject", "")
                            p2 = st.get("predicate", "")
                            o2 = st.get("object", "")
                            key2 = f"{s2}-{p2}-{o2}"
                            if key2 not in seen:
                                seen.add(key2)
                                lines.append(f"    {s2} --{p2}--> {o2}")

            return "\n".join(lines)
        except Exception as e:
            logger.warning(f"Failed to get entity context: {e}")
            return ""

    async def get_what_might_break(self, entity_name: str) -> list[str]:
        """Find entities that depend on the given entity."""
        try:
            triples = await self.kg.query(object_=entity_name, predicate="depends_on")
            return [t.get("subject", "") for t in triples if t.get("subject")]
        except Exception:
            return []

    async def get_project_summary(self, limit: int = 20) -> str:
        """Get a summary of all project entities and their relationships."""
        try:
            all_triples = await self.kg.query(limit=limit * 3)
            if not all_triples:
                return "No project memory graph data found."

            entity_types = {}
            relations = []
            for t in all_triples:
                s = t.get("subject", "")
                p = t.get("predicate", "")
                o = t.get("object", "")

                if p == "is_a":
                    entity_types.setdefault(o, []).append(s)
                elif p != "is_a":
                    relations.append(f"{s} --{p}--> {o}")

            lines = ["[PROJECT MEMORY GRAPH]"]
            for etype, entities in sorted(entity_types.items()):
                lines.append(f"  {etype}: {', '.join(entities[:10])}")
            if relations:
                lines.append(f"\n  Recent relations ({len(relations)}):")
                for r in relations[:15]:
                    lines.append(f"    {r}")

            return "\n".join(lines)
        except Exception as e:
            logger.warning(f"Failed to get project summary: {e}")
            return ""
