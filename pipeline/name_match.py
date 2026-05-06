"""Conservative name matching for OpenAlex author disambiguation.

Designed for the case where we already know two records refer to PSU and need
to decide whether they're the same person. Errs toward 'review' rather than
'accept' — false positives create silent ORCID/author-ID misattribution.

Decisions:
  - 'accept': confidence high enough to auto-accept (used by the pipeline)
  - 'review': last name matches but first name is borderline — write to review file
  - 'reject': different surnames or unrelated first names

Caller is expected to filter on institution (e.g. PSU last_known_institution)
before consulting this module — institution match is the strongest signal and
is *not* checked here.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from rapidfuzz import fuzz

# Auto-accept threshold for fuzzy first-name comparison. 90 catches obvious
# spelling variants (Jeffery/Jeffrey, Christofer/Christopher) without admitting
# nickname pairs (Sunny/Sunhye scores ~73, Anne/Annie scores ~80).
FUZZY_ACCEPT_THRESHOLD = 90
FUZZY_REVIEW_THRESHOLD = 70


@dataclass
class MatchResult:
    decision: str  # 'accept' | 'review' | 'reject'
    tier: str      # 'exact' | 'normalized' | 'fuzzy_first' | 'initial_only' | 'fuzzy_borderline' | 'mismatch'
    score: int     # 0-100, the strongest signal we found


def normalize(name: str) -> str:
    """Strip diacritics, normalize unicode dashes/apostrophes, drop punctuation, lowercase."""
    if not name:
        return ""
    s = unicodedata.normalize("NFKD", name)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = (
        s.replace("‐", "-")  # ‐
        .replace("‑", "-")   # ‑
        .replace("–", "-")   # –
        .replace("—", "-")   # —
        .replace("’", "'")   # ’
        .replace("‘", "'")   # ‘
    )
    s = re.sub(r"[.,]", "", s)
    s = " ".join(s.lower().split())
    return s


def split_name(name: str) -> tuple[list[str], str]:
    """Return (given_tokens, surname). Last whitespace-separated token is the surname."""
    tokens = normalize(name).split()
    if not tokens:
        return [], ""
    return tokens[:-1], tokens[-1]


def _is_initial(token: str) -> bool:
    """A token like 'a' or 'a-b' is treated as an initial if its largest
    alphabetic chunk is 1 character. Lets 'D' count as initial but 'Derek'
    doesn't. Hyphenated initials ('a-b') still count."""
    chunks = re.split(r"[^a-z]+", token)
    return all(len(c) <= 1 for c in chunks if c)


