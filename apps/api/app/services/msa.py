from dataclasses import dataclass
from collections.abc import Iterable


@dataclass(frozen=True)
class MsaInputSequence:
    identifier: str
    sequence: str


@dataclass(frozen=True)
class MsaAlignedRecord:
    identifier: str
    aligned_sequence: str


@dataclass(frozen=True)
class MsaAlignment:
    records: list[MsaAlignedRecord]

    @property
    def sequence_count(self) -> int:
        return len(self.records)

    @property
    def alignment_length(self) -> int:
        if not self.records:
            return 0
        return len(self.records[0].aligned_sequence)

    def to_fasta(self) -> str:
        return "".join(
            f">{record.identifier}\n{record.aligned_sequence}\n" for record in self.records
        )


def run_mock_mafft(sequences: Iterable[MsaInputSequence]) -> MsaAlignment:
    normalized = [
        MsaInputSequence(
            identifier=sequence.identifier,
            sequence=_normalize_sequence(sequence.sequence),
        )
        for sequence in sequences
    ]
    alignment_length = max((len(sequence.sequence) for sequence in normalized), default=0)
    return MsaAlignment(
        records=[
            MsaAlignedRecord(
                identifier=sequence.identifier,
                aligned_sequence=sequence.sequence.ljust(alignment_length, "-"),
            )
            for sequence in normalized
        ]
    )


def _normalize_sequence(sequence: str) -> str:
    return sequence.upper().replace(" ", "").replace("\n", "")
