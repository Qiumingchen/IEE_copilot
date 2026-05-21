# Real Science Adapters Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace silent mock scientific paths with configurable real provider and runner boundaries that always report provenance and fallback status.

**Architecture:** Keep the existing FastAPI, worker, SQLAlchemy, and Next.js routes. Add small focused adapter utilities under `apps/api/app/services` and `apps/api/app/external`, then wire them into the existing search, MSA, Rosetta, artifact, and frontend analysis flows. Tests must use local fixtures or fake executables; no test may require live internet.

**Tech Stack:** FastAPI, SQLAlchemy, Celery worker functions, httpx, pytest, Next.js, TypeScript utility tests.

---

## File Structure

- Create `apps/api/app/services/provenance.py`: shared provider/runner provenance helpers.
- Create `apps/api/app/services/msa_runner.py`: MAFFT real/fallback runner boundary.
- Create `apps/api/app/services/rosetta_runner.py`: Rosetta real/fallback runner boundary.
- Modify `apps/api/app/core/config.py`: add science adapter configuration.
- Modify `apps/api/app/external/uniprot.py`: add real response parsing and configurable client selection.
- Modify `apps/api/app/external/rcsb.py`: add real metadata parsing and configurable client selection.
- Modify `apps/api/app/external/alphafold.py`: add real prediction parsing and configurable client selection.
- Modify `apps/api/app/external/literature.py`: add real metadata parsing and configurable client selection.
- Modify `apps/worker/worker/jobs.py`: use `msa_runner` and `rosetta_runner`, store provenance in result summaries.
- Modify `apps/api/app/api/routes/enzyme_records.py`: include runner/provenance content in artifact responses.
- Modify `apps/web/lib/types.ts`: add optional provenance/runner fields to artifact content types.
- Modify `apps/web/app/enzymes/[id]/analysis/analysis-utils.ts`: extract provenance display state.
- Modify `apps/web/app/enzymes/[id]/analysis/AnalysisClient.tsx`: show real/fallback/unavailable labels and warnings.
- Modify `README.md`: document environment variables for real providers and runners.
- Add/update tests under `apps/api/tests`, `apps/worker/tests`, and `apps/web/tests`.

---

### Task 1: Provenance Helpers And Settings

**Files:**
- Create: `apps/api/app/services/provenance.py`
- Modify: `apps/api/app/core/config.py`
- Test: `apps/api/tests/test_science_provenance.py`

- [ ] **Step 1: Write the failing provenance helper tests**

Add `apps/api/tests/test_science_provenance.py`:

```python
from app.services.provenance import build_fallback_provenance, build_real_provenance


def test_build_real_provenance_records_provider_mode_and_url():
    provenance = build_real_provenance(
        provider="uniprot",
        source_url="https://rest.uniprot.org/uniprotkb/P81453",
        version="api-v1",
    )

    assert provenance["provider"] == "uniprot"
    assert provenance["mode"] == "real"
    assert provenance["source_url"] == "https://rest.uniprot.org/uniprotkb/P81453"
    assert provenance["version"] == "api-v1"
    assert provenance["retrieved_at"].endswith("Z")


def test_build_fallback_provenance_records_warning():
    provenance = build_fallback_provenance(
        provider="mafft",
        warning="MAFFT executable not configured; mock alignment used.",
    )

    assert provenance["provider"] == "mafft"
    assert provenance["mode"] == "fallback"
    assert provenance["warning"] == "MAFFT executable not configured; mock alignment used."
    assert provenance["retrieved_at"].endswith("Z")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker compose exec api pytest apps/api/tests/test_science_provenance.py -q`

Expected: FAIL because `app.services.provenance` does not exist.

- [ ] **Step 3: Add provenance helper implementation**

Create `apps/api/app/services/provenance.py`:

```python
from datetime import datetime, timezone
from typing import Any


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_real_provenance(
    *,
    provider: str,
    source_url: str | None = None,
    version: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    provenance: dict[str, Any] = {
        "provider": provider,
        "mode": "real",
        "retrieved_at": utc_timestamp(),
    }
    if source_url:
        provenance["source_url"] = source_url
    if version:
        provenance["version"] = version
    if extra:
        provenance.update(extra)
    return provenance


def build_fallback_provenance(
    *,
    provider: str,
    warning: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    provenance: dict[str, Any] = {
        "provider": provider,
        "mode": "fallback",
        "retrieved_at": utc_timestamp(),
        "warning": warning,
    }
    if extra:
        provenance.update(extra)
    return provenance
```

