# IEE-Copilot

IEE-Copilot is a production-oriented skeleton for an industrial enzyme engineering
platform. The current vertical slice covers enzyme search, local freshness-aware
caching boundaries, placeholder analysis jobs, and a workbench-style web UI.

The MVP focuses on two enzyme modules:

- Anthraquinone glycosyltransferases
- Mature microbial transglutaminases

## Local Development

Copy the sample environment file:

```powershell
Copy-Item .env.example .env
```

Start the full local stack:

```powershell
docker compose up --build
```

Open:

- Web: http://localhost:3000
- API health: http://localhost:8000/health
- MinIO console: http://localhost:9001

The default local services are PostgreSQL, Redis, MinIO, FastAPI, Celery, and
Next.js.

## Repository Layout

- `apps/web`: Next.js workbench frontend.
- `apps/api`: FastAPI backend, routes, schemas, services, database models, and Alembic migrations.
- `apps/worker`: Celery worker tasks for asynchronous analyses.
- `packages/shared`: Shared static metadata and future cross-language schemas.
- `docker`: Docker and deployment notes. Service Dockerfiles currently live beside each app.
- `docs`: Product notes, design specs, and implementation plans.
- `scripts`: Utility scripts for seed data, imports, migrations, and analysis helpers.
- `tests`: Cross-service and integration acceptance notes.

## First Vertical Slice

The implemented skeleton supports:

1. Register or log in through the API.
2. Create and list owned projects.
3. Search an enzyme by name, EC number, UniProt ID, PDB ID, or organism.
4. Resolve the enzyme query against local cache and external client boundaries.
5. Persist an enzyme summary and enqueue a placeholder analysis job.
6. Inspect analysis job status and generated artifact records.

Future stages will fill in MD, MMPBSA, and active-learning recommendations.

## Science Provider And Runner Configuration

The platform can run in demo mode or real-provider mode. Development defaults
keep fallbacks enabled so the workflow remains usable without local scientific
tool installs.

- `USE_REAL_SCIENCE_PROVIDERS=true` enables real UniProt, RCSB, AlphaFold, Crossref literature, and Europe PMC enzyme-data adapters.
- `ALLOW_SCIENCE_FALLBACKS=false` makes missing tools fail jobs instead of silently using fallback outputs.
- `HOMOLOG_PROVIDER_FETCH_SIZE=25` limits the upstream UniProt candidate pool before local identity and coverage filtering.
- `SEQUENCE_SIMILARITY_FASTA_PATH="/path/to/homologs.fasta"` configures the `sequence_similarity` homolog runner to scan a local FASTA sequence database.
- `SEQUENCE_SIMILARITY_COMMAND="python scripts/similarity/sequence_similarity_wrapper.py --backend local --database /path/to/homologs.fasta"` configures an external sequence-similarity wrapper. The command receives the query FASTA on stdin and should write tabular hits as `accession<TAB>identity<TAB>coverage`; identity and coverage may be fractions or percentages. Accessions are resolved against `SEQUENCE_SIMILARITY_FASTA_PATH`.
- `MAFFT_BIN="mafft --auto -"` configures the MAFFT runner.
- `ROSETTA_DDG_COMMAND="python /path/to/rosetta_ddg_wrapper.py"` configures the Rosetta ddG runner boundary.
- `ROSETTA_DDG_BIN="/path/to/rosetta_ddg"` can be used when a direct executable is enough.

When fallbacks are enabled, artifacts are still marked with `mode=fallback`.
Fallback outputs should not be treated as real scientific results.

Enzyme property, kinetic, and mutant records are collected from Europe PMC
literature metadata in real-provider mode. The adapter extracts conservative
mentions of optimum temperature, optimum pH, Km, kcat, kcat/Km, and mutation
strings from article titles and abstracts. If Europe PMC is unavailable or no
extractable values are found, the real adapter returns no records rather than
inventing demo values.

For mature microbial transglutaminases, engineering calculations use the
UniProt mature chain when a `Chain` feature is available. The bundled seed
entry uses P81453 full length as the stored sequence and its mature chain as
the engineering target.

Homolog collection currently supports two user-facing modes:

- `metadata_search`: the current working mode. It searches UniProt by enzyme
  name first, then EC number, fetches up to `HOMOLOG_PROVIDER_FETCH_SIZE`
  upstream candidates, and filters them locally by identity, coverage, and the
  requested maximum homolog count.
- `sequence_similarity`: uses `SEQUENCE_SIMILARITY_COMMAND` plus
  `SEQUENCE_SIMILARITY_FASTA_PATH` when both are configured. This is the
  intended boundary for BLAST/MMseqs2 wrappers. If only the FASTA path is
  configured, it scans FASTA records by local sequence identity and coverage.
  Both paths then apply the same identity, coverage, deduplication, and maximum
  homolog filters as the metadata path. If no similarity source is configured,
  results are explicitly marked as fallback rather than real BLAST or MMseqs2
  output.

The bundled similarity wrapper supports three backends:

- `--backend local`: development smoke check using ungapped identity/coverage
  against a FASTA file.
- `--backend mmseqs`: requires `mmseqs` on `PATH`; `--database` should point to
  a target FASTA file. The wrapper creates temporary MMseqs databases per run.
- `--backend blastp`: requires `blastp` on `PATH`; `--database` should be a
  prepared BLAST database prefix.

## Development Checks

Run Python tests:

```powershell
pytest apps/api/tests apps/worker/tests -v
```

Run the web type/build check:

```powershell
corepack pnpm --filter @iee-copilot/web build
```

Validate Docker Compose configuration:

```powershell
docker compose config
```

When Docker Desktop is running, build all service images:

```powershell
docker compose build
```
