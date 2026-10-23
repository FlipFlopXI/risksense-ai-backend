"""Exact boundary-aware catalogue matching; no fuzzy clinical identification."""
from dataclasses import dataclass
import re
from app.ml.drug_assistant.runtime import DrugRuntime, normalize


@dataclass(frozen=True)
class Resolution:
    drug_ids: tuple[str, ...] = ()
    status: str = "UNSUPPORTED_DRUG"


def resolve(message: str, runtime: DrugRuntime, previous: tuple[str, ...] = ()) -> Resolution:
    normalized = normalize(message)
    matches = []
    for alias, ids in runtime.aliases.items():
        for found in re.finditer(r"(?<!\w)" + re.escape(alias) + r"(?!\w)", normalized):
            matches.append((found.start(), found.end(), ids))
    # A component name inside a supported combination is not a second drug.
    matches = [m for m in matches if not any(other[0] <= m[0] and other[1] >= m[1] and (other[0], other[1]) != (m[0], m[1]) for other in matches)]
    if matches:
        if any(len(m[2]) != 1 for m in matches):
            return Resolution(status="AMBIGUOUS_DRUG")
        return Resolution(tuple(dict.fromkeys(m[2][0] for m in sorted(matches))), "RESOLVED")
    if re.search(r"\b(pill|tablet|capsule)\b.*\b(red|blue|white|round|oval|small)\b|\b(red|blue|white|round|oval|small)\b.*\b(pill|tablet|capsule)\b", normalized):
        return Resolution(status="AMBIGUOUS_DRUG")
    if re.search(r"\b(this|that|it|these|those)\b", normalized):
        # Carry only explicit pronouns, not a previously mentioned drug for an unknown name.
        if len(previous) == 1 and not re.search(r"\b(?:called|named)\b", normalized):
            return Resolution(previous, "RESOLVED")
        return Resolution(status="AMBIGUOUS_DRUG")
    # Narrow ellipsis used by ordinary follow-up questions. Multiple prior drugs
    # remain ambiguous and unknown named medicines never inherit session state.
    if previous and "instead" not in normalized and re.search(
            r"\b(?:pregnan\w*|breastfeed\w*|breast milk|lactation|side effects?|adverse effects?|"
            r"warnings?|contraindications?|interactions?|monitoring|fertility|administered)\b", normalized):
        return Resolution(previous, "RESOLVED") if len(previous) == 1 else Resolution(status="AMBIGUOUS_DRUG")
    return Resolution()