Modify `apps/api/app/core/config.py` by adding these fields to `Settings`:

```python
    allow_science_fallbacks: bool = True
    use_real_science_providers: bool = False
    mafft_bin: str | None = None
    rosetta_ddg_bin: str | None = None
    rosetta_ddg_command: str | None = None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker compose exec api pytest apps/api/tests/test_science_provenance.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/services/provenance.py apps/api/app/core/config.py apps/api/tests/test_science_provenance.py
git commit -m "feat(api): add science provenance helpers"
```

---

### Task 2: UniProt Real Parsing And Configurable Selection

**Files:**
- Modify: `apps/api/app/external/uniprot.py`
- Test: `apps/api/tests/test_uniprot_connector.py`

- [ ] **Step 1: Write failing UniProt parsing and selection tests**

Append to `apps/api/tests/test_uniprot_connector.py`:

```python
from app.external.uniprot import RealUniProtClient, get_uniprot_client, parse_uniprot_entry_payload


def test_parse_uniprot_entry_payload_extracts_core_fields():
    payload = {
        "primaryAccession": "P81453",
        "proteinDescription": {
            "recommendedName": {
                "fullName": {"value": "Protein-glutamine gamma-glutamyltransferase"},
                "ecNumbers": [{"value": "2.3.2.13"}],
            }
        },
        "organism": {"scientificName": "Streptomyces mobaraensis"},
        "sequence": {"value": "ACDEFG"},
        "uniProtKBCrossReferences": [
            {"database": "AlphaFoldDB", "id": "AF-P81453-F1"},
            {"database": "PDB", "id": "1IU4"},
        ],
    }

    entry = parse_uniprot_entry_payload(payload)

    assert entry.accession == "P81453"
    assert entry.protein_name == "Protein-glutamine gamma-glutamyltransferase"
    assert entry.organism == "Streptomyces mobaraensis"
    assert entry.ec_number == "2.3.2.13"
    assert entry.sequence == "ACDEFG"
    assert entry.cross_references["AlphaFoldDB"] == "AF-P81453-F1"
    assert entry.cross_references["PDB"] == "1IU4"


def test_get_uniprot_client_returns_real_client_when_enabled(monkeypatch):
    monkeypatch.setenv("USE_REAL_SCIENCE_PROVIDERS", "true")

    client = get_uniprot_client()

    assert isinstance(client, RealUniProtClient)
    assert client.source == "uniprot"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker compose exec api pytest apps/api/tests/test_uniprot_connector.py -q`

Expected: FAIL because `RealUniProtClient` and `parse_uniprot_entry_payload` are not defined or not wired.

- [ ] **Step 3: Implement parser and real client selection**

In `apps/api/app/external/uniprot.py`, add:

