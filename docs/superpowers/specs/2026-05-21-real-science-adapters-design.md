# Real Science Adapter Design

## Goal

Replace the current mock-heavy scientific data and computation paths with production-shaped adapters that can use real providers when available, while keeping explicit fallback behavior for local development and demos.

This design covers:

- UniProt, RCSB PDB, AlphaFold DB, and literature metadata retrieval.
- MSA execution through MAFFT when available.
- Rosetta ddG execution through a configured Rosetta binary or script when available.
- Provenance metadata for every retrieved or computed artifact.

This design does not cover:

- MD simulation.
- MMPBSA.
- Active learning or next-round model training.

## Current State

The platform already has stable routes, jobs, models, and frontend pages for search, structures, homologs, MSA, conservation, mutation recommendations, Rosetta ddG, and mutation library design.

Several scientific steps are still mock or placeholder implementations:

- External data clients often return deterministic mock data.
- MSA uses `run_mock_mafft`.
- Rosetta ddG generates mutation input and mock ddG values.
- Artifact summaries do not consistently expose whether a result came from a real provider or a fallback.

The next step is to keep the existing user flow but make each scientific provider swappable, auditable, and honest about its execution mode.

## Design Principles

1. Prefer real providers when configured and reachable.
2. Keep fallback behavior available so local development remains usable.
3. Never hide fallback results as real scientific results.
4. Store enough provenance to support debugging, reruns, and manuscript methods sections.
5. Avoid broad UI redesign in this pass; add only the labels needed to show data source and runner status.

## Provider Modes

Each external provider or runner should report one of these modes:

- `real`: a real API, executable, or scientific tool produced the result.
- `fallback`: a deterministic local fallback produced the result because the real provider was unavailable or disabled.
- `unavailable`: no result could be produced.

Provider output should include:

- `provider`: short name such as `uniprot`, `rcsb`, `alphafold`, `crossref`, `pubmed`, `mafft`, or `rosetta`.
- `mode`: `real`, `fallback`, or `unavailable`.
- `retrieved_at` or `ran_at`: UTC timestamp.
- `source_url` when applicable.
- `version` when the executable or API version is known.
- `warning` when fallback or partial data was used.

## External Data Retrieval

### UniProt

Add a real UniProt HTTP client that can:

- Search by accession, EC number, keyword, and organism text.
- Fetch canonical sequence FASTA.
- Extract organism, protein name, EC number, cross-references, and AlphaFold IDs.

The existing mock client remains as fallback. Tests should cover real response parsing using local fixture payloads, not live network calls.

### RCSB PDB

Add a real RCSB client that can:

- Fetch structure metadata by PDB ID.
- Search structure IDs by UniProt accession.
- Download PDB text when available.

The fallback client remains for demo entries. Tests should use fixture JSON/PDB text.

### AlphaFold DB

Add a real AlphaFold DB client that can:

- Fetch prediction metadata by UniProt accession.
- Capture model URL, confidence URL, pLDDT or confidence metadata when exposed.
- Optionally download predicted PDB/CIF content in a later pass.

The first implementation may stop at metadata plus provenance if structure download is not required by current UI.

### Literature Metadata

Add a literature adapter boundary rather than one hard-coded provider. Initial implementation should support a real DOI metadata path using Crossref-style fixture parsing, with room for PubMed/Semantic Scholar later.

The platform should store title, authors, journal, year, DOI or PubMed ID, abstract when available, and provider provenance.

## MSA Runner

Introduce an MSA runner service with this behavior:

1. If `IEE_MAFFT_BIN` is configured or `mafft` is discoverable on `PATH`, run MAFFT on the query and homolog sequences.
2. Capture stdout as aligned FASTA.
3. Capture stderr, exit code, runner version when available, and runtime metadata.
4. If MAFFT is unavailable and fallback is allowed, use the existing mock alignment and mark the artifact as fallback.
5. If fallback is disabled, fail the job with a clear error.

Configuration:

- `IEE_MAFFT_BIN`: optional executable path.
- `IEE_ALLOW_SCIENCE_FALLBACKS`: default `true` for development, can be set to `false` for production-like runs.

## Rosetta ddG Runner

Introduce a Rosetta runner service with this behavior:

1. Always validate mutation strings against the engineering sequence.
2. Always generate the Rosetta mutation file payload.
3. If `IEE_ROSETTA_DDG_BIN` or `IEE_ROSETTA_DDG_COMMAND` is configured, execute the real runner.
4. Parse a minimal stable output contract: mutation string, ddG value, unit, interpretation, command metadata, and logs.
5. If no real runner is configured and fallback is allowed, produce the existing placeholder ddG with `mode=fallback`.
6. If fallback is disabled, fail the job with a clear setup error.

Configuration:

- `IEE_ROSETTA_DDG_BIN`: optional executable path for a direct Rosetta ddG binary.
- `IEE_ROSETTA_DDG_COMMAND`: optional command template for site-specific wrappers.
- `IEE_ALLOW_SCIENCE_FALLBACKS`: controls placeholder use.

The first implementation should not attempt to solve full Rosetta installation, structure preparation, relaxation, or containerized HPC scheduling. It should define the execution boundary cleanly so those can be added later.

## Artifact Provenance

Analysis artifacts should include provenance in `result_summary_json` and artifact content responses.

For MSA:

```json
{
  "artifact_type": "msa",
  "runner": {
    "provider": "mafft",
    "mode": "real",
    "version": "v7.x",
    "ran_at": "2026-05-21T00:00:00Z"
  }
}
```

For Rosetta:

```json
{
  "artifact_type": "rosetta_ddg",
  "runner": {
    "provider": "rosetta",
    "mode": "fallback",
    "warning": "Rosetta runner not configured; placeholder ddG used."
  }
}
```

For external retrieval:

```json
{
  "source": "uniprot",
  "provenance": {
    "provider": "uniprot",
    "mode": "real",
    "source_url": "https://rest.uniprot.org/...",
    "retrieved_at": "2026-05-21T00:00:00Z"
  }
}
```

## Frontend Changes

Keep frontend scope small:

- Show runner/source labels on analysis artifacts.
- Show fallback warnings where relevant.
- Do not redesign the analysis page.
- Do not add MD/MMPBSA or active learning UI in this pass.

The important UX behavior is honesty: users should immediately see whether a result is real, fallback, or unavailable.

## Testing Strategy

Use test-first implementation.

Backend tests:

- Parse UniProt fixture search and FASTA responses.
- Parse RCSB fixture metadata and PDB download responses.
- Parse AlphaFold fixture metadata.
- Parse literature metadata fixture.
- MAFFT runner uses a fake executable script to verify real-runner behavior.
- MAFFT fallback is explicitly marked as fallback.
- Rosetta runner uses a fake executable/script to verify real-runner parsing.
- Rosetta fallback is explicitly marked as fallback.
- Fallback disabled causes clear job failure.

Frontend tests:

- Analysis utility functions extract and display runner mode.
- Fallback warnings are rendered from artifact content.

No test should depend on live internet access.

## Rollout Plan

1. Add provider result/provenance helpers.
2. Add fixture-based real client parsers for UniProt, RCSB, AlphaFold, and literature.
3. Wire real clients behind existing `get_*_client` boundaries.
4. Add MAFFT runner abstraction and update worker MSA job.
5. Add Rosetta runner abstraction and update worker Rosetta job.
6. Add small frontend provenance labels.
7. Update README or docs with required environment variables.

## Acceptance Criteria

- Existing search and analysis flows continue to work in development.
- Real provider clients can be tested with fixture payloads.
- MSA artifacts identify `mafft` real mode or fallback mode.
- Rosetta artifacts identify real mode or fallback mode.
- When fallbacks are disabled, missing real tools produce explicit failures rather than silent mock results.
- UI exposes whether an artifact came from a real runner or fallback.
- MD/MMPBSA and active learning remain out of scope for this pass.
