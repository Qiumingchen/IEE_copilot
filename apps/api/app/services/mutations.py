import re

from pydantic import BaseModel


_MUTATION_TOKEN_RE = re.compile(r"^([A-Z])([1-9][0-9]*)([A-Z])$")
_CANONICAL_AMINO_ACIDS = set("ACDEFGHIKLMNPQRSTVWY")


class MutationParseError(ValueError):
    pass


class ParsedMutation(BaseModel):
    wildtype: str
    position: int
    mutant: str


def parse_mutation_string(mutation_string: str) -> list[ParsedMutation]:
    normalized = mutation_string.strip().upper()
    if not normalized:
        raise MutationParseError("mutation_string is required")

    tokens = re.split(r"[/\-]", normalized)
    mutations: list[ParsedMutation] = []
    seen_positions: set[int] = set()
    for token in tokens:
        if not token:
            raise MutationParseError("Invalid mutation token: empty token")
        match = _MUTATION_TOKEN_RE.match(token)
        if match is None:
            raise MutationParseError(f"Invalid mutation token: {token}")

        wildtype, position_text, mutant = match.groups()
        if wildtype not in _CANONICAL_AMINO_ACIDS or mutant not in _CANONICAL_AMINO_ACIDS:
            raise MutationParseError(f"Invalid amino acid code in mutation token: {token}")
        if wildtype == mutant:
            raise MutationParseError(f"Mutation token does not change residue: {token}")

        position = int(position_text)
        if position in seen_positions:
            raise MutationParseError(f"Duplicate mutation position: {position}")
        seen_positions.add(position)
        mutations.append(ParsedMutation(wildtype=wildtype, position=position, mutant=mutant))

    return mutations


def normalize_mutation_string(mutations: list[ParsedMutation]) -> str:
    return "/".join(
        f"{mutation.wildtype}{mutation.position}{mutation.mutant}" for mutation in mutations
    )


def validate_mutations_against_sequence(
    mutations: list[ParsedMutation],
    sequence: str,
) -> None:
    normalized_sequence = sequence.strip().upper()
    for mutation in mutations:
        if mutation.position > len(normalized_sequence):
            raise MutationParseError(
                f"mutation position {mutation.position} exceeds sequence length {len(normalized_sequence)}"
            )
        observed = normalized_sequence[mutation.position - 1]
        if observed != mutation.wildtype:
            raise MutationParseError(
                f"expected {mutation.wildtype} at position {mutation.position} but found {observed}"
            )


def generate_rosetta_mutation_file(mutations: list[ParsedMutation]) -> str:
    return "\n".join(
        f"{mutation.wildtype} {mutation.position} {mutation.mutant}" for mutation in mutations
    )