```python
from app.core.config import get_settings
from app.services.provenance import build_real_provenance


def _first_ec_number(description: dict) -> str | None:
    recommended = description.get("recommendedName") or {}
    ec_numbers = recommended.get("ecNumbers") or []
    if ec_numbers and isinstance(ec_numbers[0], dict):
        return ec_numbers[0].get("value")
    return None


def _protein_name(description: dict) -> str:
    recommended = description.get("recommendedName") or {}
    full_name = recommended.get("fullName") or {}
    return full_name.get("value") or "Unknown UniProt protein"


def parse_uniprot_entry_payload(payload: dict) -> UniProtEntry:
    cross_references = {
        str(item.get("database")): str(item.get("id"))
        for item in payload.get("uniProtKBCrossReferences", [])
        if item.get("database") and item.get("id")
    }
    description = payload.get("proteinDescription") or {}
    return UniProtEntry(
        accession=str(payload.get("primaryAccession") or ""),
        protein_name=_protein_name(description),
        organism=(payload.get("organism") or {}).get("scientificName"),
        ec_number=_first_ec_number(description),
        sequence=(payload.get("sequence") or {}).get("value"),
        cross_references=cross_references,
    )


def parse_uniprot_search_hits(payload: dict) -> list[UniProtSearchHit]:
    hits = []
    for item in payload.get("results", []):
        entry = parse_uniprot_entry_payload(item)
        hits.append(
            UniProtSearchHit(
                accession=entry.accession,
                protein_name=entry.protein_name,
                organism=entry.organism,
                ec_number=entry.ec_number,
                score=item.get("score"),
            )
        )
    return hits


class RealUniProtClient:
    source = "uniprot"
    base_url = "https://rest.uniprot.org"

    def __init__(self, timeout: float = 15.0):
        self.timeout = timeout

    def search_by_keyword(self, keyword: str, size: int = 5) -> list[UniProtSearchHit]:
        params = {"query": keyword, "format": "json", "size": size}
        response = httpx.get(f"{self.base_url}/uniprotkb/search", params=params, timeout=self.timeout)
        response.raise_for_status()
        return parse_uniprot_search_hits(response.json())[:size]

    def search_by_ec(self, ec_number: str, size: int = 5) -> list[UniProtSearchHit]:
        return self.search_by_keyword(f"ec:{ec_number}", size=size)

    def search_by_organism(self, organism: str, size: int = 5) -> list[UniProtSearchHit]:
        return self.search_by_keyword(f"organism_name:{organism}", size=size)

    def fetch_entry(self, accession: str) -> UniProtEntry:
        response = httpx.get(f"{self.base_url}/uniprotkb/{accession}.json", timeout=self.timeout)
        response.raise_for_status()
        entry = parse_uniprot_entry_payload(response.json())
        entry.cross_references["provenance"] = build_real_provenance(
            provider="uniprot",
            source_url=f"{self.base_url}/uniprotkb/{accession}.json",
        )
        return entry

    def fetch_fasta(self, accession: str) -> str:
        response = httpx.get(f"{self.base_url}/uniprotkb/{accession}.fasta", timeout=self.timeout)
        response.raise_for_status()
        return response.text

    def fetch_cross_references(self, accession: str) -> dict[str, str]:
        return self.fetch_entry(accession).cross_references
```

Replace `get_uniprot_client` with:

```python
def get_uniprot_client() -> MockUniProtClient | RealUniProtClient:
    if get_settings().use_real_science_providers:
        return RealUniProtClient()
    return MockUniProtClient()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker compose exec api pytest apps/api/tests/test_uniprot_connector.py apps/api/tests/test_search_flow.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/external/uniprot.py apps/api/tests/test_uniprot_connector.py
git commit -m "feat(api): add real uniprot adapter"
```

---

### Task 3: RCSB, AlphaFold, And Literature Real Parsers

**Files:**
- Modify: `apps/api/app/external/rcsb.py`
- Modify: `apps/api/app/external/alphafold.py`
- Modify: `apps/api/app/external/literature.py`
- Test: `apps/api/tests/test_rcsb_connector.py`
- Test: `apps/api/tests/test_alphafold_connector.py`
- Test: `apps/api/tests/test_literature_connector.py`

- [ ] **Step 1: Write failing real parser tests**

Append to `apps/api/tests/test_rcsb_connector.py`:

```python
from app.external.rcsb import RealRcsbClient, get_rcsb_client, parse_rcsb_entry_payload


def test_parse_rcsb_entry_payload_extracts_structure_metadata():
    payload = {
        "rcsb_id": "1IU4",
        "struct": {"title": "Microbial transglutaminase structure"},
        "exptl": [{"method": "X-RAY DIFFRACTION"}],
        "rcsb_entry_info": {"resolution_combined": [2.1], "polymer_entity_count_protein": 1},
        "rcsb_entity_source_organism": [{"scientific_name": "Streptomyces mobaraensis"}],
    }

    metadata = parse_rcsb_entry_payload(payload)

    assert metadata.pdb_id == "1IU4"
    assert metadata.title == "Microbial transglutaminase structure"
    assert metadata.method == "X-RAY DIFFRACTION"
    assert metadata.resolution == 2.1
    assert metadata.organism == "Streptomyces mobaraensis"
    assert metadata.chain_summary["polymer_entity_count"] == 1


def test_get_rcsb_client_returns_real_client_when_enabled(monkeypatch):
    monkeypatch.setenv("USE_REAL_SCIENCE_PROVIDERS", "true")

    assert isinstance(get_rcsb_client(), RealRcsbClient)
```

Append to `apps/api/tests/test_alphafold_connector.py`:

