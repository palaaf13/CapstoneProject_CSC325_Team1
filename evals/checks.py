"""
Scoring for Rambo's evaluation suite. Deterministic: every check reads Rambo's
answer and what its farmingdale.edu search results quoted. No second model
judges the first.
"""

from __future__ import annotations

import re

from apps.assistant.rambo import RamboResult

MONEY = re.compile(r"\$\d+(?:,\d{3})*(?:\.\d{2})?")
PHONE = re.compile(r"\(?\b\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}\b")
EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")
YEAR = re.compile(r"\b(?:18|19|20)\d{2}\b")


def contains(text: str, term: str) -> bool:
    """Case-insensitive, whole words at both ends, so "Division II" does not
    match "Division III" and "Ram" does not match "program"."""
    pattern = re.escape(term.lower())
    if term[:1].isalnum():
        pattern = r"\b" + pattern
    if term[-1:].isalnum():
        pattern += r"\b"
    return re.search(pattern, text.lower()) is not None


def covered(text: str, groups: list[list[str]]) -> list[bool]:
    """For each expected fact (a list of acceptable wordings), whether the answer has it."""
    return [any(contains(text, word) for word in group) for group in groups]


def has_fsc_source(result: RamboResult) -> bool:
    """The answer points at farmingdale.edu: a citation, or a link in the text."""
    return bool(result.answer.sources) or "farmingdale.edu" in result.answer.text


def unsupported_specifics(result: RamboResult, history_text: str = "") -> list[str]:
    """Prices, phone numbers, emails and years in the answer that no search
    result Rambo cited (and nothing earlier in the conversation) contains.
    A specific detail with nothing behind it is the hallucination that hurts:
    a student calls the number or pays the amount."""
    evidence = " ".join([*result.evidence, history_text])
    digits = re.sub(r"\D", "", evidence)
    problems = []
    for value in PHONE.findall(result.answer.text):
        if re.sub(r"\D", "", value) not in digits:
            problems.append(f"phone number {value} is in no cited source")
    for pattern, label in ((MONEY, "amount"), (EMAIL, "email"), (YEAR, "year")):
        for value in pattern.findall(result.answer.text):
            if value.lower() not in evidence.lower():
                problems.append(f"{label} {value} is in no cited source")
    return problems


def hallucination_problems(
    result: RamboResult, forbidden: list[str], history_text: str = ""
) -> list[str]:
    """Everything in an answer that farmingdale.edu, as Rambo cited it, does not support."""
    text = result.answer.text
    problems = [f"says {term!r}" for term in forbidden if contains(text, term)]
    if result.answer.links_removed:
        problems.append(f"tried to link {result.answer.links_removed} page(s) off farmingdale.edu")
    problems += unsupported_specifics(result, history_text)
    return list(dict.fromkeys(problems))


def same_judgement(a: RamboResult, b: RamboResult, expected: dict) -> tuple[bool, str]:
    """Two students asking the same thing get the same substance: both answered,
    the same expected facts, and both (or neither) cite farmingdale.edu."""
    if not (a.ok and b.ok):
        return False, f"fallback: {a.fallback_reason or b.fallback_reason}"
    groups = expected.get("must_mention", [])
    cov_a, cov_b = covered(a.answer.text, groups), covered(b.answer.text, groups)
    if cov_a != cov_b:
        return False, f"facts {cov_a} vs {cov_b}"
    if has_fsc_source(a) != has_fsc_source(b):
        return False, "only one cites farmingdale.edu"
    return True, ""
