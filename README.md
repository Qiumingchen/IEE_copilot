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

## First Vertical Slice

The implemented skeleton supports:

1. Register or log in through the API.
2. Create and list owned projects.
3. Search an enzyme by name, EC number, UniProt ID, PDB ID, or organism.
4. Resolve the enzyme query against local cache and external client boundaries.
5. Persist an enzyme summary and enqueue a placeholder analysis job.
6. Inspect analysis job status and generated artifact records.

Future stages will fill in MSA, conservation analysis, Rosetta ddG, MD, MMPBSA,
wet-lab feedback ingestion, and active-learning recommendations.

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