```python
from app.external.alphafold import RealAlphaFoldClient, get_alphafold_client, parse_alphafold_prediction


def test_parse_alphafold_prediction_extracts_model_metadata():
    payload = [
        {
            "entryId": "AF-P81453-F1",
            "uniprotAccession": "P81453",
            "pdbUrl": "https://alphafold.ebi.ac.uk/files/AF-P81453-F1-model_v4.pdb",
            "paeDocUrl": "https://alphafold.ebi.ac.uk/files/AF-P81453-F1-predicted_aligned_error_v4.json",
            "confidenceScore": 91.2,
        }
    ]

    model = parse_alphafold_prediction(payload)

    assert model.model_id == "AF-P81453-F1"
    assert model.uniprot_id == "P81453"
    assert model.structure_url.endswith(".pdb")
    assert model.confidence_summary["mean_plddt"] == 91.2


def test_get_alphafold_client_returns_real_client_when_enabled(monkeypatch):
    monkeypatch.setenv("USE_REAL_SCIENCE_PROVIDERS", "true")

    assert isinstance(get_alphafold_client(), RealAlphaFoldClient)
```

Append to `apps/api/tests/test_literature_connector.py`:

```python
from app.external.literature import RealLiteratureClient, get_literature_client, parse_crossref_item


def test_parse_crossref_item_extracts_literature_metadata():
    item = {
        "title": ["Enzyme engineering by mutation"],
        "author": [{"given": "Ada", "family": "Lovelace"}, {"given": "Q", "family": "Tester"}],
        "container-title": ["Biocatalysis Reports"],
        "published-print": {"date-parts": [[2025, 1, 1]]},
        "DOI": "10.1000/example",
        "abstract": "<jats:p>Reports variants.</jats:p>",
    }

    metadata = parse_crossref_item(item)

    assert metadata.title == "Enzyme engineering by mutation"
    assert metadata.authors == "Ada Lovelace; Q Tester"
    assert metadata.journal == "Biocatalysis Reports"
    assert metadata.year == 2025
    assert metadata.doi == "10.1000/example"
    assert metadata.source == "crossref"


def test_get_literature_client_returns_real_client_when_enabled(monkeypatch):
    monkeypatch.setenv("USE_REAL_SCIENCE_PROVIDERS", "true")

    assert isinstance(get_literature_client(), RealLiteratureClient)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker compose exec api pytest apps/api/tests/test_rcsb_connector.py apps/api/tests/test_alphafold_connector.py apps/api/tests/test_literature_connector.py -q`

Expected: FAIL because real parser classes/functions are not defined.

- [ ] **Step 3: Implement real parsers and selection**

Add focused parser functions and `Real*Client` classes in each external module. Use synchronous `httpx.get` methods to match the current route call style. Each `get_*_client` should return the real client when `get_settings().use_real_science_providers` is true, otherwise return the existing mock client.

Use these parser contracts:

```python
def parse_rcsb_entry_payload(payload: dict) -> RcsbStructureMetadata:
    resolution_values = (payload.get("rcsb_entry_info") or {}).get("resolution_combined") or []
    organism_rows = payload.get("rcsb_entity_source_organism") or []
    return RcsbStructureMetadata(
        pdb_id=str(payload.get("rcsb_id") or "").upper(),
        title=(payload.get("struct") or {}).get("title") or "Unknown RCSB structure",
        method=((payload.get("exptl") or [{}])[0]).get("method"),
        resolution=resolution_values[0] if resolution_values else None,
        organism=(organism_rows[0] or {}).get("scientific_name") if organism_rows else None,
        chain_summary={
            "polymer_entity_count": (payload.get("rcsb_entry_info") or {}).get("polymer_entity_count_protein")
        },
        ligand_summary={},
    )
```

```python
def parse_alphafold_prediction(payload: list[dict]) -> AlphaFoldModelMetadata:
    if not payload:
        raise ValueError("AlphaFold prediction response is empty")
    item = payload[0]
    return AlphaFoldModelMetadata(
        model_id=str(item.get("entryId") or ""),
        uniprot_id=str(item.get("uniprotAccession") or ""),
        structure_url=str(item.get("pdbUrl") or item.get("cifUrl") or ""),
        confidence_url=str(item.get("paeDocUrl") or ""),
        confidence_summary={"mean_plddt": item.get("confidenceScore")},
    )
```

