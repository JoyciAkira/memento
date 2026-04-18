"""KG Auto-Extraction Engine — extracts entities and relationships from memory text."""

import asyncio
import hashlib
import json
import logging
from datetime import datetime
from typing import Any, Dict, List

import aiosqlite

logger = logging.getLogger(__name__)


class KGExtractionEngine:
    BATCH_SIZE = 10
    MAX_CHARS_PER_MEMORY = 500
    DEFAULT_CONFIDENCE = 0.7

    def __init__(self, db_path: str, kg, llm_client=None, model: str = "openai/gpt-4o-mini"):
        self.db_path = db_path
        self.kg = kg
        self.llm_client = llm_client
        self.model = model

    @staticmethod
    def _text_hash(text: str) -> str:
        return hashlib.sha256(text.encode()).hexdigest()

    async def get_unprocessed_memories(self, limit: int = 50) -> List[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT m.id, m.text
                FROM memories m
                LEFT JOIN kg_extraction_log kel ON kel.memory_id = m.id
                LEFT JOIN memory_meta mm ON mm.id = m.id
                WHERE kel.memory_id IS NULL
                  AND COALESCE(mm.is_deleted, 0) = 0
                ORDER BY m.created_at DESC
                LIMIT ?
                """,
                (limit,),
            )
            return [{"id": r["id"], "text": r["text"]} for r in await cursor.fetchall()]

    def _format_batch(self, memories: List[Dict[str, Any]]) -> str:
        lines = []
        for m in memories:
            text = m["text"][: self.MAX_CHARS_PER_MEMORY]
            lines.append(f'Memory [{m["id"]}]: "{text}"')
        return "\n".join(lines)

    def _parse_llm_response(self, raw: str) -> Dict[str, Any]:
        text = raw.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines)
        try:
            data = json.loads(text)
            if "extractions" not in data:
                return {"extractions": []}
            return data
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse LLM extraction response: {raw[:200]}")
            return {"extractions": []}

    def _apply_extraction(self, extraction: Dict[str, Any]) -> Dict[str, int]:
        entities_count = 0
        triples_count = 0
        for item in extraction.get("extractions", []):
            for ent in item.get("entities", []):
                name = ent.get("name", "").strip()
                etype = ent.get("type", "unknown")
                if name:
                    self.kg.add_entity(name, etype)
                    entities_count += 1
            for rel in item.get("relations", []):
                subj = rel.get("subject", "").strip()
                pred = rel.get("predicate", "").strip()
                obj = rel.get("object", "").strip()
                conf = float(rel.get("confidence", self.DEFAULT_CONFIDENCE))
                memory_id = item.get("memory_id", "")
                if subj and pred and obj:
                    self.kg.add_triple(
                        subj,
                        pred,
                        obj,
                        confidence=conf,
                        source_closet=memory_id,
                    )
                    triples_count += 1
        return {"entities": entities_count, "triples": triples_count}

    async def _mark_processed(
        self,
        memory_id: str,
        text: str,
        entities_found: int,
        triples_found: int,
        error: str = None,
    ):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO kg_extraction_log
                (memory_id, memory_text_hash, extracted_at, entities_found, triples_found, extraction_error, llm_model)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    memory_id,
                    self._text_hash(text),
                    datetime.now().isoformat(),
                    entities_found,
                    triples_found,
                    error,
                    self.model,
                ),
            )
            await db.commit()

    async def extract_batch(self, memories: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not self.llm_client:
            return {"extractions": [], "error": "LLM not configured"}

        memories_text = self._format_batch(memories)

        from memento.prompts.registry import load_prompt

        prompt_data = load_prompt("kg_extract_triples")
        system_prompt = prompt_data.get("system_prompt", "")
        user_template = prompt_data.get("user_prompt_template", "")
        user_prompt = user_template.replace("{memories_text}", memories_text)

        try:
            response = await self.llm_client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.1,
            )
            raw = response.choices[0].message.content or ""
            return self._parse_llm_response(raw)
        except Exception as e:
            logger.error(f"LLM extraction error: {e}")
            return {"extractions": [], "error": str(e)}

    async def run_extraction_cycle(self, max_memories: int = 50) -> Dict[str, Any]:
        if not self.llm_client:
            return {"processed": 0, "entities": 0, "triples": 0, "batches": 0, "error": "LLM not configured"}

        memories = await self.get_unprocessed_memories(limit=max_memories)
        if not memories:
            return {"processed": 0, "entities": 0, "triples": 0, "batches": 0}

        chunks = [memories[i : i + self.BATCH_SIZE] for i in range(0, len(memories), self.BATCH_SIZE)]

        total_entities = 0
        total_triples = 0
        total_processed = 0

        for chunk in chunks:
            extraction = await self.extract_batch(chunk)
            error = extraction.get("error")

            def _apply():
                return self._apply_extraction(extraction)

            counts = await asyncio.to_thread(_apply)
            total_entities += counts["entities"]
            total_triples += counts["triples"]

            chunk_ids = {m["id"]: m["text"] for m in chunk}
            for mid, text in chunk_ids.items():
                await self._mark_processed(mid, text, 0, 0, error)
                total_processed += 1

        return {
            "processed": total_processed,
            "entities": total_entities,
            "triples": total_triples,
            "batches": len(chunks),
        }
