"""
Shared helpers for active-substance handling.

This module centralises the two operations that were previously duplicated
(and inconsistent) between ``active_substance_external_resolver`` and
``clinical_variants_lookup``:

  * ``normalize``          - accent/case/whitespace-insensitive form
  * ``split_substances``   - break a combination product ("x + y") into its
                             individual active substances

Keeping a single implementation matters: 122 of the 643 RCMs in the corpus
(19%) carry a combination active substance, and ClinPGx guideline annotations
list drugs *individually* in ``relatedChemicals``. A combination therefore only
cross-references correctly if it is split the same way everywhere.
"""

from __future__ import annotations

import re
import unicodedata

# Separators that genuinely delimit two active substances in an RCM.
# ``e``/``and`` are included because RCMs write "ácido X e cafeína", but see
# STOPWORDS below for the fallout that has to be filtered afterwards.
_SPLIT_PATTERN = re.compile(
    r"\s*(?:\+|/|;|,|\be\b|\band\b)\s*",
    flags=re.IGNORECASE,
)

# Fragments that are never an active substance on their own. They appear as
# split artefacts, most notably from ClinPGx entries such as
# "Vitamin K and analogues", which would otherwise yield the query "analogues".
STOPWORDS = frozenset({
    "analogues", "analogue", "analogs", "analog", "analogos", "analogo",
    "derivados", "derivado", "derivatives", "derivative",
    "outros", "outras", "other", "others",
    "associacoes", "associacao", "combinations", "combination",
    "etc", "e", "and", "ou", "or", "de", "da", "do", "e outros",
})

# Below this length a token is far too short to be safely used with the
# substring matching in ``_matches_query`` - "K" or "AC" would match almost
# anything in a reference database.
MIN_QUERY_LENGTH = 4


def normalize(text: str) -> str:
    """Lowercase, strip diacritics, collapse whitespace."""
    if not text:
        return ""

    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower().strip()
    return re.sub(r"\s+", " ", text)


def split_substances(text: str, *, keep_whole: bool = True) -> list[str]:
    """
    Split a (possibly combined) active-substance string into its components.

    Args:
        text: raw active-substance string, e.g. "paracetamol + tiocolquicosido".
        keep_whole: also return the original, unsplit string as the first
            candidate. Needed because a handful of reference entries are
            themselves combinations - ClinPGx has exactly one,
            "sulfamethoxazole / trimethoprim" (PA166279741) - and would be
            missed if only the parts were queried.

    Returns:
        De-duplicated list, original casing preserved, order stable.
    """
    if not text or not text.strip():
        return []

    text = text.strip()
    candidates: list[str] = []

    if keep_whole:
        candidates.append(text)

    candidates.extend(part.strip() for part in _SPLIT_PATTERN.split(text))

    results: list[str] = []
    seen: set[str] = set()

    for candidate in candidates:
        if not candidate:
            continue

        norm = normalize(candidate)

        if not norm or norm in seen:
            continue
        if norm in STOPWORDS:
            continue
        # The whole string is exempt from the length guard: it was supplied by
        # the caller, not produced by splitting.
        if candidate != text and len(norm) < MIN_QUERY_LENGTH:
            continue

        seen.add(norm)
        results.append(candidate)

    return results


# ---------------------------------------------------------------------------
# Curated equivalences
# ---------------------------------------------------------------------------
# Word-boundary matching is deliberately conservative, so genuine
# pharmacological relationships that are not visible in the name have to be
# declared explicitly. This table is the *only* place where one substance is
# allowed to stand in for another - never infer it from string similarity.
#
# Seeded with the single relation confirmed during validation. Everything else
# in `review_substance_equivalences.csv` was inspected and rejected: those are
# distinct drugs whose names merely overlap (hydrochlorothiazide is not
# chlorothiazide, escitalopram is not citalopram, cetazolam is not
# acetazolamide).
#
# Metabolites (norclobazam, desmethylnaproxen, O-desmethyltramadol,
# N-desmethyltamoxifen) are intentionally NOT included: whether a metabolite
# should inherit the parent drug's annotations is a pharmacological decision,
# not a string-matching one.
EQUIVALENCES: dict[str, tuple[str, ...]] = {
    # dexibuprofen is the S-(+)-enantiomer of ibuprofen; the CPIC CYP2C9 NSAID
    # guideline is written for ibuprofen.
    "dexibuprofen": ("ibuprofen",),
}


def _expand_equivalences(query_norm: str) -> list[str]:
    return [query_norm, *EQUIVALENCES.get(query_norm, ())]


def matches(value: str, query: str) -> bool:
    """
    Word-boundary-aware substring match between a reference value and a query.

    The previous implementation used a bare bidirectional substring test
    (``q in value or value in q``), which produces silent false positives on
    short substance names. The case that surfaced during validation:

        query "iron"  vs  ClinPGx chemical "spironolactone"
        -> sp[iron]olactone matched, linking an iron supplement to a
           spironolactone guideline.

    Requiring word boundaries keeps the useful cases - "simvastatin" still
    matches "simvastatin acid", "tenofovir disoproxil" still matches
    "tenofovir disoproxil fumarate" - while rejecting matches that fall in the
    middle of a word.

    Trade-off: metabolite names that glue the parent drug to a prefix
    ("desmethylnaproxen" for "naproxen") stop matching. That is deliberate -
    a metabolite is not the substance the RCM declares.
    """
    value_norm = normalize(value)
    query_norm = normalize(query)

    if not value_norm or not query_norm:
        return False

    for candidate in _expand_equivalences(query_norm):
        if value_norm == candidate:
            return True

        shorter, longer = (
            (candidate, value_norm)
            if len(candidate) <= len(value_norm)
            else (value_norm, candidate)
        )

        if re.search(rf"\b{re.escape(shorter)}\b", longer):
            return True

    return False


def matches_any(value: str, queries: list[str]) -> bool:
    """True if ``value`` matches at least one query."""
    return any(matches(value, q) for q in queries or [])


def build_queries(
    active_substance: str | None,
    aliases: list[str] | None,
    *,
    keep_whole: bool = True,
) -> list[str]:
    """
    Build the de-duplicated query list for an active substance and its aliases.

    Aliases come first: they are the English translations, and reference
    databases (ClinPGx, UMLS) are English-language.
    """
    raw: list[str] = []

    for alias in aliases or []:
        if alias and alias.strip():
            raw.extend(split_substances(alias.strip(), keep_whole=keep_whole))

    if active_substance and active_substance.strip():
        raw.extend(split_substances(active_substance.strip(), keep_whole=keep_whole))

    seen: set[str] = set()
    queries: list[str] = []

    for query in raw:
        norm = normalize(query)
        if norm and norm not in seen:
            seen.add(norm)
            queries.append(query)

    return queries