```python
def parse_crossref_item(item: dict) -> LiteratureMetadata:
    authors = "; ".join(
        " ".join(part for part in [author.get("given"), author.get("family")] if part)
        for author in item.get("author", [])
    ) or None
    date_parts = ((item.get("published-print") or item.get("published-online") or {}).get("date-parts") or [[]])
    return LiteratureMetadata(
        title=(item.get("title") or ["Unknown literature record"])[0],
        authors=authors,
        journal=(item.get("container-title") or [None])[0],
        year=date_parts[0][0] if date_parts and date_parts[0] else None,
        doi=item.get("DOI"),
        abstract=item.get("abstract"),
        source="crossref",
        metadata={"provider": "crossref"},
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker compose exec api pytest apps/api/tests/test_rcsb_connector.py apps/api/tests/test_alphafold_connector.py apps/api/tests/test_literature_connector.py apps/api/tests/test_search_flow.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/external/rcsb.py apps/api/app/external/alphafold.py apps/api/app/external/literature.py apps/api/tests/test_rcsb_connector.py apps/api/tests/test_alphafold_connector.py apps/api/tests/test_literature_connector.py
git commit -m "feat(api): add real structure and literature adapters"
```

---

### Task 4: MAFFT Runner Boundary

**Files:**
- Create: `apps/api/app/services/msa_runner.py`
- Modify: `apps/worker/worker/jobs.py`
- Test: `apps/api/tests/test_msa_runner.py`
- Test: `apps/worker/tests/test_worker_jobs.py`

- [ ] **Step 1: Write failing MAFFT runner tests**

Add `apps/api/tests/test_msa_runner.py`:

```python
from pathlib import Path

import pytest

from app.services.msa import MsaInputSequence
from app.services.msa_runner import run_msa_with_runner


def test_run_msa_with_runner_uses_fallback_when_mafft_missing():
    result = run_msa_with_runner(
        [MsaInputSequence(identifier="query", sequence="ACD")],
        mafft_bin=None,
        allow_fallback=True,
    )

    assert result.alignment.to_fasta() == ">query\nACD\n"
    assert result.runner["provider"] == "mafft"
    assert result.runner["mode"] == "fallback"
    assert "warning" in result.runner


def test_run_msa_with_runner_fails_when_fallback_disabled():
    with pytest.raises(RuntimeError, match="MAFFT executable is not configured"):
        run_msa_with_runner(
            [MsaInputSequence(identifier="query", sequence="ACD")],
            mafft_bin=None,
            allow_fallback=False,
        )


def test_run_msa_with_runner_uses_fake_mafft_executable(tmp_path: Path):
    script = tmp_path / "fake_mafft.py"
    script.write_text(
        "import sys\n"
        "data = sys.stdin.read()\n"
        "print(data.strip())\n",
        encoding="utf-8",
    )

    result = run_msa_with_runner(
        [MsaInputSequence(identifier="query", sequence="ACD")],
        mafft_bin=f"python {script}",
        allow_fallback=False,
    )

    assert result.alignment.to_fasta() == ">query\nACD\n"
    assert result.runner["mode"] == "real"
```

Update `apps/worker/tests/test_worker_jobs.py` MSA assertion to expect `runner.mode == "fallback"` when no MAFFT binary is configured.

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker compose exec api pytest apps/api/tests/test_msa_runner.py -q`

Expected: FAIL because `app.services.msa_runner` does not exist.

- [ ] **Step 3: Implement MAFFT runner**

Create `apps/api/app/services/msa_runner.py`:

```python
from dataclasses import dataclass
import shlex
import subprocess

from app.services.msa import MsaAlignment, MsaInputSequence, run_mock_mafft
from app.services.provenance import build_fallback_provenance, build_real_provenance


@dataclass(frozen=True)
class MsaRunResult:
    alignment: MsaAlignment
    runner: dict
    stderr: str | None = None


