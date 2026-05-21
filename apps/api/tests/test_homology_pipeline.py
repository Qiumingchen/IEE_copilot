from app.services.homology import (
    HomologSearchParameters,
    HomologSequence,
    collect_homologs,
    deduplicate_sequences,
    fetch_uniprot_homolog_candidates,
    filter_by_coverage,
    filter_by_identity,
    limit_max_sequences,
)
from app.external.uniprot import UniProtEntry, UniProtSearchHit


QUERY_SEQUENCE = "ACDEFGHIKL"


def test_collect_homologs_filters_candidates_with_default_thresholds():
    candidates = [
        HomologSequence(
            accession="HIT_HIGH",
            name="Too close homolog",
            organism="Test organism",
            sequence="ACDEFGHIKL",
            source="test",
        ),
        HomologSequence(
            accession="HIT_KEEP",
            name="Accepted homolog",
            organism="Test organism",
            sequence="ACDEFGHIVL",
            source="test",
        ),
        HomologSequence(
            accession="HIT_LOW_ID",
            name="Low identity homolog",
            organism="Test organism",
            sequence="VVVVVVVVVV",
            source="test",
        ),
        HomologSequence(
            accession="HIT_LOW_COV",
            name="Low coverage homolog",
            organism="Test organism",
            sequence="ACDEF",
            source="test",
        ),
    ]

    homologs = collect_homologs(QUERY_SEQUENCE, candidates)

    assert [homolog.accession for homolog in homologs] == ["HIT_KEEP"]
    assert homologs[0].identity == 0.9
    assert homologs[0].coverage == 1.0


def test_filter_by_identity_uses_inclusive_min_and_max_percentages():
    candidates = [
        HomologSequence("MIN", "Min", None, "ACDEVVVVVV", "test", identity=0.4, coverage=1.0),
        HomologSequence("MAX", "Max", None, "ACDEFGHIVL", "test", identity=0.95, coverage=1.0),
        HomologSequence("TOO_HIGH", "Too high", None, "ACDEFGHIKL", "test", identity=1.0, coverage=1.0),
        HomologSequence("TOO_LOW", "Too low", None, "VVVVVVVVVV", "test", identity=0.3, coverage=1.0),
    ]

    filtered = filter_by_identity(candidates, identity_min=40, identity_max=95)

    assert [homolog.accession for homolog in filtered] == ["MIN", "MAX"]


def test_filter_by_coverage_uses_inclusive_min_percentage():
    candidates = [
        HomologSequence("KEEP", "Keep", None, "ACDEFGH", "test", identity=0.8, coverage=0.7),
        HomologSequence("DROP", "Drop", None, "ACDEF", "test", identity=0.8, coverage=0.5),
    ]

    filtered = filter_by_coverage(candidates, coverage_min=70)

    assert [homolog.accession for homolog in filtered] == ["KEEP"]


def test_deduplicate_sequences_keeps_best_scoring_duplicate():
    candidates = [
        HomologSequence("LOW", "Duplicate low", None, "ACDEFGHIVL", "test", identity=0.8, coverage=1.0),
        HomologSequence("HIGH", "Duplicate high", None, "ACDEFGHIVL", "test", identity=0.9, coverage=1.0),
        HomologSequence("OTHER", "Other", None, "ACDEYGHIVL", "test", identity=0.8, coverage=1.0),
    ]

    deduplicated = deduplicate_sequences(candidates)

    assert [homolog.accession for homolog in deduplicated] == ["HIGH", "OTHER"]


def test_limit_max_sequences_orders_by_identity_then_coverage():
    candidates = [
        HomologSequence("SECOND", "Second", None, "ACDEFGHIVL", "test", identity=0.8, coverage=1.0),
        HomologSequence("THIRD", "Third", None, "ACDEYGHIVL", "test", identity=0.7, coverage=1.0),
        HomologSequence("FIRST", "First", None, "ACDEFGHILL", "test", identity=0.8, coverage=0.9),
    ]

    limited = limit_max_sequences(candidates, max_sequences=2)

    assert [homolog.accession for homolog in limited] == ["SECOND", "FIRST"]


def test_collect_homologs_accepts_custom_parameters():
    candidates = [
        HomologSequence(
            accession="CLOSE",
            name="Close homolog",
            organism=None,
            sequence="ACDEFGHIKL",
            source="test",
        )
    ]

    homologs = collect_homologs(
        QUERY_SEQUENCE,
        candidates,
        parameters=HomologSearchParameters(identity_max=100, max_sequences=1),
    )

    assert [homolog.accession for homolog in homologs] == ["CLOSE"]


def test_fetch_uniprot_homolog_candidates_converts_search_hits_to_sequences():
    class FakeUniProtClient:
        source = "uniprot"

        def search_by_ec(self, ec_number, size=5):
            assert ec_number == "2.3.2.13"
            return [
                UniProtSearchHit(
                    accession="P11111",
                    protein_name="Candidate transglutaminase",
                    organism="Streptomyces testensis",
                    ec_number=ec_number,
                )
            ]

        def search_by_keyword(self, keyword, size=5):
            raise AssertionError("EC search should be preferred when EC number is available")

        def fetch_entry(self, accession):
            assert accession == "P11111"
            return UniProtEntry(
                accession=accession,
                protein_name="Candidate transglutaminase",
                organism="Streptomyces testensis",
                ec_number="2.3.2.13",
                sequence="ACDEFGHIVL",
            )

    candidates = fetch_uniprot_homolog_candidates(
        enzyme_name="Microbial transglutaminase",
        ec_number="2.3.2.13",
        uniprot_client=FakeUniProtClient(),
        size=5,
    )

    assert candidates == [
        HomologSequence(
            accession="P11111",
            name="Candidate transglutaminase",
            organism="Streptomyces testensis",
            sequence="ACDEFGHIVL",
            source="uniprot",
        )
    ]
