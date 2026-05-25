from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.external.uniprot import UniProtEntry, UniProtSearchHit
from app.db.base import Base
from app.db.models import (
    AnalysisArtifact,
    AnalysisJob,
    EnzymeEntry,
    EnzymeFamily,
    EnzymeModule,
    JobStatus,
    KineticRecord,
    MutationRecord,
    ProteinSequence,
    PropertyRecord,
    StructureEntry,
)
from worker.jobs import (
    _homolog_candidates_for_job,
    finish_conservation_profile_job,
    finish_homology_collection_job,
    finish_library_design_job,
    finish_mutation_recommendation_job,
    finish_msa_job,
    finish_placeholder_job,
    finish_real_data_refresh_job,
    finish_rosetta_ddg_job,
    mark_job_failed,
)


class _FakeUniProtClient:
    def __init__(self):
        self.searches = []

    def search_by_keyword(self, _keyword: str, size: int = 25):
        self.searches.append(("keyword", size))
        return [
            UniProtSearchHit(
                accession="REAL_HOMOLOG_1",
                protein_name="Real homolog 1",
                organism="Test organism",
                ec_number="2.3.2.13",
                score=1.0,
            )
        ]

    def search_by_ec(self, _ec_number: str, *, size: int = 25):
        self.searches.append(("ec", size))
        return [
            UniProtSearchHit(
                accession="REAL_HOMOLOG_1",
                protein_name="Real homolog 1",
                organism="Test organism",
                ec_number="2.3.2.13",
                score=1.0,
            )
        ]

    def fetch_entry(self, _accession: str):
        return UniProtEntry(
            accession="REAL_HOMOLOG_1",
            protein_name="Real homolog 1",
            organism="Test organism",
            ec_number="2.3.2.13",
            sequence="ACDEFGHIVL",
            cross_references={},
        )


def test_finish_placeholder_job_builds_real_local_family_profile_summary():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with SessionLocal() as db:
        family = EnzymeFamily(
            module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
            name="Mature microbial transglutaminases",
        )
        db.add(family)
        db.flush()
        enzyme = EnzymeEntry(
            family_id=family.id,
            name="Worker profile enzyme",
            organism="Bacillus subtilis",
            uniprot_id="P00691",
            source="uniprot",
        )
        db.add(enzyme)
        db.flush()
        db.add_all(
            [
                ProteinSequence(
                    enzyme_entry_id=enzyme.id,
                    sequence="ACDEFGHIKL",
                    mature_sequence=None,
                    source="uniprot",
                    checksum="worker-profile-sequence",
                ),
                PropertyRecord(
                    enzyme_entry_id=enzyme.id,
                    property_type="optimal_temperature",
                    value_original="72",
                    unit_original="degC",
                    method="europepmc",
                    evidence_text="real literature evidence",
                ),
                KineticRecord(
                    enzyme_entry_id=enzyme.id,
                    substrate="starch",
                    km="1.8",
                    kcat="42",
                    method="europepmc",
                    evidence_text="real kinetic literature evidence",
                ),
                MutationRecord(
                    enzyme_entry_id=enzyme.id,
                    mutation_string="A123V",
                    effect_summary="thermostability improved",
                    assay_condition_summary={"source": "europepmc"},
                ),
                StructureEntry(
                    enzyme_entry_id=enzyme.id,
                    structure_type="alphafold_model",
                    complex_state="apo",
                    source="alphafold",
                ),
            ]
        )
        job = AnalysisJob(
            enzyme_entry_id=enzyme.id,
            job_type="family_profile_summary",
            status=JobStatus.QUEUED,
        )
        db.add(job)
        db.commit()
        db.refresh(job)

        finish_placeholder_job(db, job.id, bucket="iee-artifacts")

        db.refresh(job)
        artifact = db.scalar(select(AnalysisArtifact).where(AnalysisArtifact.job_id == job.id))

    assert job.status == JobStatus.FINISHED
    assert job.result_summary_json["message"] == "family profile summary completed"
    assert job.result_summary_json["artifact_type"] == "family_profile_summary"
    assert job.result_summary_json["enzyme"]["name"] == "Worker profile enzyme"
    assert job.result_summary_json["counts"] == {
        "protein_sequences": 1,
        "properties": 1,
        "kinetics": 1,
        "mutations": 1,
        "structures": 1,
    }
    assert job.result_summary_json["sources"] == ["alphafold", "europepmc", "uniprot"]
    assert artifact is not None
    assert artifact.artifact_type == "family_profile_summary"
    assert artifact.size_bytes > 0