def run_msa_with_runner(
    sequences: list[MsaInputSequence],
    *,
    mafft_bin: str | None,
    allow_fallback: bool,
) -> MsaRunResult:
    input_fasta = "".join(f">{sequence.identifier}\n{sequence.sequence}\n" for sequence in sequences)
    if mafft_bin:
        completed = subprocess.run(
            shlex.split(mafft_bin),
            input=input_fasta,
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode == 0 and completed.stdout.strip():
            return MsaRunResult(
                alignment=MsaAlignment.from_fasta(completed.stdout),
                runner=build_real_provenance(provider="mafft", extra={"exit_code": completed.returncode}),
                stderr=completed.stderr or None,
            )
        if not allow_fallback:
            raise RuntimeError(f"MAFFT failed with exit code {completed.returncode}: {completed.stderr}")

    if not allow_fallback:
        raise RuntimeError("MAFFT executable is not configured and science fallbacks are disabled")

    return MsaRunResult(
        alignment=run_mock_mafft(sequences),
        runner=build_fallback_provenance(
            provider="mafft",
            warning="MAFFT executable not configured; mock alignment used.",
        ),
    )
```

If `MsaAlignment.from_fasta` does not exist, add it to `apps/api/app/services/msa.py`:

```python
    @classmethod
    def from_fasta(cls, fasta: str) -> "MsaAlignment":
        records = []
        identifier = None
        sequence_lines = []
        for line in fasta.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith(">"):
                if identifier is not None:
                    records.append(MsaAlignedRecord(identifier=identifier, aligned_sequence="".join(sequence_lines)))
                identifier = stripped[1:].split()[0]
                sequence_lines = []
            else:
                sequence_lines.append(stripped)
        if identifier is not None:
            records.append(MsaAlignedRecord(identifier=identifier, aligned_sequence="".join(sequence_lines)))
        return cls(records=records)
```

Modify `finish_msa_job` in `apps/worker/worker/jobs.py`:

```python
from app.core.config import get_settings
from app.services.msa_runner import run_msa_with_runner
```

Replace `alignment = run_mock_mafft(...)` with:

```python
    settings = get_settings()
    msa_result = run_msa_with_runner(
        [
            MsaInputSequence(identifier="query", sequence=query_sequence),
            *_homolog_inputs_from_job(job),
        ],
        mafft_bin=settings.mafft_bin,
        allow_fallback=settings.allow_science_fallbacks,
    )
    alignment = msa_result.alignment
```

Add `"runner": msa_result.runner` to `job.result_summary_json`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker compose exec api pytest apps/api/tests/test_msa_runner.py apps/api/tests/test_msa_service.py -q`

Run: `docker compose exec worker pytest apps/worker/tests/test_worker_jobs.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/services/msa.py apps/api/app/services/msa_runner.py apps/api/tests/test_msa_runner.py apps/worker/worker/jobs.py apps/worker/tests/test_worker_jobs.py
git commit -m "feat(worker): add mafft runner boundary"
```

---

### Task 5: Rosetta Runner Boundary

**Files:**
- Create: `apps/api/app/services/rosetta_runner.py`
- Modify: `apps/worker/worker/jobs.py`
- Test: `apps/api/tests/test_rosetta_runner.py`
- Test: `apps/worker/tests/test_worker_jobs.py`

- [ ] **Step 1: Write failing Rosetta runner tests**

Add `apps/api/tests/test_rosetta_runner.py`:

```python
from pathlib import Path

import pytest

from app.services.mutations import parse_mutation_string
from app.services.rosetta_runner import run_rosetta_ddg_with_runner


def test_rosetta_runner_uses_fallback_when_command_missing():
    result = run_rosetta_ddg_with_runner(
        mutation_string="L10A",
        mutations=parse_mutation_string("L10A"),
        mutation_file="L 10 A",
        command=None,
        allow_fallback=True,
    )

    assert result.payload["ddg_kcal_per_mol"] == -0.6
    assert result.payload["runner"]["mode"] == "fallback"
    assert result.payload["runner"]["provider"] == "rosetta"


def test_rosetta_runner_fails_when_fallback_disabled():
    with pytest.raises(RuntimeError, match="Rosetta ddG runner is not configured"):
        run_rosetta_ddg_with_runner(
            mutation_string="L10A",
            mutations=parse_mutation_string("L10A"),
            mutation_file="L 10 A",
            command=None,
            allow_fallback=False,
        )


def test_rosetta_runner_parses_fake_runner_output(tmp_path: Path):
    script = tmp_path / "fake_rosetta.py"
    script.write_text(
        "import json\n"
        "print(json.dumps({'ddg_kcal_per_mol': -1.25, 'interpretation': 'stabilizing'}))\n",
        encoding="utf-8",
    )

    result = run_rosetta_ddg_with_runner(
        mutation_string="L10A",
        mutations=parse_mutation_string("L10A"),
        mutation_file="L 10 A",
        command=f"python {script}",
        allow_fallback=False,
    )

    assert result.payload["ddg_kcal_per_mol"] == -1.25
    assert result.payload["interpretation"] == "stabilizing"
    assert result.payload["runner"]["mode"] == "real"
```

Update `apps/worker/tests/test_worker_jobs.py` Rosetta assertion to expect `runner.mode == "fallback"` when no Rosetta command is configured.

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker compose exec api pytest apps/api/tests/test_rosetta_runner.py -q`

Expected: FAIL because `app.services.rosetta_runner` does not exist.

- [ ] **Step 3: Implement Rosetta runner**

Create `apps/api/app/services/rosetta_runner.py`:

```python
from dataclasses import dataclass
import json
import shlex
import subprocess
from typing import Any

from app.services.mutations import ParsedMutation
from app.services.provenance import build_fallback_provenance, build_real_provenance


@dataclass(frozen=True)
class RosettaRunResult:
    payload: dict[str, Any]


def run_rosetta_ddg_with_runner(
    *,
    mutation_string: str,
    mutations: list[ParsedMutation],
    mutation_file: str,
    command: str | None,
    allow_fallback: bool,
) -> RosettaRunResult:
    if command:
        completed = subprocess.run(
            shlex.split(command),
            input=mutation_file,
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode == 0 and completed.stdout.strip():
            parsed = json.loads(completed.stdout)
            ddg = float(parsed["ddg_kcal_per_mol"])
            return RosettaRunResult(
                payload={
                    "mutation_string": mutation_string,
                    "mutation_file": mutation_file,
                    "parsed_mutations": [mutation.model_dump() for mutation in mutations],
                    "ddg_kcal_per_mol": ddg,
                    "interpretation": parsed.get("interpretation") or ("stabilizing" if ddg < 0 else "destabilizing_or_neutral"),
                    "runner": build_real_provenance(
                        provider="rosetta",
                        extra={"exit_code": completed.returncode},
                    ),
                }
            )
        if not allow_fallback:
            raise RuntimeError(f"Rosetta ddG runner failed with exit code {completed.returncode}: {completed.stderr}")

    if not allow_fallback:
        raise RuntimeError("Rosetta ddG runner is not configured and science fallbacks are disabled")

    ddg = _fallback_ddg_for_mutation(mutation_string)
    return RosettaRunResult(
        payload={
            "mutation_string": mutation_string,
            "mutation_file": mutation_file,
            "parsed_mutations": [mutation.model_dump() for mutation in mutations],
            "ddg_kcal_per_mol": ddg,
            "interpretation": "stabilizing" if ddg < 0 else "destabilizing_or_neutral",
            "runner": build_fallback_provenance(
                provider="rosetta",
                warning="Rosetta runner not configured; placeholder ddG used.",
            ),
        }
    )


def _fallback_ddg_for_mutation(mutation_string: str) -> float:
    total = sum(ord(char) for char in mutation_string)
    return round(((total % 21) - 10) / 5, 2)
```

Modify `finish_rosetta_ddg_job` in `apps/worker/worker/jobs.py` to call this runner and merge `structure_id` into the returned payload.

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker compose exec api pytest apps/api/tests/test_rosetta_runner.py apps/api/tests/test_mutation_parser.py -q`

Run: `docker compose exec worker pytest apps/worker/tests/test_worker_jobs.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/services/rosetta_runner.py apps/api/tests/test_rosetta_runner.py apps/worker/worker/jobs.py apps/worker/tests/test_worker_jobs.py
git commit -m "feat(worker): add rosetta runner boundary"
```

---

### Task 6: Artifact Provenance API And Frontend Display

**Files:**
- Modify: `apps/api/app/api/routes/enzyme_records.py`
- Modify: `apps/web/lib/types.ts`
- Modify: `apps/web/app/enzymes/[id]/analysis/analysis-utils.ts`
- Modify: `apps/web/app/enzymes/[id]/analysis/AnalysisClient.tsx`
- Test: `apps/api/tests/test_enzyme_records.py`
- Test: `apps/web/tests/analysis-utils.test.mjs`

- [ ] **Step 1: Write failing artifact provenance tests**

Append to `apps/web/tests/analysis-utils.test.mjs`:

```javascript
import { getArtifactRunnerLabel } from "../app/enzymes/[id]/analysis/analysis-utils.ts";

test("formats fallback artifact runner labels", () => {
  const label = getArtifactRunnerLabel({
    content_json: {
      runner: {
        provider: "mafft",
        mode: "fallback",
        warning: "MAFFT executable not configured; mock alignment used."
      }
    }
  });

  assert.equal(label.text, "mafft fallback");
  assert.equal(label.warning, "MAFFT executable not configured; mock alignment used.");
});
```

Add or update an API artifact content test in `apps/api/tests/test_enzyme_records.py` to create an MSA job with:

```python
result_summary_json={
    "artifact_type": "msa",
    "msa_fasta": ">query\nACD\n",
    "runner": {"provider": "mafft", "mode": "fallback", "warning": "mock alignment used"},
}
```

Assert `GET /enzymes/{enzyme_id}/analysis-artifacts/{artifact_id}/content` returns the `runner` object either in `content_json` or a typed response field.

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker compose exec api pytest apps/api/tests/test_enzyme_records.py -q`

Run: `pnpm --filter @iee-copilot/web test`

Expected: FAIL because runner display extraction is missing or artifact content omits runner metadata.

- [ ] **Step 3: Implement API and frontend display**

In `_artifact_content_from_summary` in `apps/api/app/api/routes/enzyme_records.py`, when building `content_json` for `msa`, `conservation_profile`, `homolog_sequences`, `mutation_recommendations`, `rosetta_ddg`, and `mutation_library`, include:

```python
runner = summary.get("runner")
provenance = summary.get("provenance")
if runner and isinstance(runner, dict):
    content_json["runner"] = runner
if provenance and isinstance(provenance, dict):
    content_json["provenance"] = provenance
```

In `apps/web/app/enzymes/[id]/analysis/analysis-utils.ts`, export:

```typescript
export function getArtifactRunnerLabel(content: { content_json?: Record<string, unknown> | null }) {
  const json = content.content_json;
  const runner = json && typeof json.runner === "object" && json.runner !== null ? json.runner as Record<string, unknown> : null;
  if (!runner) {
    return { text: "source unknown", warning: null as string | null, mode: "unavailable" };
  }
  const provider = typeof runner.provider === "string" ? runner.provider : "runner";
  const mode = typeof runner.mode === "string" ? runner.mode : "unavailable";
  const warning = typeof runner.warning === "string" ? runner.warning : null;
  return { text: `${provider} ${mode}`, warning, mode };
}
```

In `AnalysisClient.tsx`, render the label near selected artifact content and in the Rosetta/MSA summary sections. Use existing typography classes and no page redesign.

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker compose exec api pytest apps/api/tests/test_enzyme_records.py -q`

Run: `pnpm --filter @iee-copilot/web test`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/api/routes/enzyme_records.py apps/api/tests/test_enzyme_records.py apps/web/lib/types.ts apps/web/app/enzymes/[id]/analysis/analysis-utils.ts apps/web/app/enzymes/[id]/analysis/AnalysisClient.tsx apps/web/tests/analysis-utils.test.mjs
git commit -m "feat(web): show science runner provenance"
```

---

### Task 7: Documentation And Full Verification

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update README environment section**

Add:

```markdown
### Science Provider And Runner Configuration

The platform can run in demo mode or real-provider mode.

- `USE_REAL_SCIENCE_PROVIDERS=true` enables real UniProt, RCSB, AlphaFold, and literature adapters.
- `ALLOW_SCIENCE_FALLBACKS=false` makes missing tools fail jobs instead of silently using fallback outputs.
- `MAFFT_BIN="mafft --auto -"` configures the MAFFT runner.
- `ROSETTA_DDG_COMMAND="python /path/to/rosetta_ddg_wrapper.py"` configures the Rosetta ddG runner boundary.

When fallbacks are enabled, artifacts are still marked with `mode=fallback`; fallback outputs should not be treated as real scientific results.
```

- [ ] **Step 2: Run backend tests**

Run: `docker compose exec api pytest apps/api/tests -q`

Expected: PASS.

- [ ] **Step 3: Run worker tests**

Run: `docker compose exec worker pytest apps/worker/tests -q`

Expected: PASS.

- [ ] **Step 4: Run web tests**

Run: `pnpm --filter @iee-copilot/web test`

Expected: PASS.

- [ ] **Step 5: Run git status**

Run: `git status --short --branch`

Expected: branch `main` with only intended README changes before commit.

- [ ] **Step 6: Commit**

```bash
git add README.md
git commit -m "docs: document science runner configuration"
```

---

## Self-Review Notes

- Spec coverage: Tasks cover provenance helpers, real UniProt/RCSB/AlphaFold/literature parsing and selection, MAFFT runner, Rosetta runner, API artifact provenance, frontend display, and README environment variables.
- Scope guard: MD, MMPBSA, and active learning are not included in any implementation task.
- Test strategy: Every production change has a failing-test step before implementation and uses local fixtures or fake executables.
- Type consistency: The plan consistently uses `runner` for executable/tool provenance and `provenance` for external retrieval metadata. Both use `provider`, `mode`, timestamp, and optional `warning`.
