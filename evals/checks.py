"""
Scoring for Rambo's evaluation suite. Deterministic: every check reads Rambo's
answer and what its farmingdale.edu search results quoted. No second model
judges the first.
"""

from __future__ import annotations

import re

from apps.assistant.rambo import _MD_LINK, RamboResult

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


def linked_urls(result: RamboResult) -> list[str]:
    """Every farmingdale.edu page the answer links or cites."""
    urls = [url for _, url in _MD_LINK.findall(result.answer.text)]
    urls += [source.url for source in result.answer.sources]
    return [url for url in dict.fromkeys(urls) if "farmingdale.edu" in url]


def unsupported_specifics(
    result: RamboResult, history_text: str = "", pages: dict[str, str | None] | None = None
) -> tuple[list[str], list[str]]:
    """Phone numbers, emails, dollar amounts and years in the answer that appear
    on none of the farmingdale.edu pages Rambo linked (nor in his citations, the
    link addresses themselves, or earlier turns). A specific detail with nothing
    behind it is the hallucination that hurts: a student calls the number or
    pays the amount.

    Returns (problems, unverified): a detail that isn't on any page Rambo linked
    is a problem, unless one of his links couldn't be read (a PDF, or a failed
    fetch). Then it is only reported as unverified."""
    pages = pages or {}
    urls = linked_urls(result)
    readable = [pages[url] for url in urls if pages.get(url)]
    # Only a page we tried and failed to read excuses a detail. A page never
    # fetched is simply no evidence.
    unreadable = any(url in pages and pages[url] is None for url in urls)
    evidence = " ".join([*result.evidence, history_text, *urls, *readable])
    evidence_lower = evidence.lower()
    digits = re.sub(r"\D", "", evidence)

    text = result.answer.text
    found: list[tuple[str, bool]] = []
    for value in PHONE.findall(text):
        found.append((f"phone number {value}", re.sub(r"\D", "", value) in digits))
    # Phone numbers out of the way, so "934-420-2000" doesn't also read as the year 2000.
    rest = PHONE.sub(" ", text)
    for pattern, label in ((MONEY, "amount"), (EMAIL, "email"), (YEAR, "year")):
        for value in pattern.findall(rest):
            found.append((f"{label} {value}", value.lower() in evidence_lower))

    problems, unverified = [], []
    for label, ok in found:
        if ok:
            continue
        if unreadable:
            unverified.append(f"{label} (a linked page couldn't be read)")
        else:
            problems.append(f"{label} is on no page Rambo linked")
    return list(dict.fromkeys(problems)), list(dict.fromkeys(unverified))


def hallucination_problems(
    result: RamboResult,
    forbidden: list[str],
    history_text: str = "",
    pages: dict[str, str | None] | None = None,
) -> list[str]:
    """Everything in an answer that farmingdale.edu, as Rambo linked it, does not support."""
    text = result.answer.text
    problems = [f"says {term!r}" for term in forbidden if contains(text, term)]
    if result.answer.links_removed:
        problems.append(f"tried to link {result.answer.links_removed} page(s) off farmingdale.edu")
    problems += unsupported_specifics(result, history_text, pages)[0]
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
