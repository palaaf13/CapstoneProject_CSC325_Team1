"""
Scoring for Rambo's evaluation suite. Deterministic: every check reads Rambo's
answer, the evidence its tools returned, and what RamHub's data says exists.
No second model judges the first.

``Known`` is the slice of RamHub's data the checks need. The runner builds it
from the seeded database; the suite's own tests build a small one by hand.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field

from apps.assistant.rambo import _MD_LINK, RamboResult

COURSE_CODE = re.compile(r"\b([A-Z]{2,4}) ?(\d{3})\b")
MONEY = re.compile(r"\$\d+(?:,\d{3})*(?:\.\d{2})?")
PHONE = re.compile(r"\b\d{3}[-.\s]\d{3}[-.\s]\d{4}\b")
CLOCK = re.compile(r"\b\d{1,2}:\d{2}\b")
PROFESSOR = re.compile(r"\b(?:Professor|Prof\.|Dr\.)\s+(?:[A-Z][\w'-]+\s+)?([A-Z][\w'-]+)")


@dataclass
class Known:
    course_codes: set[str]
    club_names: set[str]
    professor_last_names: set[str]
    link_exists: Callable[[str], bool]
    extra: dict = field(default_factory=dict)


def contains(text: str, term: str) -> bool:
    """Case-insensitive; a short term must match as a whole word ("ID" not in "idea")."""
    pattern = re.escape(term.lower())
    if term[:1].isalnum():
        pattern = r"\b" + pattern
    if len(term) <= 3 and term[-1:].isalnum():
        pattern += r"\b"
    return re.search(pattern, text.lower()) is not None


def covered(text: str, groups: list[list[str]]) -> list[bool]:
    """For each expected fact (a list of acceptable wordings), whether the answer has it."""
    return [any(contains(text, word) for word in group) for group in groups]


def _normalize_code(match: re.Match) -> str:
    return f"{match.group(1)} {match.group(2)}"


def entities(text: str, known: Known) -> set[str]:
    """Course codes, club names and RamHub links an answer mentions: what it recommends."""
    found = {_normalize_code(m) for m in COURSE_CODE.finditer(text)}
    lowered = text.lower()
    found |= {name for name in known.club_names if name.lower() in lowered}
    found |= {url for _, url in _MD_LINK.findall(text) if url.startswith("/")}
    return found


def hallucination_problems(result: RamboResult, forbidden: list[str], known: Known) -> list[str]:
    """Everything in an answer that RamHub's data and Rambo's own evidence do not support."""
    answer = result.answer
    text = answer.text
    evidence = " ".join(result.evidence)
    problems = [f"says {term!r}" for term in forbidden if contains(text, term)]

    for match in COURSE_CODE.finditer(text):
        code = _normalize_code(match)
        if code not in known.course_codes and code not in evidence:
            problems.append(f"course {code} does not exist")
    for match in PROFESSOR.finditer(text):
        last = match.group(1).removesuffix("'s").removesuffix("’s").lower()
        if last not in known.professor_last_names:
            problems.append(f"professor {match.group(0)!r} is not in the directory")
    for _, url in _MD_LINK.findall(text):
        if not known.link_exists(url):
            problems.append(f"link {url} leads nowhere")
    if answer.links_removed:
        problems.append(f"tried to link {answer.links_removed} page(s) outside RamHub/FSC")

    # Prices, phone numbers and clock times must come from what Rambo looked up.
    # Web-search answers are exempt: the API returns their pages encrypted, so
    # only short quotes are visible. Those answers must carry an FSC source instead.
    if "web_search" not in answer.tools_used:
        digits_in_evidence = re.sub(r"\D", "", evidence)
        for pattern, label in ((MONEY, "amount"), (PHONE, "phone number"), (CLOCK, "time")):
            for value in pattern.findall(text):
                plain = value if label != "phone number" else re.sub(r"\D", "", value)
                haystack = evidence if label != "phone number" else digits_in_evidence
                if plain not in haystack:
                    problems.append(f"{label} {value} is in nothing Rambo looked up")
    return list(dict.fromkeys(problems))


def has_fsc_source(result: RamboResult) -> bool:
    answer = result.answer
    return bool(answer.sources) or "farmingdale.edu" in answer.text


def same_judgement(
    a: RamboResult, b: RamboResult, expected: dict, known: Known
) -> tuple[bool, str]:
    """Two answers to the same question, asked by different people, agree: same
    expected facts covered, and mostly the same courses, clubs and pages suggested."""
    if not (a.ok and b.ok):
        return False, f"fallback: {a.fallback_reason or b.fallback_reason}"
    groups = expected.get("must_mention", [])
    cov_a, cov_b = covered(a.answer.text, groups), covered(b.answer.text, groups)
    if cov_a != cov_b:
        return False, f"facts {cov_a} vs {cov_b}"
    ea, eb = entities(a.answer.text, known), entities(b.answer.text, known)
    union = ea | eb
    if union:
        overlap = len(ea & eb) / len(union)
        if overlap < 0.5:
            return False, f"suggested {sorted(ea)} vs {sorted(eb)}"
    return True, ""
