import enum
import re
from dataclasses import dataclass

from app.db.models import EnzymeModule


class QueryKind(str, enum.Enum):
    UNIPROT = "uniprot"
    PDB = "pdb"
    EC = "ec"
    SEQUENCE = "sequence"
    KEYWORD = "keyword"


@dataclass(frozen=True)
class ResolvedQuery:
    raw_query: str
    normalized_query: str
    kind: QueryKind
    module_hint: EnzymeModule | None


UNIPROT_RE = re.compile(
    r"^(?:[OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9](?:[A-Z][A-Z0-9]{2}[0-9]){1,2})$"
)
PDB_RE = re.compile(r"^[0-9][A-Za-z0-9]{3}$")
EC_RE = re.compile(r"^\d+\.\d+\.\d+\.\d+$")
AA_SEQUENCE_RE = re.compile(r"^[ACDEFGHIKLMNPQRSTVWYBXZJUO]+$", re.IGNORECASE)


def detect_module(query: str) -> EnzymeModule | None:
    lowered = query.lower()
    if "transglutaminase" in lowered or "mtgase" in lowered:
        return EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE
    if "anthraquinone" in lowered or "glycosyltransferase" in lowered:
        return EnzymeModule.ANTHRAQUINONE_GLYCOSYLTRANSFERASE
    return None


def detect_amino_acid_sequence(query: str) -> bool:
    compact = re.sub(r"\s+", "", query)
    return len(compact) >= 30 and AA_SEQUENCE_RE.match(compact) is not None


def resolve_query(query: str) -> ResolvedQuery:
    normalized = query.strip()
    upper = normalized.upper()
    if EC_RE.match(normalized):
        kind = QueryKind.EC
    elif PDB_RE.match(upper):
        kind = QueryKind.PDB
        normalized = upper
    elif UNIPROT_RE.match(upper):
        kind = QueryKind.UNIPROT
        normalized = upper
    elif detect_amino_acid_sequence(normalized):
        kind = QueryKind.SEQUENCE
        normalized = re.sub(r"\s+", "", upper)
    else:
        kind = QueryKind.KEYWORD
    return ResolvedQuery(
        raw_query=query,
        normalized_query=normalized,
        kind=kind,
        module_hint=detect_module(query),
    )