def test_finish_real_data_refresh_job_updates_status_and_summary(monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def fake_save_literature(_db, _enzyme, *, require_real):
        assert require_real is True
        return 1, ["crossref"], []

    def fake_save_external_data(_db, _enzyme, *, require_real):
        assert require_real is True
        return {"properties": 2, "kinetics": 0, "mutations": 0}, ["europepmc", "europepmc"], [
            "one source was temporarily unavailable"
        ]

    def fake_save_alphafold(_db, _enzyme, *, require_real):
        assert require_real is True
        return 0, [], []

    monkeypatch.setattr("app.api.routes.enzymes._save_literature_for_enzyme", fake_save_literature)
    monkeypatch.setattr("app.api.routes.enzymes._save_external_enzyme_data", fake_save_external_data)
    monkeypatch.setattr("app.api.routes.enzymes._save_alphafold_structure_for_enzyme", fake_save_alphafold)

    with SessionLocal() as db:
        family = EnzymeFamily(
            module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
            name="Mature microbial transglutaminases",
        )
        db.add(family)
        db.flush()
        enzyme = EnzymeEntry(
            family_id=family.id,
            name="Worker real data enzyme",
            organism="Streptomyces mobaraensis",
            uniprot_id="P81453",
            source="uniprot",
        )
        db.add(enzyme)
        db.flush()
        job = AnalysisJob(
            enzyme_entry_id=enzyme.id,
            job_type="real_data_refresh",
            status=JobStatus.QUEUED,
            parameters_json={"scope": "enzyme"},
        )
        db.add(job)
        db.commit()
        db.refresh(job)

        finish_real_data_refresh_job(db, job.id)

        db.refresh(job)

    assert job.status == JobStatus.FINISHED
    assert job.result_summary_json == {
        "message": "real data refresh completed",
        "scope": "enzyme",
        "created": {"references": 1, "properties": 2, "kinetics": 0, "mutations": 0, "structures": 0},
        "sources": ["crossref", "europepmc"],
        "warnings": ["one source was temporarily unavailable"],
        "progress": {
            "checked_sources": 3,
            "found_records": 3,
            "not_found_sources": 1,
            "processed_enzymes": 1,
            "total_enzymes": 1,
            "stage": "completed",
        },
    }


def test_finish_real_data_refresh_job_stops_after_cancel_request(monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    calls = []

    def fake_save_literature(db, _enzyme, *, require_real):
        assert require_real is True
        calls.append("literature")
        job = db.scalar(select(AnalysisJob).where(AnalysisJob.job_type == "real_data_refresh"))
        job.status = JobStatus.CANCELLED
        db.commit()
        return 1, ["crossref"], []

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("cancelled real data refresh should not continue to next source")

    monkeypatch.setattr("app.api.routes.enzymes._save_literature_for_enzyme", fake_save_literature)
    monkeypatch.setattr("app.api.routes.enzymes._save_external_enzyme_data", fail_if_called)

    with SessionLocal() as db:
        family = EnzymeFamily(
            module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
            name="Mature microbial transglutaminases",
        )
        db.add(family)
        db.flush()
        enzyme = EnzymeEntry(
            family_id=family.id,
            name="Cancellable real data enzyme",
            organism="Streptomyces mobaraensis",
            uniprot_id="P81453",
            source="uniprot",
        )
        db.add(enzyme)
        db.flush()
        job = AnalysisJob(
            enzyme_entry_id=enzyme.id,
            job_type="real_data_refresh",
            status=JobStatus.QUEUED,
            parameters_json={"scope": "enzyme"},
        )
        db.add(job)
        db.commit()
        db.refresh(job)

        finish_real_data_refresh_job(db, job.id)

        db.refresh(job)

    assert calls == ["literature"]
    assert job.status == JobStatus.CANCELLED
    assert job.result_summary_json["message"] == "real data refresh cancelled"
    assert job.result_summary_json["created"]["references"] == 1
    assert job.result_summary_json["progress"]["checked_sources"] == 1
    assert job.result_summary_json["progress"]["found_records"] == 1


def test_finish_homology_collection_job_creates_homolog_sequence_artifact(monkeypatch):
    class RealButFallbackSettings:
        use_real_science_providers = False
        allow_science_fallbacks = True
        homolog_provider_fetch_size = 25
        sequence_similarity_fasta_path = None
        sequence_similarity_command = None
        mafft_bin = "mafft --auto -"

    monkeypatch.setattr("worker.jobs.get_settings", lambda: RealButFallbackSettings(), raising=False)

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with SessionLocal() as db:
        family = EnzymeFamily(
            module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
            name="Mature microbial transglutaminases",
        )
        db.add(family)
        db.flush()
        enzyme = EnzymeEntry(
            family_id=family.id,
            name="Worker test mTGase",
            source="test",
        )
        db.add(enzyme)
        db.flush()
        enzyme_id = enzyme.id
        db.add(
            ProteinSequence(
                enzyme_entry_id=enzyme_id,
                sequence="ACDEFGHIKL",
                mature_sequence="ACDEFGHIKL",
                source="test",
                checksum="worker-test-sequence",
            )
        )
        job = AnalysisJob(
            enzyme_entry_id=enzyme_id,
            job_type="homolog_collection",
            status=JobStatus.QUEUED,
            parameters_json={"identity_min": 40, "identity_max": 95, "coverage_min": 70},
        )
        db.add(job)
        db.commit()
        db.refresh(job)

        finish_homology_collection_job(db, job.id, bucket="iee-artifacts")

        db.refresh(job)
        artifact = db.scalar(
            select(AnalysisArtifact).where(
                AnalysisArtifact.job_id == job.id,
                AnalysisArtifact.artifact_type == "homolog_sequences",
            )
        )

    assert job.status == JobStatus.FINISHED
    assert job.result_summary_json["message"] == "homolog collection completed"
    assert job.result_summary_json["homolog_count"] == 2
    assert job.result_summary_json["artifact_type"] == "homolog_sequences"
    assert job.result_summary_json["diagnostics"] == {
        "candidate_count": 5,
        "scored_count": 5,
        "passed_identity_count": 2,
        "filtered_identity_count": 3,
        "passed_coverage_count": 2,
        "filtered_coverage_count": 0,
        "deduplicated_count": 2,
        "duplicate_count": 0,
        "returned_count": 2,
        "max_sequences": 25,
    }
    assert job.result_summary_json["runner"]["provider"] == "uniprot"
    assert job.result_summary_json["runner"]["mode"] == "fallback"
    assert [homolog["accession"] for homolog in job.result_summary_json["homologs"]] == [
        "MOCK_HOMOLOG_90",
        "MOCK_HOMOLOG_80",
    ]
    assert artifact is not None
    assert artifact.enzyme_entry_id == enzyme_id
    assert artifact.bucket == "iee-artifacts"
    assert artifact.object_key == f"analysis-jobs/{job.id}/homolog-sequences.json"
    assert artifact.content_type == "application/json"
    assert artifact.size_bytes > 0
    assert artifact.checksum is not None


def test_finish_homology_collection_job_backfills_missing_sequence_from_uniprot(monkeypatch):
    class RealButFallbackSettings:
        use_real_science_providers = True
        allow_science_fallbacks = True
        homolog_provider_fetch_size = 25
        sequence_similarity_fasta_path = None
        sequence_similarity_command = None
        mafft_bin = "mafft --auto -"

    class FakeUniProtClient:
        source = "uniprot"

        def fetch_entry(self, accession: str):
            assert accession == "P81453"
            return UniProtEntry(
                accession=accession,
                protein_name="Protein-glutamine gamma-glutamyltransferase",
                organism="Streptomyces mobaraensis",
                ec_number="2.3.2.13",
                sequence="ACDEFGHIKL",
                mature_sequence="CDEFGHIKL",
                reviewed=True,
                cross_references={"AlphaFoldDB": "AF-P81453-F1"},
            )

        def fetch_fasta(self, accession: str):
            return ">sp|P81453|TGASE\nACDEFGHIKL\n"

    monkeypatch.setattr("worker.jobs.get_settings", lambda: RealButFallbackSettings(), raising=False)
    monkeypatch.setattr("worker.jobs.get_uniprot_client", lambda: FakeUniProtClient(), raising=False)

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with SessionLocal() as db:
        family = EnzymeFamily(
            module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
            name="Mature microbial transglutaminases",
        )
        db.add(family)
        db.flush()
        enzyme = EnzymeEntry(
            family_id=family.id,
            name="Protein-glutamine gamma-glutamyltransferase",
            organism="Streptomyces mobaraensis",
            ec_number="2.3.2.13",
            uniprot_id="P81453",
            source="uniprot",
        )
        db.add(enzyme)
        db.flush()
        job = AnalysisJob(
            enzyme_entry_id=enzyme.id,
            job_type="homolog_collection",
            status=JobStatus.QUEUED,
            parameters_json={"identity_min": 40, "identity_max": 95, "coverage_min": 70},
        )
        db.add(job)
        db.commit()
        db.refresh(job)

        finish_homology_collection_job(db, job.id, bucket="iee-artifacts")

        db.refresh(job)
        protein_sequence = db.scalar(
            select(ProteinSequence).where(ProteinSequence.enzyme_entry_id == enzyme.id)
        )

    assert protein_sequence is not None
    assert protein_sequence.sequence == "ACDEFGHIKL"
    assert protein_sequence.mature_sequence == "CDEFGHIKL"
    assert job.status == JobStatus.FINISHED
    assert job.result_summary_json["message"] == "homolog collection completed"


def test_homolog_candidates_for_job_caps_real_provider_request_size(monkeypatch):
    fake_client = _FakeUniProtClient()
    monkeypatch.setattr("worker.jobs.get_uniprot_client", lambda: fake_client)
    enzyme = EnzymeEntry(
        name="Test transglutaminase",
        ec_number="2.3.2.13",
        source="test",
    )

    candidates, runner = _homolog_candidates_for_job(
        enzyme,
        query_sequence="ACDEFGHIKL",
        max_sequences=500,
        provider_fetch_size=25,
        search_mode="metadata_search",
        use_real_provider=True,
        allow_fallback=True,
    )

    assert fake_client.searches == [("keyword", 100), ("ec", 99)]
    assert candidates[0].accession == "REAL_HOMOLOG_1"
    assert runner["provider"] == "uniprot"
    assert runner["mode"] == "real"
    assert runner["candidate_count"] == 1
    assert runner["requested_size"] == 100


def test_homolog_candidate_pool_expands_for_larger_final_max_sequences(monkeypatch):
    fake_client = _FakeUniProtClient()
    monkeypatch.setattr("worker.jobs.get_uniprot_client", lambda: fake_client)
    enzyme = EnzymeEntry(
        name="Test transglutaminase",
        ec_number="2.3.2.13",
        source="test",
    )

    _homolog_candidates_for_job(
        enzyme,
        query_sequence="ACDEFGHIKL",
        max_sequences=100,
        provider_fetch_size=25,
        search_mode="metadata_search",
        use_real_provider=True,
        allow_fallback=True,
    )

    assert fake_client.searches == [("keyword", 100), ("ec", 99)]


def test_homolog_candidate_pool_is_independent_from_final_max_sequences(monkeypatch):
    fake_client = _FakeUniProtClient()
    monkeypatch.setattr("worker.jobs.get_uniprot_client", lambda: fake_client)
    enzyme = EnzymeEntry(
        name="Test transglutaminase",
        ec_number="2.3.2.13",
        source="test",
    )

    _homolog_candidates_for_job(
        enzyme,
        query_sequence="ACDEFGHIKL",
        max_sequences=10,
        provider_fetch_size=25,
        search_mode="metadata_search",
        use_real_provider=True,
        allow_fallback=True,
    )

    assert fake_client.searches == [("keyword", 25), ("ec", 24)]


def test_sequence_similarity_homolog_mode_uses_local_fasta_runner(tmp_path):
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
    enzyme = EnzymeEntry(
        name="Test transglutaminase",
        ec_number="2.3.2.13",
        source="test",
    )

    candidates, runner = _homolog_candidates_for_job(
        enzyme,
        query_sequence="ACDEFGHIKL",
        max_sequences=25,
        provider_fetch_size=25,
        search_mode="sequence_similarity",
        use_real_provider=True,
        allow_fallback=False,
        sequence_similarity_fasta_path=str(fasta_path),
    )

    assert [candidate.accession for candidate in candidates[:2]] == ["EXACT", "NEAR"]
    assert candidates[1].organism == "Streptomyces testensis"
    assert runner["provider"] == "local_fasta_similarity"
    assert runner["mode"] == "real"
    assert runner["search_mode"] == "sequence_similarity"
    assert runner["candidate_count"] == 3


def test_sequence_similarity_homolog_mode_prefers_configured_command(tmp_path):
    fasta_path = tmp_path / "homologs.fasta"
    fasta_path.write_text(
        "\n".join(
            [
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
        "print('NEAR\\t90\\t100')\n",
        encoding="utf-8",
    )
    enzyme = EnzymeEntry(
        name="Test transglutaminase",
        ec_number="2.3.2.13",
        source="test",
    )

    candidates, runner = _homolog_candidates_for_job(
        enzyme,
        query_sequence="ACDEFGHIKL",
        max_sequences=25,
        provider_fetch_size=25,
        search_mode="sequence_similarity",
        use_real_provider=True,
        allow_fallback=False,
        sequence_similarity_fasta_path=str(fasta_path),
        sequence_similarity_command=f"python {script}",
    )

    assert [candidate.accession for candidate in candidates] == ["NEAR"]
    assert candidates[0].source == "sequence_similarity_command"
    assert runner["provider"] == "sequence_similarity_command"
    assert runner["mode"] == "real"
    assert runner["candidate_count"] == 1


def test_sequence_similarity_homolog_command_failure_falls_back_to_local_fasta(tmp_path):
    fasta_path = tmp_path / "homologs.fasta"
    fasta_path.write_text(
        "\n".join(
            [
                ">NEAR near homolog OS=Streptomyces testensis",
                "ACDEFGHIVL",
            ]
        ),
        encoding="utf-8",
    )
    script = tmp_path / "failing_similarity.py"
    script.write_text(
        "import sys\n"
        "print('tool unavailable', file=sys.stderr)\n"
        "raise SystemExit(2)\n",
        encoding="utf-8",
    )
    enzyme = EnzymeEntry(
        name="Test transglutaminase",
        ec_number="2.3.2.13",
        source="test",
    )

    candidates, runner = _homolog_candidates_for_job(
        enzyme,
        query_sequence="ACDEFGHIKL",
        max_sequences=25,
        provider_fetch_size=25,
        search_mode="sequence_similarity",
        use_real_provider=True,
        allow_fallback=True,
        sequence_similarity_fasta_path=str(fasta_path),
        sequence_similarity_command=f"python {script}",
    )

    assert [candidate.accession for candidate in candidates] == ["NEAR"]
    assert candidates[0].source == "local_fasta_similarity"
    assert runner["provider"] == "sequence_similarity_command"
    assert runner["mode"] == "fallback"
    assert "tool unavailable" in runner["warning"]


def test_sequence_similarity_homolog_empty_command_hits_fall_back_to_local_fasta(tmp_path):
    fasta_path = tmp_path / "homologs.fasta"
    fasta_path.write_text(
        "\n".join(
            [
                ">NEAR near homolog OS=Streptomyces testensis",
                "ACDEFGHIVL",
            ]
        ),
        encoding="utf-8",
    )
    script = tmp_path / "empty_similarity.py"
    script.write_text(
        "import sys\n"
        "sys.stdin.read()\n",
        encoding="utf-8",
    )
    enzyme = EnzymeEntry(
        name="Test transglutaminase",
        ec_number="2.3.2.13",
        source="test",
    )

    candidates, runner = _homolog_candidates_for_job(
        enzyme,
        query_sequence="ACDEFGHIKL",
        max_sequences=25,
        provider_fetch_size=25,
        search_mode="sequence_similarity",
        use_real_provider=True,
        allow_fallback=True,
        sequence_similarity_fasta_path=str(fasta_path),
        sequence_similarity_command=f"python {script}",
    )

    assert [candidate.accession for candidate in candidates] == ["NEAR"]
    assert candidates[0].source == "local_fasta_similarity"
    assert runner["provider"] == "sequence_similarity_command"
    assert runner["mode"] == "fallback"
    assert "returned no candidates" in runner["warning"]


def test_sequence_similarity_homolog_mode_reports_unavailable_runner():
    enzyme = EnzymeEntry(
        name="Test transglutaminase",
        ec_number="2.3.2.13",
        source="test",
    )

    candidates, runner = _homolog_candidates_for_job(
        enzyme,
        query_sequence="ACDEFGHIKL",
        max_sequences=25,
        provider_fetch_size=25,
        search_mode="sequence_similarity",
        use_real_provider=True,
        allow_fallback=True,
        sequence_similarity_fasta_path=None,
    )

    assert candidates[0].accession == "MOCK_EXACT"
    assert runner["provider"] == "sequence_similarity"
    assert runner["mode"] == "fallback"
    assert runner["search_mode"] == "sequence_similarity"
    assert "BLAST/MMseqs2" in runner["warning"]


def test_finish_msa_job_creates_msa_artifact_from_target_sequence(monkeypatch):
    class RealButFallbackSettings:
        use_real_science_providers = False
        allow_science_fallbacks = True
        mafft_bin = None

    monkeypatch.setattr("worker.jobs.get_settings", lambda: RealButFallbackSettings(), raising=False)

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with SessionLocal() as db:
        family = EnzymeFamily(
            module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
            name="Mature microbial transglutaminases",
        )
        db.add(family)
        db.flush()
        enzyme = EnzymeEntry(
            family_id=family.id,
            name="Worker MSA test mTGase",
            source="test",
        )
        db.add(enzyme)
        db.flush()
        enzyme_id = enzyme.id
        db.add(
            ProteinSequence(
                enzyme_entry_id=enzyme_id,
                sequence="ACDEFGHIKL",
                mature_sequence="ACDEFGHIKL",
                source="test",
                checksum="worker-msa-test-sequence",
            )
        )
        job = AnalysisJob(
            enzyme_entry_id=enzyme_id,
            job_type="msa",
            status=JobStatus.QUEUED,
            parameters_json={
                "homologs": [
                    {"identifier": "homolog_1", "sequence": "ACDEFGHIVL"},
                    {"identifier": "homolog_2", "sequence": "ACDEYGHIKL"},
                ]
            },
        )
        db.add(job)
        db.commit()
        db.refresh(job)

        finish_msa_job(db, job.id, bucket="iee-artifacts")

        db.refresh(job)
        artifact = db.scalar(
            select(AnalysisArtifact).where(
                AnalysisArtifact.job_id == job.id,
                AnalysisArtifact.artifact_type == "msa",
            )
        )

    assert job.status == JobStatus.FINISHED
    assert job.result_summary_json["message"] == "MSA completed"
    assert job.result_summary_json["sequence_count"] == 3
    assert job.result_summary_json["alignment_length"] == 10
    assert job.result_summary_json["artifact_type"] == "msa"
    assert (
        job.result_summary_json["msa_fasta"]
        == ">query\nACDEFGHIKL\n>homolog_1\nACDEFGHIVL\n>homolog_2\nACDEYGHIKL\n"
    )
    assert job.result_summary_json["runner"]["provider"] == "mafft"
    assert job.result_summary_json["runner"]["mode"] == "fallback"
    assert (
        job.result_summary_json["runner"]["warning"]
        == "MAFFT executable not configured; mock alignment used."
    )
    assert artifact is not None
    assert artifact.enzyme_entry_id == enzyme_id
    assert artifact.bucket == "iee-artifacts"
    assert artifact.object_key == f"analysis-jobs/{job.id}/msa.fasta"
    assert artifact.content_type == "text/x-fasta"
    assert artifact.size_bytes > 0
    assert artifact.checksum is not None


def test_finish_conservation_profile_job_creates_conservation_artifact():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with SessionLocal() as db:
        family = EnzymeFamily(
            module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
            name="Mature microbial transglutaminases",
        )
        db.add(family)
        db.flush()
        enzyme = EnzymeEntry(
            family_id=family.id,
            name="Worker conservation test mTGase",
            source="test",
        )
        db.add(enzyme)
        db.flush()
        enzyme_id = enzyme.id
        db.add(
            ProteinSequence(
                enzyme_entry_id=enzyme_id,
                sequence="ACD",
                mature_sequence="ACD",
                source="test",
                checksum="worker-conservation-test-sequence",
            )
        )
        job = AnalysisJob(
            enzyme_entry_id=enzyme_id,
            job_type="conservation_profile",
            status=JobStatus.QUEUED,
            parameters_json={
                "aligned_records": [
                    {"identifier": "query", "aligned_sequence": "ACD"},
                    {"identifier": "homolog_1", "aligned_sequence": "ACD"},
                    {"identifier": "homolog_2", "aligned_sequence": "ACE"},
                    {"identifier": "homolog_3", "aligned_sequence": "A-D"},
                ]
            },
        )
        db.add(job)
        db.commit()
        db.refresh(job)

        finish_conservation_profile_job(db, job.id, bucket="iee-artifacts")

        db.refresh(job)
        artifact = db.scalar(
            select(AnalysisArtifact).where(
                AnalysisArtifact.job_id == job.id,
                AnalysisArtifact.artifact_type == "conservation_profile",
            )
        )

    assert job.status == JobStatus.FINISHED
    assert job.result_summary_json == {
        "message": "conservation profile completed",
        "site_count": 3,
        "sequence_count": 4,
        "artifact_type": "conservation_profile",
        "sites": [
            {
                "query_position": 1,
                "alignment_column": 1,
                "wildtype_residue": "A",
                "shannon_entropy": 0.0,
                "wildtype_frequency": 1.0,
                "conservation_category": "highly_conserved",
            },
            {
                "query_position": 2,
                "alignment_column": 2,
                "wildtype_residue": "C",
                "shannon_entropy": 0.811,
                "wildtype_frequency": 0.75,
                "conservation_category": "moderately_conserved",
            },
            {
                "query_position": 3,
                "alignment_column": 3,
                "wildtype_residue": "D",
                "shannon_entropy": 0.811,
                "wildtype_frequency": 0.75,
                "conservation_category": "moderately_conserved",
            },
        ],
    }
    assert artifact is not None
    assert artifact.enzyme_entry_id == enzyme_id
    assert artifact.bucket == "iee-artifacts"
    assert artifact.object_key == f"analysis-jobs/{job.id}/conservation-profile.json"
    assert artifact.content_type == "application/json"
    assert artifact.size_bytes > 0
    assert artifact.checksum is not None


def test_finish_mutation_recommendation_job_creates_hotspot_artifact():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with SessionLocal() as db:
        family = EnzymeFamily(
            module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
            name="Worker recommendation family",
        )
        db.add(family)
        db.flush()
        enzyme = EnzymeEntry(
            family_id=family.id,
            name="Worker recommendation test mTGase",
            organism="Streptomyces mobaraensis",
            source="test",
        )
        db.add(enzyme)
        db.flush()
        db.add(
            ProteinSequence(
                enzyme_entry_id=enzyme.id,
                sequence="ACDEFGHIKL",
                mature_sequence="ACDEFGHIKL",
                source="test",
                checksum="worker-recommendation-sequence",
            )
        )
        job = AnalysisJob(
            enzyme_entry_id=enzyme.id,
            job_type="mutation_recommendation",
            status=JobStatus.QUEUED,
            parameters_json={
                "conservation_sites": [
                    {
                        "query_position": 1,
                        "wildtype_residue": "A",
                        "shannon_entropy": 0.0,
                        "wildtype_frequency": 1.0,
                        "conservation_category": "highly_conserved",
                    },
                    {
                        "query_position": 8,
                        "wildtype_residue": "I",
                        "shannon_entropy": 0.918,
                        "wildtype_frequency": 0.667,
                        "conservation_category": "moderately_conserved",
                    },
                    {
                        "query_position": 10,
                        "wildtype_residue": "L",
                        "shannon_entropy": 1.2,
                        "wildtype_frequency": 0.4,
                        "conservation_category": "variable",
                    },
                ],
                "rosetta_results": [
                    {
                        "mutation_string": "L10A",
                        "ddg_kcal_per_mol": -0.8,
                        "interpretation": "stabilizing",
                    }
                ],
                "mutation_records": [
                    {
                        "mutation_string": "L10A",
                        "property_delta": {"optimal_temperature_delta_degC": 5},
                    }
                ],
                "structure_id": "structure-selected",
                "target_property": "thermostability",
            },
        )
        db.add(job)
        db.commit()

        finish_mutation_recommendation_job(db, job.id, bucket="iee-artifacts")

        artifact = db.scalar(
            select(AnalysisArtifact).where(
                AnalysisArtifact.job_id == job.id,
                AnalysisArtifact.artifact_type == "mutation_recommendations",
            )
        )

    assert job.status == JobStatus.FINISHED
    assert job.result_summary_json["message"] == "mutation recommendation completed"
    assert job.result_summary_json["artifact_type"] == "mutation_recommendations"
    assert job.result_summary_json["structure_id"] == "structure-selected"
    assert job.result_summary_json["target_property"] == "thermostability"
    assert [candidate["query_position"] for candidate in job.result_summary_json["candidates"]] == [10, 8]
    assert job.result_summary_json["candidates"][0]["suggested_mutations"] == ["L10A", "L10V", "L10S"]
    scored_suggestions = job.result_summary_json["candidates"][0]["scored_suggestions"]
    assert scored_suggestions[0]["mutation_string"] == "L10A"
    assert scored_suggestions[0]["total_score"] > scored_suggestions[1]["total_score"]
    assert [component["name"] for component in scored_suggestions[0]["components"]] == [
        "conservation_tolerance",
        "reported_benefit",
        "structure_proximity",
        "rosetta_stability",
        "solubility",
        "thermostability_score",
        "opt_temperature_score",
        "opt_pH_score",
        "activity_retention_score",
        "surface_charge_score",
        "solubility_score",
    ]
    assert "medium_solubility_risk" in scored_suggestions[0]["risk_summary"]
    assert "mature_enzyme_only" in scored_suggestions[0]["risk_summary"]
    assert artifact is not None
    assert artifact.object_key == f"analysis-jobs/{job.id}/mutation-recommendations.json"
    assert artifact.content_type == "application/json"
    assert artifact.size_bytes > 0


def test_finish_rosetta_ddg_job_creates_mock_ddg_artifact(monkeypatch):
    class RealButFallbackSettings:
        allow_science_fallbacks = True
        rosetta_ddg_command = None
        rosetta_ddg_bin = None

    monkeypatch.setattr("worker.jobs.get_settings", lambda: RealButFallbackSettings(), raising=False)

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with SessionLocal() as db:
        family = EnzymeFamily(
            module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
            name="Worker Rosetta family",
        )
        db.add(family)
        db.flush()
        enzyme = EnzymeEntry(
            family_id=family.id,
            name="Worker Rosetta test mTGase",
            organism="Streptomyces mobaraensis",
            source="test",
        )
        db.add(enzyme)
        db.flush()
        job = AnalysisJob(
            enzyme_entry_id=enzyme.id,
            job_type="rosetta_ddg",
            status=JobStatus.QUEUED,
            parameters_json={"mutation_string": "L10A", "structure_id": "structure-1"},
        )
        db.add(job)
        db.commit()

        finish_rosetta_ddg_job(db, job.id, bucket="iee-artifacts")

        artifact = db.scalar(
            select(AnalysisArtifact).where(
                AnalysisArtifact.job_id == job.id,
                AnalysisArtifact.artifact_type == "rosetta_ddg",
            )
        )

    assert job.status == JobStatus.FINISHED
    assert job.result_summary_json["message"] == "Rosetta ddG completed"
    assert job.result_summary_json["mutation_string"] == "L10A"
    assert job.result_summary_json["mutation_file"] == "L 10 A"
    assert job.result_summary_json["ddg_kcal_per_mol"] == -0.6
    assert job.result_summary_json["artifact_type"] == "rosetta_ddg"
    assert job.result_summary_json["runner"]["provider"] == "rosetta"
    assert job.result_summary_json["runner"]["mode"] == "fallback"
    assert artifact is not None
    assert artifact.object_key == f"analysis-jobs/{job.id}/rosetta-ddg.json"
    assert artifact.content_type == "application/json"
    assert artifact.size_bytes > 0


def test_finish_library_design_job_creates_mutation_library_artifact():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with SessionLocal() as db:
        family = EnzymeFamily(
            module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
            name="Worker library family",
        )
        db.add(family)
        db.flush()
        enzyme = EnzymeEntry(
            family_id=family.id,
            name="Worker library test mTGase",
            organism="Streptomyces mobaraensis",
            source="test",
        )
        db.add(enzyme)
        db.flush()
        job = AnalysisJob(
            enzyme_entry_id=enzyme.id,
            job_type="library_design",
            status=JobStatus.QUEUED,
            parameters_json={
                "library_size": 6,
                "max_order": 2,
                "plate_format": 96,
                "recommendation_candidates": [
                    {
                        "query_position": 10,
                        "wildtype_residue": "L",
                        "conservation_category": "variable",
                        "priority_score": 1.8,
                        "suggested_mutations": ["L10A"],
                    },
                    {
                        "query_position": 12,
                        "wildtype_residue": "F",
                        "conservation_category": "moderately_conserved",
                        "priority_score": 1.2,
                        "suggested_mutations": ["F12A"],
                    },
                ],
                "rosetta_results": [
                    {
                        "mutation_string": "L10A",
                        "ddg_kcal_per_mol": -0.6,
                        "interpretation": "stabilizing",
                    }
                ],
            },
        )
        db.add(job)
        db.commit()

        finish_library_design_job(db, job.id, bucket="iee-artifacts")

        artifact = db.scalar(
            select(AnalysisArtifact).where(
                AnalysisArtifact.job_id == job.id,
                AnalysisArtifact.artifact_type == "mutation_library",
            )
        )

    assert job.status == JobStatus.FINISHED
    assert job.result_summary_json["message"] == "mutation library design completed"
    assert job.result_summary_json["artifact_type"] == "mutation_library"
    assert job.result_summary_json["variant_count"] > 0
    assert job.result_summary_json["plate_layout"][0]["role"] == "wt_control"
    assert job.result_summary_json["plate_layout"][1]["role"] == "blank_control"
    assert job.result_summary_json["csv_text"].startswith("well,variant_id")
    assert artifact is not None
    assert artifact.object_key == f"analysis-jobs/{job.id}/mutation-library.json"
    assert artifact.content_type == "application/json"
    assert artifact.size_bytes > 0


def test_mark_job_failed_records_error_message():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with SessionLocal() as db:
        job = AnalysisJob(job_type="family_profile_summary", status=JobStatus.RUNNING)
        db.add(job)
        db.commit()
        db.refresh(job)

        mark_job_failed(db, job.id, "Rosetta executable missing")

        db.refresh(job)

    assert job.status == JobStatus.FAILED
    assert job.error_message == "Rosetta executable missing"
    assert job.finished_at is not None
