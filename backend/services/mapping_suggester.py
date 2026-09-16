"""Suggests source->target column mappings. Suggestions are never
auto-applied — the API only returns them; the user must confirm."""
from __future__ import annotations

import difflib
import re


_STOPWORDS = {"the", "of", "a", "an"}

# Known synonym clusters seen in typical customer-master migrations.
_SYNONYMS = [
    {"custid", "customerid", "customerno", "custno", "id", "customer_id"},
    {"firstname", "fname", "first_name", "givenname"},
    {"lastname", "lname", "last_name", "surname", "familyname"},
    {"dob", "dateofbirth", "birthdate", "birth_date", "date_of_birth"},
    {"mobile", "mobileno", "phone", "phonenumber", "cell", "cellphone", "contactno"},
    {"email", "emailaddress", "email_id", "mailid"},
    {"address", "addr", "address1", "addressline1"},
]


def _normalize(name: str) -> str:
    n = re.sub(r"[^a-z0-9]", "", name.lower())
    return n


def _synonym_key(norm_name: str) -> str | None:
    for cluster in _SYNONYMS:
        if norm_name in cluster:
            return "|".join(sorted(cluster))
    return None


def suggest_mappings(source_columns: list[str], target_columns: list[str]) -> list[dict]:
    """Returns a list of {source_column, target_column, confidence, reason}
    sorted by confidence desc. Each target column is suggested at most once,
    each source column is suggested at most once (greedy best-match)."""
    suggestions = []
    norm_targets = {t: _normalize(t) for t in target_columns}
    syn_targets = {t: _synonym_key(norm_targets[t]) for t in target_columns}

    used_targets = set()

    for s in source_columns:
        norm_s = _normalize(s)
        syn_s = _synonym_key(norm_s)

        best_target = None
        best_score = 0.0
        best_reason = ""

        for t in target_columns:
            if t in used_targets:
                continue
            norm_t = norm_targets[t]

            if norm_s == norm_t:
                score, reason = 0.99, "exact column name match"
            elif syn_s and syn_s == syn_targets[t]:
                score, reason = 0.92, "recognised naming synonym"
            elif norm_s in norm_t or norm_t in norm_s:
                score, reason = 0.75, "one name contains the other"
            else:
                ratio = difflib.SequenceMatcher(None, norm_s, norm_t).ratio()
                score, reason = ratio * 0.7, "fuzzy name similarity"

            if score > best_score:
                best_score = score
                best_target = t
                best_reason = reason

        if best_target and best_score >= 0.55:
            suggestions.append(
                {
                    "source_column": s,
                    "target_column": best_target,
                    "confidence": round(best_score, 2),
                    "reason": best_reason,
                }
            )
            used_targets.add(best_target)

    suggestions.sort(key=lambda x: -x["confidence"])
    return suggestions
