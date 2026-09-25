"""Evidence grading for web-grounded NEXO responses."""
from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True, slots=True)
class EvidenceGrade:
    grade: str
    citation_count: int
    source_count: int
    warnings: tuple[str, ...] = ()


def grade_evidence(response: str, sources: list[str]) -> EvidenceGrade:
    citations = [int(x) for x in re.findall(r"\[(\d{1,2})\]", response or "")]
    clean = [str(x).strip() for x in sources if str(x).strip()]
    warnings: list[str] = []
    if clean and not citations:
        warnings.append("web_sources_without_inline_citations")
    if citations and (min(citations) < 1 or max(citations) > len(clean)):
        warnings.append("citation_out_of_range")
    unique = tuple(dict.fromkeys(warnings))
    if not clean:
        grade = "NONE"
    elif unique:
        grade = "INVALID"
    elif citations:
        grade = "GROUNDED"
    else:
        grade = "SOURCE_ONLY"
    return EvidenceGrade(grade, len(citations), len(clean), unique)
