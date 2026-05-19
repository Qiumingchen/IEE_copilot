from app.services.msa import MsaInputSequence, run_mock_mafft


def test_run_mock_mafft_aligns_sequences_to_same_length():
    alignment = run_mock_mafft(
        [
            MsaInputSequence(identifier="query", sequence="ACDEFG"),
            MsaInputSequence(identifier="homolog_short", sequence="ACDF"),
            MsaInputSequence(identifier="homolog_long", sequence="ACDEFGH"),
        ]
    )

    assert alignment.sequence_count == 3
    assert alignment.alignment_length == 7
    assert {len(record.aligned_sequence) for record in alignment.records} == {7}
    assert alignment.records[0].aligned_sequence == "ACDEFG-"
    assert alignment.records[1].aligned_sequence == "ACDF---"
    assert alignment.to_fasta() == (
        ">query\nACDEFG-\n"
        ">homolog_short\nACDF---\n"
        ">homolog_long\nACDEFGH\n"
    )
