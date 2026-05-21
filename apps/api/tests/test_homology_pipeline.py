import threading
import time
from pathlib import Path

from app.services.homology import (
    HomologSearchParameters,
    HomologSequence,
    collect_homologs,
    collect_homologs_with_diagnostics,
    deduplicate_sequences,
    fetch_local_fasta_similarity_candidates,
    fetch_uniprot_homolog_candidates,
    filter_by_coverage,
    filter_by_identity,
    limit_max_sequences,
    run_configured_sequence_similarity_search,
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


def test_collect_homologs_with_diagnostics_counts_filter_stages():
    candidates = [
        HomologSequence("TOO_CLOSE", "Too close", None, "ACDEFGHIKL", "test"),
        HomologSequence("KEEP", "Keep", None, "ACDEFGHIVL", "test"),
        HomologSequence("LOW_ID", "Low identity", None, "VVVVVVVVVV", "test"),
        HomologSequence("LOW_COV", "Low coverage", None, "ACDEV", "test"),
        HomologSequence("KEEP_DUP", "Duplicate keep", None, "ACDEFGHIVL", "test"),
    ]

    homologs, diagnostics = collect_homologs_with_diagnostics(QUERY_SEQUENCE, candidates)

    assert [homolog.accession for homolog in homologs] == ["KEEP_DUP"]
    assert diagnostics == {
        "candidate_count": 5,
        "scored_count": 5,
        "passed_identity_count": 3,
        "filtered_identity_count": 2,
        "passed_coverage_count": 2,
        "filtered_coverage_count": 1,
        "deduplicated_count": 1,
        "duplicate_count": 1,
        "returned_count": 1,
        "max_sequences": 25,
    }


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

        def __init__(self):
            self.searches = []

        def search_by_ec(self, ec_number, size=5):
            assert ec_number == "2.3.2.13"
            self.searches.append(("ec", ec_number, size))
            return [
                UniProtSearchHit(
                    accession="P22222",
                    protein_name="Broad EC candidate",
                    organism="Homo sapiens",
                    ec_number=ec_number,
                )
            ]

        def search_by_keyword(self, keyword, size=5):
            assert keyword == "Microbial transglutaminase"
            self.searches.append(("keyword", keyword, size))
            return [
                UniProtSearchHit(
                    accession="P11111",
                    protein_name="Candidate transglutaminase",
                    organism="Streptomyces testensis",
                    ec_number="2.3.2.13",
                )
            ]

        def fetch_entry(self, accession):
            sequences = {
                "P11111": "ACDEFGHIVL",
                "P22222": "VVVVVVVVVV",
            }
            return UniProtEntry(
                accession=accession,
                protein_name=f"Candidate {accession}",
                organism="Streptomyces testensis" if accession == "P11111" else "Homo sapiens",
                ec_number="2.3.2.13",
                sequence=sequences[accession],
            )

    fake_client = FakeUniProtClient()
    candidates = fetch_uniprot_homolog_candidates(
        enzyme_name="Microbial transglutaminase",
        ec_number="2.3.2.13",
        uniprot_client=fake_client,
        size=5,
    )

    assert fake_client.searches == [
        ("keyword", "Microbial transglutaminase", 5),
        ("ec", "2.3.2.13", 4),
    ]
    assert candidates == [
        HomologSequence(
            accession="P11111",
            name="Candidate P11111",
            organism="Streptomyces testensis",
            sequence="ACDEFGHIVL",
            source="uniprot",
        ),
        HomologSequence(
            accession="P22222",
            name="Candidate P22222",
            organism="Homo sapiens",
            sequence="VVVVVVVVVV",
            source="uniprot",
        ),
    ]


def test_fetch_uniprot_homolog_candidates_uses_canonical_query_for_mock_mtgase():
    class FakeUniProtClient:
        source = "uniprot"

        def __init__(self):
            self.searches = []

        def search_by_keyword(self, keyword, size=5):
            self.searches.append(("keyword", keyword, size))
            if keyword == "Microbial transglutaminase":
                return [
                    UniProtSearchHit(
                        accession="P11111",
                        protein_name="Canonical mTGase candidate",
                        organism="Streptomyces testensis",
                        ec_number="2.3.2.13",
                    )
                ]
            return []

        def search_by_ec(self, ec_number, size=5):
            self.searches.append(("ec", ec_number, size))
            return []

        def fetch_entry(self, accession):
            return UniProtEntry(
                accession=accession,
                protein_name="Canonical mTGase candidate",
                organism="Streptomyces testensis",
                ec_number="2.3.2.13",
                sequence="ACDEFGHIVL",
            )

    fake_client = FakeUniProtClient()

    candidates = fetch_uniprot_homolog_candidates(
        enzyme_name="Mock microbial transglutaminase",
        ec_number="2.3.2.13",
        uniprot_client=fake_client,
        size=5,
    )

    assert fake_client.searches[0] == ("keyword", "Microbial transglutaminase", 5)
    assert [candidate.accession for candidate in candidates] == ["P11111"]


def test_fetch_uniprot_homolog_candidates_fetches_entries_concurrently_in_hit_order():
    class SlowUniProtClient:
        source = "uniprot"

        def __init__(self):
            self.active_fetches = 0
            self.max_active_fetches = 0
            self.lock = threading.Lock()

        def search_by_keyword(self, keyword, size=5):
            return [
                UniProtSearchHit(
                    accession=f"P{i}",
                    protein_name=f"Candidate {i}",
                    organism="Streptomyces testensis",
                    ec_number="2.3.2.13",
                )
                for i in range(4)
            ]

        def search_by_ec(self, ec_number, size=5):
            return []

        def fetch_entry(self, accession):
            with self.lock:
                self.active_fetches += 1
                self.max_active_fetches = max(self.max_active_fetches, self.active_fetches)
            time.sleep(0.03)
            with self.lock:
                self.active_fetches -= 1
            return UniProtEntry(
                accession=accession,
                protein_name=f"Candidate {accession}",
                organism="Streptomyces testensis",
                ec_number="2.3.2.13",
                sequence="ACDEFGHIVL",
            )

    fake_client = SlowUniProtClient()

    candidates = fetch_uniprot_homolog_candidates(
        enzyme_name="Microbial transglutaminase",
        ec_number="2.3.2.13",
        uniprot_client=fake_client,
        size=4,
    )

    assert fake_client.max_active_fetches > 1
    assert [candidate.accession for candidate in candidates] == ["P0", "P1", "P2", "P3"]


def test_run_configured_sequence_similarity_search_maps_command_hits_to_fasta_records(tmp_path: Path):
    fasta_path = tmp_path / "homologs.fasta"
    fasta_path.write_text(
        "\n".join(
            [
                ">EXACT exact match [Synthetic construct]",
                "ACDEFGHIKL",
                ">NEAR near homolog OS=Streptomyces testensis",
                "ACDEFGHIVL",
                ">DISTANT distant protein",
                "VVVVVVVVVV",
            ]
        ),
        encoding="utf-8",
    )
    script = tmp_path / "fake_similarity.py"
    script.write_text(
        "import sys\n"
        "sys.stdin.read()\n"
        "print('NEAR\\t90\\t100')\n"
        "print('DISTANT\\t10\\t100')\n",
        encoding="utf-8",
    )

    candidates = run_configured_sequence_similarity_search(
        query_sequence=QUERY_SEQUENCE,
        fasta_path=str(fasta_path),
        command=f"python {script}",
        size=5,
    )

    assert [candidate.accession for candidate in candidates] == ["NEAR", "DISTANT"]
    assert candidates[0].sequence == "ACDEFGHIVL"
    assert candidates[0].organism == "Streptomyces testensis"
    assert candidates[0].identity == 0.9
    assert candidates[0].coverage == 1.0
    assert candidates[0].source == "sequence_similarity_command"


def test_fetch_local_fasta_similarity_candidates_prefers_full_coverage_hits(tmp_path: Path):
    fasta_path = tmp_path / "homologs.fasta"
    fasta_path.write_text(
        "\n".join(
            [
                ">SHORT exact short fragment",
                "ACDEF",
                ">FULL full length homolog",
                "ACDEFGHIVL",
            ]
        ),
        encoding="utf-8",
    )

    candidates = fetch_local_fasta_similarity_candidates(
        query_sequence=QUERY_SEQUENCE,
        fasta_path=str(fasta_path),
        size=2,
    )

    assert [candidate.accession for candidate in candidates] == ["FULL", "SHORT"]
