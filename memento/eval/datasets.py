from __future__ import annotations

import json
import os
from typing import Any


class EvalCase:
    __slots__ = ("query", "expected_ids", "notes")

    def __init__(self, query: str, expected_ids: list[str], notes: str = ""):
        self.query = query
        self.expected_ids = expected_ids
        self.notes = notes


class EvalSet:
    __slots__ = ("name", "cases")

    def __init__(self, name: str, cases: list[EvalCase] | None = None):
        self.name = name
        self.cases = cases or []

    def add_case(self, query: str, expected_ids: list[str], notes: str = "") -> None:
        self.cases.append(EvalCase(query=query, expected_ids=expected_ids, notes=notes))

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "cases": [
                {"query": c.query, "expected_ids": c.expected_ids, "notes": c.notes}
                for c in self.cases
            ],
        }

    def save(self, path: str) -> None:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)

    @classmethod
    def load(cls, path: str) -> EvalSet:
        with open(path) as f:
            data = json.load(f)
        cases = [
            EvalCase(query=c["query"], expected_ids=c["expected_ids"], notes=c.get("notes", ""))
            for c in data["cases"]
        ]
        return cls(name=data["name"], cases=cases)
