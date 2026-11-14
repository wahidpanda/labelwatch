"""Unit-level diff between two versions of one label section (SPEC section 8, step B)."""

from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Literal

from rapidfuzz import fuzz

from app.ingest.normalize import hash_form

MODIFIED_THRESHOLD = 0.90

ChangeKind = Literal["added", "modified", "removed"]


@dataclass(frozen=True)
class UnitChange:
    kind: ChangeKind
    new: str | None
    old: str | None
    similarity: float


def similarity(a: str, b: str) -> float:
    return fuzz.ratio(hash_form(a), hash_form(b)) / 100.0


def diff_units(old: list[str], new: list[str]) -> list[UnitChange]:
    old_keys = [hash_form(u) for u in old]
    new_keys = [hash_form(u) for u in new]
    old_anywhere = set(old_keys)
    new_anywhere = set(new_keys)
    changes: list[UnitChange] = []
    matcher = SequenceMatcher(a=old_keys, b=new_keys, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        # Units that only moved elsewhere in the section are not changes.
        olds = [i for i in range(i1, i2) if old_keys[i] not in new_anywhere]
        news = [j for j in range(j1, j2) if new_keys[j] not in old_anywhere]
        used: set[int] = set()
        for j in news:
            best, best_score = None, 0.0
            for i in olds:
                if i in used:
                    continue
                score = fuzz.ratio(old_keys[i], new_keys[j]) / 100.0
                if score > best_score:
                    best, best_score = i, score
            if best is not None and best_score >= MODIFIED_THRESHOLD:
                used.add(best)
                changes.append(UnitChange("modified", new[j], old[best], best_score))
            else:
                changes.append(UnitChange("added", new[j], None, best_score))
        for i in olds:
            if i not in used:
                changes.append(UnitChange("removed", None, old[i], 0.0))
    return changes