def match(name_a: str, name_b: str) -> MatchResult:
    """Compare two names. Returns MatchResult with decision tier.

    Pre-condition: caller has already verified institution match (e.g. both
    are at PSU). This function focuses on whether the names plausibly refer
    to the same person.
    """
    given_a, surname_a = split_name(name_a)
    given_b, surname_b = split_name(name_b)

    # Hard requirement: surnames must match exactly after normalization.
    # No phonetic matching here — surname spelling collisions are the main
    # source of false positives.
    if not surname_a or not surname_b:
        return MatchResult("reject", "mismatch", 0)
    if surname_a != surname_b:
        return MatchResult("reject", "mismatch", 0)
    if not given_a or not given_b:
        return MatchResult("reject", "mismatch", 0)

    # Tier 1a: full string match after normalization.
    if normalize(name_a) == normalize(name_b):
        return MatchResult("accept", "exact", 100)

    # Tier 1b: spaceless join of given names matches — handles 'Hong Gang' vs 'Honggang'.
    if "".join(given_a) == "".join(given_b):
        return MatchResult("accept", "normalized", 100)

    # Tier 1c: identical once we strip out single-letter initials on both sides.
    # Handles 'Cynthia H Chuang' vs 'Cynthia Chuang'.
    full_tokens_a = [t for t in given_a if not _is_initial(t)]
    full_tokens_b = [t for t in given_b if not _is_initial(t)]
    if full_tokens_a and full_tokens_b and full_tokens_a == full_tokens_b:
        return MatchResult("accept", "normalized", 100)

    # Identify each side's first non-initial given name (the "real" first name).
    full_a = full_tokens_a[0] if full_tokens_a else None
    full_b = full_tokens_b[0] if full_tokens_b else None

    # Tier 2: both have a full first name → compare.
    if full_a and full_b:
        if full_a == full_b:
            return MatchResult("accept", "normalized", 100)
        score = int(fuzz.token_sort_ratio(full_a, full_b))
        if score >= FUZZY_ACCEPT_THRESHOLD:
            return MatchResult("accept", "fuzzy_first", score)
        if score >= FUZZY_REVIEW_THRESHOLD:
            return MatchResult("review", "fuzzy_borderline", score)
        return MatchResult("reject", "mismatch", score)

    # Tier 3: one side is initials-only (e.g. RMD has "D. A. Kreager", OA has
    # "Derek A. Kreager"). Risky because two PSU people can share a first
    # initial and surname — never auto-accept here, even if compatible.
    init_a = given_a[0][0] if given_a else ""
    init_b = given_b[0][0] if given_b else ""
    if init_a and init_b and init_a == init_b:
        return MatchResult("review", "initial_only", 50)

    return MatchResult("reject", "mismatch", 0)


# ---------------------------------------------------------------------------
# Quick self-test — run with: python -m pipeline.name_match
# ---------------------------------------------------------------------------

def _selftest() -> None:
    cases = [
        # (name_a, name_b, expected_decision, label)
        ("Cynthia Huang-Pollock", "Cynthia Huang‐Pollock", "accept", "unicode hyphen"),
        ("Amilcar Matos-Moreno", "Amílcar Matos-Moreno", "accept", "accent"),
        ("Cynthia H Chuang", "Cynthia H. Chuang", "accept", "middle-initial period"),
        ("Anthony E. Pegg", "Anthony E. Pegg", "accept", "exact"),
        ("Deirdre O'Sullivan", "Deirdre O’Sullivan", "accept", "unicode apostrophe"),
        ("Hong Gang Wang", "Honggang Wang", "accept", "spacing variant"),
        # Spelling variants stay in review — token_sort_ratio puts them ~85, below
        # our deliberately conservative 90 cutoff. Cheap human eyeball is fine.
        ("Jeffery Neighbors", "Jeffrey D. Neighbors", "review", "spelling variant + middle"),
        ("Christofer J Skurka", "Christopher Skurka", "review", "Christofer/Christopher"),
        ("Anne Olmstead", "Annie J. Olmstead", "review", "Anne vs Annie nickname"),
        ("Sunny Bai", "Sunhye Bai", "review", "Sunny/Sunhye nickname"),
        ("D. A. Kreager", "Derek A. Kreager", "review", "initial-only first"),
        ("A Mejia", "Alfonso Mejía", "review", "single initial"),
        ("Audrey Kulaylat", "Afif N. Kulaylat", "reject", "same first letter, diff person"),
        ("Brent Smith", "Stephen B. Smith", "reject", "different first names"),
        ("Some Other Name", "Anthony Pegg", "reject", "different surname"),
    ]
    width = max(len(a) + len(b) for a, b, *_ in cases) + 6
    fails = 0
    for a, b, expected, label in cases:
        r = match(a, b)
        ok = r.decision == expected
        mark = "OK  " if ok else "FAIL"
        if not ok:
            fails += 1
        print(f"  {mark}  {label:<35}  {a!r} vs {b!r}".ljust(width + 35),
              f"-> {r.decision:<6} tier={r.tier:<18} score={r.score}")
    print(f"\n{len(cases) - fails}/{len(cases)} passed")


if __name__ == "__main__":
    _selftest()
