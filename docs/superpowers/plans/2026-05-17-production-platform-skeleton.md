# IEE-Copilot Production Platform Skeleton Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a production-oriented IEE-Copilot monorepo that runs locally with Docker Compose and proves the first vertical slice: enzyme search, cache check, external retrieval boundary, database persistence, queued analysis job, and web display.

**Architecture:** The platform is a monorepo with `apps/web` for Next.js, `apps/api` for FastAPI, `apps/worker` for Celery, PostgreSQL for domain data, Redis for jobs, and MinIO for artifacts. The first implementation creates real service boundaries and a minimal business flow while keeping MSA, Rosetta, MD, MMPBSA, and active learning as typed extension points.

**Tech Stack:** Next.js, React, TypeScript, Tailwind CSS, FastAPI, SQLAlchemy, Alembic, PostgreSQL, Redis, Celery, MinIO, pnpm, uv, Docker Compose, pytest.

---

## File Structure Map

Create this structure:

```text
AGENTS.md
PRD.md
原始方案.md
.gitignore
.env.example
docker-compose.yml
package.json
pnpm-workspace.yaml
pyproject.toml

apps/
  api/
    app/
      __init__.py
      main.py
      api/
        __init__.py
        routes/
          __init__.py
          auth.py
          enzymes.py
          health.py
          jobs.py
          projects.py
      core/
        __init__.py
        config.py
        security.py
      db/
        __init__.py
        base.py
        models.py
        session.py
      schemas/
        __init__.py
        auth.py
        enzyme.py
        job.py
        project.py
      services/
        __init__.py
        cache.py
        query_resolver.py
      external/
        __init__.py
        alphafold.py
        literature.py
        rcsb.py
        uniprot.py
      tasks/
        __init__.py
        celery_app.py
    alembic.ini
    alembic/
      env.py
      versions/
    tests/
      test_health.py
      test_query_resolver.py
      test_search_flow.py
    Dockerfile

  worker/
    worker/
      __init__.py
      main.py
      jobs.py
    tests/
      test_worker_jobs.py
    Dockerfile

  web/
    app/
      layout.tsx
      page.tsx
      login/page.tsx
      search/page.tsx
      enzymes/[id]/page.tsx
      jobs/[id]/page.tsx
    lib/
      api.ts
      types.ts
    package.json
    next.config.mjs
    tailwind.config.ts
    postcss.config.mjs
    tsconfig.json
    Dockerfile

packages/
  shared/
    enzyme-modules.json

scripts/
  seed/
    seed.py

tests/
  integration/
    test_compose_contract.md
```

Responsibilities:

- `apps/api/app/main.py`: FastAPI app factory and router registration.
- `apps/api/app/db/models.py`: SQLAlchemy models for the first scientific core schema.
- `apps/api/app/services/query_resolver.py`: Query type and enzyme module detection.
- `apps/api/app/services/cache.py`: 15-day freshness and local hit logic.
- `apps/api/app/external/*.py`: HTTP client boundaries for UniProt, RCSB, AlphaFold, and literature metadata.
- `apps/api/app/tasks/celery_app.py`: Shared Celery app configuration for API and worker.
- `apps/worker/worker/jobs.py`: Celery task implementations that update `analysis_job` and create artifact records.
- `apps/web/app/*`: Workbench-first frontend pages for login, search, enzyme detail, and job status.
- `scripts/seed/seed.py`: Demo user, enzyme families, and demo project.

---

### Task 1: Repository And Workspace Foundation

**Files:**
- Create: `.gitignore`
- Create: `.env.example`
- Create: `package.json`
- Create: `pnpm-workspace.yaml`
- Create: `pyproject.toml`
- Create: `packages/shared/enzyme-modules.json`
- Create: `tests/integration/test_compose_contract.md`

- [ ] **Step 1: Initialize git if missing**

Run:

```powershell
git rev-parse --is-inside-work-tree
```

Expected if the repo is already initialized:

```text
true
```

Expected in the current workspace before implementation:

```text
fatal: not a git repository
```

If the command returns the fatal message, run:

```powershell
git init
```

Expected:

```text
Initialized empty Git repository
```

- [ ] **Step 2: Create root workspace files**

Write `.gitignore`:

```gitignore
.env
.env.local
.env.production
.venv/
node_modules/
.next/
dist/
build/
__pycache__/
.pytest_cache/
.mypy_cache/
.ruff_cache/
.coverage
htmlcov/
.superpowers/
data/
*.pyc
*.pyo
*.log
```

Write `.env.example`:

```dotenv
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=iee_copilot
POSTGRES_USER=iee
POSTGRES_PASSWORD=iee_dev_password
DATABASE_URL=postgresql+psycopg://iee:iee_dev_password@postgres:5432/iee_copilot

REDIS_URL=redis://redis:6379/0

MINIO_ENDPOINT=minio:9000
MINIO_ACCESS_KEY=iee_minio
MINIO_SECRET_KEY=iee_minio_password
MINIO_BUCKET=iee-artifacts
MINIO_SECURE=false

API_HOST=0.0.0.0
API_PORT=8000
API_SECRET_KEY=change-me-in-local-env
ACCESS_TOKEN_EXPIRE_MINUTES=1440

NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

Write root `package.json`:

```json
{
  "name": "iee-copilot",
  "private": true,
  "packageManager": "pnpm@9.15.0",
  "scripts": {
    "web:dev": "pnpm --filter @iee-copilot/web dev",
    "web:build": "pnpm --filter @iee-copilot/web build",
    "web:lint": "pnpm --filter @iee-copilot/web lint"
  }
}
```

Write `pnpm-workspace.yaml`:

```yaml
packages:
  - "apps/web"
  - "packages/*"
```

Write `packages/shared/enzyme-modules.json`:

```json
{
  "ANTHRAQUINONE_GLYCOSYLTRANSFERASE": {
    "label": "Anthraquinone Glycosyltransferase",
    "defaultGoals": ["specific_activity", "product_selectivity", "thermostability"]
  },
  "MICROBIAL_TRANSGLUTAMINASE_MATURE": {
    "label": "Mature Microbial Transglutaminase",
    "defaultGoals": ["thermostability", "opt_temperature", "specific_activity"]
  }
}
```

Write `pyproject.toml`:

```toml
[project]
name = "iee-copilot"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
  "alembic>=1.13.2",
  "celery[redis]>=5.4.0",
  "fastapi>=0.115.0",
  "httpx>=0.27.0",
  "email-validator>=2.2.0",
  "minio>=7.2.8",
  "passlib[bcrypt]>=1.7.4",
  "psycopg[binary]>=3.2.1",
  "pydantic-settings>=2.4.0",
  "python-jose[cryptography]>=3.3.0",
  "python-multipart>=0.0.9",
  "sqlalchemy>=2.0.32",
  "uvicorn[standard]>=0.30.6"
]

[project.optional-dependencies]
dev = [
  "pytest>=8.3.2",
  "pytest-asyncio>=0.23.8",
  "ruff>=0.6.2"
]

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.pytest.ini_options]
testpaths = ["apps/api/tests", "apps/worker/tests"]
pythonpath = ["apps/api", "apps/worker"]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools]
py-modules = []
```

Write `tests/integration/test_compose_contract.md`:

```markdown
# Compose Contract

The local stack is accepted when:

1. `docker compose up --build` starts postgres, redis, minio, api, worker, and web.
2. `GET http://localhost:8000/health` returns `{"status":"ok"}`.
3. `GET http://localhost:8000/health/db` returns `{"database":"ok"}`.
4. `http://localhost:3000` renders the web dashboard or redirects to login.
5. Searching `microbial transglutaminase` returns an enzyme summary and a job id.
```

- [ ] **Step 3: Verify root files**

Run:

```powershell
Get-ChildItem -Force
```

Expected: output includes `.gitignore`, `.env.example`, `package.json`, `pnpm-workspace.yaml`, and `pyproject.toml`.

- [ ] **Step 4: Commit**

Run:

```powershell
git add .gitignore .env.example package.json pnpm-workspace.yaml pyproject.toml packages/shared/enzyme-modules.json tests/integration/test_compose_contract.md
git commit -m "chore: initialize monorepo workspace"
```

Expected: commit succeeds.

---

### Task 2: FastAPI Configuration, Health Checks, And Database Session

**Files:**
- Create: `apps/api/app/__init__.py`
- Create: `apps/api/app/main.py`
- Create: `apps/api/app/core/__init__.py`
- Create: `apps/api/app/core/config.py`
- Create: `apps/api/app/db/__init__.py`
- Create: `apps/api/app/db/session.py`
- Create: `apps/api/app/api/__init__.py`
- Create: `apps/api/app/api/routes/__init__.py`
- Create: `apps/api/app/api/routes/health.py`
- Create: `apps/api/tests/test_health.py`

- [ ] **Step 1: Write failing health tests**

Create `apps/api/tests/test_health.py`:

```python
from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health_returns_ok():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "iee-copilot-api"}


def test_health_db_reports_configuration_without_connecting_when_disabled(monkeypatch):
    monkeypatch.setenv("SKIP_DB_HEALTHCHECK", "true")

    response = client.get("/health/db")

    assert response.status_code == 200
    assert response.json() == {"database": "skipped"}
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
pytest apps/api/tests/test_health.py -v
```

Expected: failure because `app.main` does not exist.

- [ ] **Step 3: Implement settings, database session, and health router**

Create `apps/api/app/core/config.py`:

```python
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite+pysqlite:///:memory:"
    redis_url: str = "redis://localhost:6379/0"
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "iee_minio"
    minio_secret_key: str = "iee_minio_password"
    minio_bucket: str = "iee-artifacts"
    minio_secure: bool = False
    api_secret_key: str = "dev-secret"
    access_token_expire_minutes: int = 1440
    skip_db_healthcheck: bool = False

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

Create `apps/api/app/db/session.py`:

```python
from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


def build_engine():
    settings = get_settings()
    connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
    return create_engine(settings.database_url, pool_pre_ping=True, connect_args=connect_args)


engine = build_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ping_database() -> bool:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    return True
```

Create `apps/api/app/api/routes/health.py`:

```python
from fastapi import APIRouter, HTTPException

from app.core.config import get_settings
from app.db.session import ping_database

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "iee-copilot-api"}


@router.get("/health/db")
def health_db() -> dict[str, str]:
    settings = get_settings()
    if settings.skip_db_healthcheck:
        return {"database": "skipped"}
    try:
        ping_database()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="database unavailable") from exc
    return {"database": "ok"}
```

Create `apps/api/app/main.py`:

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.health import router as health_router

app = FastAPI(title="IEE-Copilot API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
```

Create empty package markers:

```python
# apps/api/app/__init__.py
```

```python
# apps/api/app/core/__init__.py
```

```python
# apps/api/app/db/__init__.py
```

```python
# apps/api/app/api/__init__.py
```

```python
# apps/api/app/api/routes/__init__.py
```

- [ ] **Step 4: Run tests and verify they pass**

Run:

```powershell
pytest apps/api/tests/test_health.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

Run:

```powershell
git add apps/api
git commit -m "feat(api): add health checks and database session"
```

Expected: commit succeeds.

---

### Task 3: Core Database Models And Alembic

**Files:**
- Create: `apps/api/app/db/base.py`
- Create: `apps/api/app/db/models.py`
- Create: `apps/api/alembic.ini`
- Create: `apps/api/alembic/env.py`
- Create: `apps/api/alembic/versions/20260517_0001_core_schema.py`
- Create: `apps/api/tests/test_models.py`

- [ ] **Step 1: Write model tests**

Create `apps/api/tests/test_models.py`:

```python
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.models import EnzymeFamily, EnzymeModule, User, UserRole


def test_core_models_can_create_user_and_family():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        user = User(email="demo@example.com", password_hash="hash", role=UserRole.USER)
        family = EnzymeFamily(
            module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
            name="Mature microbial transglutaminase",
            description="Mature enzyme engineering target",
        )
        session.add_all([user, family])
        session.commit()

        saved_user = session.scalar(select(User).where(User.email == "demo@example.com"))
        saved_family = session.scalar(select(EnzymeFamily).where(EnzymeFamily.name == family.name))

    assert saved_user is not None
    assert saved_user.role == UserRole.USER
    assert saved_family is not None
    assert saved_family.module == EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE
```

- [ ] **Step 2: Run test and verify it fails**

Run:

```powershell
pytest apps/api/tests/test_models.py -v
```

Expected: failure because `app.db.base` or `app.db.models` does not exist.

- [ ] **Step 3: Implement models**

Create `apps/api/app/db/base.py`:

```python
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
```

Create `apps/api/app/db/models.py` with these enums and tables:

```python
import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def uuid_str() -> str:
    return str(uuid.uuid4())


class UserRole(str, enum.Enum):
    USER = "user"
    CURATOR = "curator"
    ADMIN = "admin"


class ProjectMemberRole(str, enum.Enum):
    OWNER = "owner"
    MEMBER = "member"


class EnzymeModule(str, enum.Enum):
    ANTHRAQUINONE_GLYCOSYLTRANSFERASE = "ANTHRAQUINONE_GLYCOSYLTRANSFERASE"
    MICROBIAL_TRANSGLUTAMINASE_MATURE = "MICROBIAL_TRANSGLUTAMINASE_MATURE"


class Visibility(str, enum.Enum):
    PRIVATE = "private"
    PUBLIC = "public"


class CurationStatus(str, enum.Enum):
    UNREVIEWED = "unreviewed"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class JobStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    FINISHED = "finished"
    FAILED = "failed"
    CANCELLED = "cancelled"


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str | None] = mapped_column(String(120))
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.USER)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    target_enzyme_module: Mapped[EnzymeModule | None] = mapped_column(Enum(EnzymeModule))
    default_visibility: Mapped[Visibility] = mapped_column(Enum(Visibility), default=Visibility.PRIVATE)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ProjectMember(Base):
    __tablename__ = "project_members"
    __table_args__ = (UniqueConstraint("project_id", "user_id", name="uq_project_member"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    role: Mapped[ProjectMemberRole] = mapped_column(Enum(ProjectMemberRole))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class EnzymeFamily(Base):
    __tablename__ = "enzyme_family"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    module: Mapped[EnzymeModule] = mapped_column(Enum(EnzymeModule), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    last_refreshed_at: Mapped[datetime | None] = mapped_column(DateTime)


class EnzymeEntry(Base):
    __tablename__ = "enzyme_entry"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    family_id: Mapped[str] = mapped_column(ForeignKey("enzyme_family.id"))
    name: Mapped[str] = mapped_column(String(240))
    organism: Mapped[str | None] = mapped_column(String(240))
    ec_number: Mapped[str | None] = mapped_column(String(40))
    uniprot_id: Mapped[str | None] = mapped_column(String(40), index=True)
    pdb_id: Mapped[str | None] = mapped_column(String(12), index=True)
    alphafold_id: Mapped[str | None] = mapped_column(String(80))
    source: Mapped[str] = mapped_column(String(80), default="local")
    last_refreshed_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    family: Mapped[EnzymeFamily] = relationship()


class ProteinSequence(Base):
    __tablename__ = "protein_sequence"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    enzyme_entry_id: Mapped[str] = mapped_column(ForeignKey("enzyme_entry.id"))
    sequence: Mapped[str] = mapped_column(Text)
    mature_sequence: Mapped[str | None] = mapped_column(Text)
    is_engineering_target: Mapped[bool] = mapped_column(default=True)
    source: Mapped[str] = mapped_column(String(80))
    checksum: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AnalysisJob(Base):
    __tablename__ = "analysis_job"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"))
    enzyme_entry_id: Mapped[str | None] = mapped_column(ForeignKey("enzyme_entry.id"))
    job_type: Mapped[str] = mapped_column(String(80))
    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus), default=JobStatus.QUEUED)
    parameters_json: Mapped[dict | None] = mapped_column(JSON)
    result_summary_json: Mapped[dict | None] = mapped_column(JSON)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)


class AnalysisArtifact(Base):
    __tablename__ = "analysis_artifact"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"))
    enzyme_entry_id: Mapped[str | None] = mapped_column(ForeignKey("enzyme_entry.id"))
    job_id: Mapped[str | None] = mapped_column(ForeignKey("analysis_job.id"))
    artifact_type: Mapped[str] = mapped_column(String(80))
    bucket: Mapped[str] = mapped_column(String(120))
    object_key: Mapped[str] = mapped_column(String(500))
    checksum: Mapped[str | None] = mapped_column(String(64))
    content_type: Mapped[str | None] = mapped_column(String(120))
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(80), default="worker")
    visibility: Mapped[Visibility] = mapped_column(Enum(Visibility), default=Visibility.PRIVATE)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
```

Append the remaining scientific tables in the same file:

```python
class StructureEntry(Base):
    __tablename__ = "structure_entry"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    enzyme_entry_id: Mapped[str] = mapped_column(ForeignKey("enzyme_entry.id"))
    structure_type: Mapped[str] = mapped_column(String(40))
    complex_state: Mapped[str] = mapped_column(String(40), default="unknown")
    pdb_id: Mapped[str | None] = mapped_column(String(12))
    chain_summary: Mapped[dict | None] = mapped_column(JSON)
    ligand_summary: Mapped[dict | None] = mapped_column(JSON)
    artifact_id: Mapped[str | None] = mapped_column(ForeignKey("analysis_artifact.id"))
    source: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class LiteratureReference(Base):
    __tablename__ = "literature_reference"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    title: Mapped[str] = mapped_column(Text)
    authors: Mapped[str | None] = mapped_column(Text)
    journal: Mapped[str | None] = mapped_column(String(240))
    year: Mapped[int | None] = mapped_column(Integer)
    doi: Mapped[str | None] = mapped_column(String(200))
    pubmed_id: Mapped[str | None] = mapped_column(String(80))
    source: Mapped[str] = mapped_column(String(80), default="manual")
    metadata_json: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class PropertyRecord(Base):
    __tablename__ = "property_record"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    enzyme_entry_id: Mapped[str] = mapped_column(ForeignKey("enzyme_entry.id"))
    property_type: Mapped[str] = mapped_column(String(80))
    value_original: Mapped[str] = mapped_column(String(120))
    unit_original: Mapped[str | None] = mapped_column(String(80))
    value_standardized: Mapped[str | None] = mapped_column(String(120))
    unit_standardized: Mapped[str | None] = mapped_column(String(80))
    standardization_status: Mapped[str] = mapped_column(String(40), default="not_attempted")
    substrate: Mapped[str | None] = mapped_column(String(240))
    assay_temperature: Mapped[str | None] = mapped_column(String(80))
    assay_pH: Mapped[str | None] = mapped_column(String(80))
    buffer: Mapped[str | None] = mapped_column(String(240))
    method: Mapped[str | None] = mapped_column(Text)
    reference_id: Mapped[str | None] = mapped_column(ForeignKey("literature_reference.id"))
    evidence_text: Mapped[str | None] = mapped_column(Text)
    visibility: Mapped[Visibility] = mapped_column(Enum(Visibility), default=Visibility.PUBLIC)
    curation_status: Mapped[CurationStatus] = mapped_column(
        Enum(CurationStatus), default=CurationStatus.UNREVIEWED
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class KineticRecord(Base):
    __tablename__ = "kinetic_record"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    enzyme_entry_id: Mapped[str] = mapped_column(ForeignKey("enzyme_entry.id"))
    substrate: Mapped[str | None] = mapped_column(String(240))
    km: Mapped[str | None] = mapped_column(String(120))
    kcat: Mapped[str | None] = mapped_column(String(120))
    kcat_km: Mapped[str | None] = mapped_column(String(120))
    unit_original: Mapped[str | None] = mapped_column(String(120))
    assay_temperature: Mapped[str | None] = mapped_column(String(80))
    assay_pH: Mapped[str | None] = mapped_column(String(80))
    method: Mapped[str | None] = mapped_column(Text)
    reference_id: Mapped[str | None] = mapped_column(ForeignKey("literature_reference.id"))
    visibility: Mapped[Visibility] = mapped_column(Enum(Visibility), default=Visibility.PUBLIC)
    curation_status: Mapped[CurationStatus] = mapped_column(
        Enum(CurationStatus), default=CurationStatus.UNREVIEWED
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class MutationRecord(Base):
    __tablename__ = "mutation_record"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    enzyme_entry_id: Mapped[str] = mapped_column(ForeignKey("enzyme_entry.id"))
    parent_enzyme_entry_id: Mapped[str | None] = mapped_column(ForeignKey("enzyme_entry.id"))
    mutation_string: Mapped[str] = mapped_column(String(240))
    mutation_positions: Mapped[dict | None] = mapped_column(JSON)
    effect_summary: Mapped[str | None] = mapped_column(Text)
    property_delta: Mapped[dict | None] = mapped_column(JSON)
    substrate: Mapped[str | None] = mapped_column(String(240))
    assay_condition_summary: Mapped[dict | None] = mapped_column(JSON)
    reference_id: Mapped[str | None] = mapped_column(ForeignKey("literature_reference.id"))
    is_user_uploaded: Mapped[bool] = mapped_column(default=False)
    visibility: Mapped[Visibility] = mapped_column(Enum(Visibility), default=Visibility.PUBLIC)
    curation_status: Mapped[CurationStatus] = mapped_column(
        Enum(CurationStatus), default=CurationStatus.UNREVIEWED
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
```

Append experiment and audit tables:

```python
class UserExperiment(Base):
    __tablename__ = "user_experiment"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))
    enzyme_entry_id: Mapped[str | None] = mapped_column(ForeignKey("enzyme_entry.id"))
    variant_name: Mapped[str] = mapped_column(String(200))
    mutation_string: Mapped[str | None] = mapped_column(String(240))
    sequence: Mapped[str | None] = mapped_column(Text)
    measured_property: Mapped[str] = mapped_column(String(120))
    measured_value: Mapped[str] = mapped_column(String(120))
    unit: Mapped[str | None] = mapped_column(String(80))
    assay_condition_json: Mapped[dict | None] = mapped_column(JSON)
    visibility: Mapped[Visibility] = mapped_column(Enum(Visibility), default=Visibility.PRIVATE)
    curation_status: Mapped[CurationStatus] = mapped_column(
        Enum(CurationStatus), default=CurationStatus.UNREVIEWED
    )
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class VisibilityRequest(Base):
    __tablename__ = "visibility_request"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))
    target_type: Mapped[str] = mapped_column(String(80))
    target_id: Mapped[str] = mapped_column(String(36))
    requested_visibility: Mapped[Visibility] = mapped_column(Enum(Visibility))
    status: Mapped[str] = mapped_column(String(40), default="pending")
    requested_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    reviewed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    review_comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime)


class CurationTask(Base):
    __tablename__ = "curation_task"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    visibility_request_id: Mapped[str] = mapped_column(ForeignKey("visibility_request.id"))
    status: Mapped[str] = mapped_column(String(40), default="open")
    assigned_to: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    summary: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    actor_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(120))
    target_type: Mapped[str] = mapped_column(String(80))
    target_id: Mapped[str | None] = mapped_column(String(36))
    metadata_json: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
```

- [ ] **Step 4: Add Alembic config**

Create `apps/api/alembic.ini`:

```ini
[alembic]
script_location = apps/api/alembic
prepend_sys_path = .
sqlalchemy.url = sqlite+pysqlite:///:memory:

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
```

Create `apps/api/alembic/env.py`:

```python
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import get_settings
from app.db.base import Base
from app.db import models  # noqa: F401

config = context.config
fileConfig(config.config_file_name)
target_metadata = Base.metadata


def get_url() -> str:
    return get_settings().database_url


def run_migrations_offline() -> None:
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section)
    configuration["sqlalchemy.url"] = get_url()
    connectable = engine_from_config(configuration, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

Create `apps/api/alembic/versions/20260517_0001_core_schema.py`:

```python
"""core schema

Revision ID: 20260517_0001
Revises:
Create Date: 2026-05-17
"""

from alembic import op
import sqlalchemy as sa

revision = "20260517_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    from app.db.base import Base
    from app.db import models  # noqa: F401

    bind = op.get_bind()
    Base.metadata.create_all(bind)


def downgrade() -> None:
    from app.db.base import Base
    from app.db import models  # noqa: F401

    bind = op.get_bind()
    Base.metadata.drop_all(bind)
```

- [ ] **Step 5: Run model tests**

Run:

```powershell
pytest apps/api/tests/test_models.py -v
```

Expected: 1 passed.

- [ ] **Step 6: Commit**

Run:

```powershell
git add apps/api/app/db apps/api/alembic.ini apps/api/alembic apps/api/tests/test_models.py
git commit -m "feat(api): add core scientific database schema"
```

Expected: commit succeeds.

---

### Task 4: Query Resolver, Cache Service, And External Client Boundaries

**Files:**
- Create: `apps/api/app/services/query_resolver.py`
- Create: `apps/api/app/services/cache.py`
- Create: `apps/api/app/external/uniprot.py`
- Create: `apps/api/app/external/rcsb.py`
- Create: `apps/api/app/external/alphafold.py`
- Create: `apps/api/app/external/literature.py`
- Create: `apps/api/tests/test_query_resolver.py`

- [ ] **Step 1: Write resolver tests**

Create `apps/api/tests/test_query_resolver.py`:

```python
from app.db.models import EnzymeModule
from app.services.query_resolver import QueryKind, resolve_query


def test_resolve_uniprot_accession():
    resolved = resolve_query("P81453")

    assert resolved.kind == QueryKind.UNIPROT
    assert resolved.normalized_query == "P81453"


def test_resolve_pdb_id():
    resolved = resolve_query("1IU4")

    assert resolved.kind == QueryKind.PDB
    assert resolved.normalized_query == "1IU4"


def test_resolve_ec_number():
    resolved = resolve_query("2.3.2.13")

    assert resolved.kind == QueryKind.EC
    assert resolved.normalized_query == "2.3.2.13"


def test_detect_mtgase_module_from_keyword():
    resolved = resolve_query("microbial transglutaminase")

    assert resolved.module_hint == EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE


def test_detect_anthraquinone_module_from_keyword():
    resolved = resolve_query("anthraquinone glycosyltransferase")

    assert resolved.module_hint == EnzymeModule.ANTHRAQUINONE_GLYCOSYLTRANSFERASE
```

- [ ] **Step 2: Run test and verify it fails**

Run:

```powershell
pytest apps/api/tests/test_query_resolver.py -v
```

Expected: failure because `app.services.query_resolver` does not exist.

- [ ] **Step 3: Implement resolver**

Create `apps/api/app/services/query_resolver.py`:

```python
import enum
import re
from dataclasses import dataclass

from app.db.models import EnzymeModule


class QueryKind(str, enum.Enum):
    UNIPROT = "uniprot"
    PDB = "pdb"
    EC = "ec"
    KEYWORD = "keyword"


@dataclass(frozen=True)
class ResolvedQuery:
    raw_query: str
    normalized_query: str
    kind: QueryKind
    module_hint: EnzymeModule | None


UNIPROT_RE = re.compile(r"^[OPQ][0-9][A-Z0-9]{3}[0-9]$|^[A-NR-Z][0-9][A-Z][A-Z0-9]{2}[0-9]$")
PDB_RE = re.compile(r"^[0-9][A-Za-z0-9]{3}$")
EC_RE = re.compile(r"^\d+\.\d+\.\d+\.\d+$")


def detect_module(query: str) -> EnzymeModule | None:
    lowered = query.lower()
    if "transglutaminase" in lowered or "mtgase" in lowered:
        return EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE
    if "anthraquinone" in lowered or "glycosyltransferase" in lowered:
        return EnzymeModule.ANTHRAQUINONE_GLYCOSYLTRANSFERASE
    return None


def resolve_query(query: str) -> ResolvedQuery:
    normalized = query.strip()
    upper = normalized.upper()
    if EC_RE.match(normalized):
        kind = QueryKind.EC
        normalized = normalized
    elif PDB_RE.match(upper):
        kind = QueryKind.PDB
        normalized = upper
    elif UNIPROT_RE.match(upper):
        kind = QueryKind.UNIPROT
        normalized = upper
    else:
        kind = QueryKind.KEYWORD
    return ResolvedQuery(
        raw_query=query,
        normalized_query=normalized,
        kind=kind,
        module_hint=detect_module(query),
    )
```

Create `apps/api/app/services/cache.py`:

```python
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import EnzymeEntry


def is_fresh(last_refreshed_at: datetime | None, days: int = 15) -> bool:
    if last_refreshed_at is None:
        return False
    return datetime.utcnow() - last_refreshed_at <= timedelta(days=days)


def find_fresh_uniprot_hit(db: Session, uniprot_id: str) -> EnzymeEntry | None:
    entry = db.scalar(select(EnzymeEntry).where(EnzymeEntry.uniprot_id == uniprot_id))
    if entry and is_fresh(entry.last_refreshed_at):
        return entry
    return None
```

- [ ] **Step 4: Implement external client boundaries**

Create `apps/api/app/external/uniprot.py`:

```python
import httpx


class UniProtClient:
    base_url = "https://rest.uniprot.org"

    def __init__(self, timeout: float = 15.0):
        self.timeout = timeout

    async def search(self, query: str, size: int = 5) -> dict:
        params = {"query": query, "format": "json", "size": size}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(f"{self.base_url}/uniprotkb/search", params=params)
            response.raise_for_status()
            return response.json()

    async def fetch_fasta(self, accession: str) -> str:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(f"{self.base_url}/uniprotkb/{accession}.fasta")
            response.raise_for_status()
            return response.text
```

Create `apps/api/app/external/rcsb.py`:

```python
import httpx


class RcsbClient:
    base_url = "https://data.rcsb.org/rest/v1/core"

    def __init__(self, timeout: float = 15.0):
        self.timeout = timeout

    async def fetch_entry(self, pdb_id: str) -> dict:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(f"{self.base_url}/entry/{pdb_id.lower()}")
            response.raise_for_status()
            return response.json()
```

Create `apps/api/app/external/alphafold.py`:

```python
import httpx


class AlphaFoldClient:
    base_url = "https://alphafold.ebi.ac.uk/api"

    def __init__(self, timeout: float = 15.0):
        self.timeout = timeout

    async def fetch_prediction(self, uniprot_id: str) -> list[dict]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(f"{self.base_url}/prediction/{uniprot_id}")
            response.raise_for_status()
            return response.json()
```

Create `apps/api/app/external/literature.py`:

```python
class LiteratureClient:
    async def search_metadata(self, query: str) -> list[dict]:
        return [
            {
                "title": f"Manual literature metadata seed for {query}",
                "source": "manual_mock",
                "year": 2026,
            }
        ]
```

- [ ] **Step 5: Run resolver tests**

Run:

```powershell
pytest apps/api/tests/test_query_resolver.py -v
```

Expected: 5 passed.

- [ ] **Step 6: Commit**

Run:

```powershell
git add apps/api/app/services apps/api/app/external apps/api/tests/test_query_resolver.py
git commit -m "feat(api): add query resolver and external clients"
```

Expected: commit succeeds.

---

### Task 5: Authentication, Projects, And Seed Data

**Files:**
- Create: `apps/api/app/core/security.py`
- Create: `apps/api/app/schemas/auth.py`
- Create: `apps/api/app/schemas/project.py`
- Create: `apps/api/app/api/routes/auth.py`
- Create: `apps/api/app/api/routes/projects.py`
- Create: `apps/api/tests/conftest.py`
- Modify: `apps/api/app/main.py`
- Create: `scripts/seed/seed.py`
- Create: `apps/api/tests/test_auth_projects.py`

- [ ] **Step 1: Write API tests**

Create `apps/api/tests/test_auth_projects.py`:

```python
def test_register_login_and_me(client):
    email = "first-user@example.com"
    password = "strong-password"

    register = client.post(
        "/auth/register",
        json={"email": email, "password": password, "display_name": "First User"},
    )
    assert register.status_code in {200, 201}
    assert register.json()["email"] == email

    login = client.post("/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200
    token = login.json()["access_token"]

    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == email
```

- [ ] **Step 2: Run test and verify it fails**

Run:

```powershell
pytest apps/api/tests/test_auth_projects.py -v
```

Expected: failure because auth routes do not exist.

- [ ] **Step 3: Implement security helpers**

Create `apps/api/app/core/security.py`:

```python
from datetime import datetime, timedelta

from jose import jwt
from passlib.context import CryptContext

from app.core.config import get_settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def create_access_token(subject: str) -> str:
    settings = get_settings()
    expires = datetime.utcnow() + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {"sub": subject, "exp": expires}
    return jwt.encode(payload, settings.api_secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str) -> str:
    settings = get_settings()
    payload = jwt.decode(token, settings.api_secret_key, algorithms=[ALGORITHM])
    return str(payload["sub"])
```

Create `apps/api/app/schemas/auth.py`:

```python
from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    display_name: str | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: str
    email: EmailStr
    display_name: str | None
    role: str

    model_config = {"from_attributes": True}
```

Create `apps/api/app/schemas/project.py`:

```python
from pydantic import BaseModel


class ProjectCreate(BaseModel):
    name: str
    description: str | None = None
    target_enzyme_module: str | None = None


class ProjectResponse(BaseModel):
    id: str
    name: str
    description: str | None
    target_enzyme_module: str | None

    model_config = {"from_attributes": True}
```

- [ ] **Step 4: Implement auth and project routes**

Create `apps/api/tests/conftest.py`:

```python
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app


@pytest.fixture()
def client():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
```

Create `apps/api/app/api/routes/auth.py`:

```python
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import create_access_token, decode_access_token, hash_password, verify_password
from app.db.models import User, UserRole
from app.db.session import get_db
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserResponse

router = APIRouter(prefix="/auth", tags=["auth"])
bearer = HTTPBearer()


def current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    user_id = decode_access_token(credentials.credentials)
    user = db.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="invalid user")
    return user


@router.post("/register", response_model=UserResponse, status_code=201)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> User:
    existing = db.scalar(select(User).where(User.email == payload.email))
    if existing:
        raise HTTPException(status_code=409, detail="email already registered")
    user = User(
        email=payload.email,
        display_name=payload.display_name,
        password_hash=hash_password(payload.password),
        role=UserRole.USER,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.scalar(select(User).where(User.email == payload.email))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="invalid credentials")
    return TokenResponse(access_token=create_access_token(user.id))


@router.get("/me", response_model=UserResponse)
def me(user: User = Depends(current_user)) -> User:
    return user
```

Create `apps/api/app/api/routes/projects.py`:

```python
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routes.auth import current_user
from app.db.models import EnzymeModule, Project, ProjectMember, ProjectMemberRole, User
from app.db.session import get_db
from app.schemas.project import ProjectCreate, ProjectResponse

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=list[ProjectResponse])
def list_projects(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return db.scalars(select(Project).where(Project.owner_user_id == user.id)).all()


@router.post("", response_model=ProjectResponse, status_code=201)
def create_project(
    payload: ProjectCreate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    module = EnzymeModule(payload.target_enzyme_module) if payload.target_enzyme_module else None
    project = Project(
        owner_user_id=user.id,
        name=payload.name,
        description=payload.description,
        target_enzyme_module=module,
    )
    db.add(project)
    db.flush()
    db.add(ProjectMember(project_id=project.id, user_id=user.id, role=ProjectMemberRole.OWNER))
    db.commit()
    db.refresh(project)
    return project
```

Modify `apps/api/app/main.py` to include routers:

```python
from app.api.routes.auth import router as auth_router
from app.api.routes.projects import router as projects_router

app.include_router(auth_router)
app.include_router(projects_router)
```

- [ ] **Step 5: Add seed script**

Create `scripts/seed/seed.py`:

```python
from sqlalchemy import select

from app.core.security import hash_password
from app.db.models import EnzymeFamily, EnzymeModule, Project, User, UserRole
from app.db.session import SessionLocal


def main() -> None:
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == "demo@iee.local"))
        if user is None:
            user = User(
                email="demo@iee.local",
                display_name="IEE Demo User",
                password_hash=hash_password("demo-password"),
                role=UserRole.ADMIN,
            )
            db.add(user)
            db.flush()

        for module, name in [
            (
                EnzymeModule.ANTHRAQUINONE_GLYCOSYLTRANSFERASE,
                "Anthraquinone Glycosyltransferase",
            ),
            (
                EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
                "Mature Microbial Transglutaminase",
            ),
        ]:
            family = db.scalar(select(EnzymeFamily).where(EnzymeFamily.module == module))
            if family is None:
                db.add(EnzymeFamily(module=module, name=name, description=name))

        project = db.scalar(select(Project).where(Project.name == "Demo enzyme engineering project"))
        if project is None:
            db.add(
                Project(
                    owner_user_id=user.id,
                    name="Demo enzyme engineering project",
                    description="Seed project for the first IEE-Copilot vertical slice",
                    target_enzyme_module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
                )
            )
        db.commit()


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Run auth tests**

Run:

```powershell
pytest apps/api/tests/test_auth_projects.py -v
```

Expected: 1 passed.

- [ ] **Step 7: Commit**

Run:

```powershell
git add apps/api/app/core/security.py apps/api/app/schemas apps/api/app/api/routes/auth.py apps/api/app/api/routes/projects.py apps/api/app/main.py scripts/seed/seed.py apps/api/tests/conftest.py apps/api/tests/test_auth_projects.py
git commit -m "feat(api): add auth projects and seed data"
```

Expected: commit succeeds.

---

### Task 6: Enzyme Search API And Job Creation

**Files:**
- Create: `apps/api/app/schemas/enzyme.py`
- Create: `apps/api/app/schemas/job.py`
- Create: `apps/api/app/api/routes/enzymes.py`
- Create: `apps/api/app/api/routes/jobs.py`
- Modify: `apps/api/app/main.py`
- Create: `apps/api/tests/test_search_flow.py`

- [ ] **Step 1: Write search flow test**

Create `apps/api/tests/test_search_flow.py`:

```python
def auth_headers(client):
    email = "search-user@example.com"
    password = "strong-password"
    client.post("/auth/register", json={"email": email, "password": password})
    token = client.post("/auth/login", json={"email": email, "password": password}).json()[
        "access_token"
    ]
    return {"Authorization": f"Bearer {token}"}


def test_search_returns_enzyme_summary_and_job_id(client):
    headers = auth_headers(client)
    project = client.post(
        "/projects",
        headers=headers,
        json={"name": "Search Project", "target_enzyme_module": "MICROBIAL_TRANSGLUTAMINASE_MATURE"},
    ).json()

    response = client.post(
        "/enzymes/search",
        headers=headers,
        json={"query": "microbial transglutaminase", "project_id": project["id"]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["enzyme"]["name"]
    assert body["job_id"]
    assert body["cache_status"] in {"hit", "miss_refreshed", "stale_refreshed"}
```

- [ ] **Step 2: Run test and verify it fails**

Run:

```powershell
pytest apps/api/tests/test_search_flow.py -v
```

Expected: failure because enzyme routes do not exist.

- [ ] **Step 3: Create schemas**

Create `apps/api/app/schemas/enzyme.py`:

```python
from pydantic import BaseModel


class EnzymeSearchRequest(BaseModel):
    query: str
    project_id: str | None = None
    organism: str | None = None
    enzyme_module: str | None = None


class EnzymeSummary(BaseModel):
    id: str
    name: str
    organism: str | None
    ec_number: str | None
    uniprot_id: str | None
    pdb_id: str | None
    alphafold_id: str | None
    source: str

    model_config = {"from_attributes": True}


class EnzymeSearchResponse(BaseModel):
    enzyme: EnzymeSummary
    job_id: str | None
    cache_status: str
    warnings: list[str] = []
```

Create `apps/api/app/schemas/job.py`:

```python
from pydantic import BaseModel


class JobResponse(BaseModel):
    id: str
    job_type: str
    status: str
    error_message: str | None

    model_config = {"from_attributes": True}
```

- [ ] **Step 4: Implement enzyme and job routes**

Create `apps/api/app/api/routes/enzymes.py`:

```python
import hashlib
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routes.auth import current_user
from app.db.models import (
    AnalysisJob,
    EnzymeEntry,
    EnzymeFamily,
    EnzymeModule,
    JobStatus,
    ProteinSequence,
    User,
)
from app.db.session import get_db
from app.schemas.enzyme import EnzymeSearchRequest, EnzymeSearchResponse, EnzymeSummary
from app.services.cache import find_fresh_uniprot_hit
from app.services.query_resolver import QueryKind, resolve_query

router = APIRouter(prefix="/enzymes", tags=["enzymes"])


def sequence_checksum(sequence: str) -> str:
    return hashlib.sha256(sequence.encode("utf-8")).hexdigest()


def ensure_family(db: Session, module: EnzymeModule) -> EnzymeFamily:
    family = db.scalar(select(EnzymeFamily).where(EnzymeFamily.module == module))
    if family:
        return family
    family = EnzymeFamily(module=module, name=module.value, description=module.value)
    db.add(family)
    db.flush()
    return family


def create_seed_entry(db: Session, query: str, module: EnzymeModule | None) -> EnzymeEntry:
    family = ensure_family(db, module or EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE)
    entry = EnzymeEntry(
        family_id=family.id,
        name=query.title(),
        organism=None,
        ec_number=None,
        uniprot_id=None,
        pdb_id=None,
        alphafold_id=None,
        source="search_seed",
        last_refreshed_at=datetime.utcnow(),
    )
    db.add(entry)
    db.flush()
    sequence = "M" + "A" * 120
    db.add(
        ProteinSequence(
            enzyme_entry_id=entry.id,
            sequence=sequence,
            mature_sequence=sequence,
            is_engineering_target=True,
            source="search_seed",
            checksum=sequence_checksum(sequence),
        )
    )
    return entry


def to_summary(entry: EnzymeEntry) -> EnzymeSummary:
    return EnzymeSummary(
        id=entry.id,
        name=entry.name,
        organism=entry.organism,
        ec_number=entry.ec_number,
        uniprot_id=entry.uniprot_id,
        pdb_id=entry.pdb_id,
        alphafold_id=entry.alphafold_id,
        source=entry.source,
    )


@router.post("/search", response_model=EnzymeSearchResponse)
def search_enzymes(
    payload: EnzymeSearchRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    resolved = resolve_query(payload.query)
    cache_status = "miss_refreshed"
    entry = None
    if resolved.kind == QueryKind.UNIPROT:
        entry = find_fresh_uniprot_hit(db, resolved.normalized_query)
        if entry:
            cache_status = "hit"
    if entry is None:
        entry = create_seed_entry(db, payload.query, resolved.module_hint)
    job = AnalysisJob(
        project_id=payload.project_id,
        enzyme_entry_id=entry.id,
        job_type="family_profile_placeholder",
        status=JobStatus.QUEUED,
        parameters_json={"query": payload.query, "resolved_kind": resolved.kind.value},
        created_by=user.id,
    )
    db.add(job)
    db.commit()
    db.refresh(entry)
    db.refresh(job)
    return EnzymeSearchResponse(enzyme=to_summary(entry), job_id=job.id, cache_status=cache_status)


@router.get("/{enzyme_id}", response_model=EnzymeSummary)
def get_enzyme(enzyme_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    entry = db.get(EnzymeEntry, enzyme_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="enzyme not found")
    return to_summary(entry)
```

Create `apps/api/app/api/routes/jobs.py`:

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routes.auth import current_user
from app.db.models import AnalysisJob, User
from app.db.session import get_db
from app.schemas.job import JobResponse

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("", response_model=list[JobResponse])
def list_jobs(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return db.scalars(select(AnalysisJob).where(AnalysisJob.created_by == user.id)).all()


@router.get("/{job_id}", response_model=JobResponse)
def get_job(job_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    job = db.get(AnalysisJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job
```

Modify `apps/api/app/main.py`:

```python
from app.api.routes.enzymes import router as enzymes_router
from app.api.routes.jobs import router as jobs_router

app.include_router(enzymes_router)
app.include_router(jobs_router)
```

- [ ] **Step 5: Run search flow test**

Run:

```powershell
pytest apps/api/tests/test_search_flow.py -v
```

Expected: 1 passed.

- [ ] **Step 6: Commit**

Run:

```powershell
git add apps/api/app/schemas/enzyme.py apps/api/app/schemas/job.py apps/api/app/api/routes/enzymes.py apps/api/app/api/routes/jobs.py apps/api/app/main.py apps/api/tests/test_search_flow.py
git commit -m "feat(api): add enzyme search vertical slice"
```

Expected: commit succeeds.

---

### Task 7: Celery Worker And Artifact Record Update

**Files:**
- Create: `apps/api/app/tasks/__init__.py`
- Create: `apps/api/app/tasks/celery_app.py`
- Create: `apps/worker/worker/__init__.py`
- Create: `apps/worker/worker/main.py`
- Create: `apps/worker/worker/jobs.py`
- Create: `apps/worker/tests/test_worker_jobs.py`

- [ ] **Step 1: Write worker unit test**

Create `apps/worker/tests/test_worker_jobs.py`:

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.db.models import AnalysisArtifact, AnalysisJob, JobStatus
from worker.jobs import finish_placeholder_job


def test_finish_placeholder_job_updates_status_and_artifact():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)

    with SessionLocal() as db:
        job = AnalysisJob(job_type="family_profile_placeholder", status=JobStatus.QUEUED)
        db.add(job)
        db.commit()
        job_id = job.id

    with SessionLocal() as db:
        finish_placeholder_job(db, job_id, bucket="iee-artifacts")

    with SessionLocal() as db:
        saved_job = db.get(AnalysisJob, job_id)
        artifacts = db.query(AnalysisArtifact).filter_by(job_id=job_id).all()

    assert saved_job.status == JobStatus.FINISHED
    assert saved_job.result_summary_json["message"] == "placeholder analysis completed"
    assert len(artifacts) == 1
    assert artifacts[0].artifact_type == "family_profile_summary"
```

- [ ] **Step 2: Run test and verify it fails**

Run:

```powershell
pytest apps/worker/tests/test_worker_jobs.py -v
```

Expected: failure because `worker.jobs` does not exist.

- [ ] **Step 3: Implement Celery app and worker job**

Create `apps/api/app/tasks/celery_app.py`:

```python
from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "iee_copilot",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["worker.jobs"],
)
```

Create `apps/worker/worker/jobs.py`:

```python
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import AnalysisArtifact, AnalysisJob, JobStatus
from app.db.session import SessionLocal
from app.tasks.celery_app import celery_app


def finish_placeholder_job(db: Session, job_id: str, bucket: str) -> None:
    job = db.get(AnalysisJob, job_id)
    if job is None:
        raise ValueError(f"analysis job not found: {job_id}")
    job.status = JobStatus.RUNNING
    job.started_at = datetime.utcnow()
    db.flush()
    artifact = AnalysisArtifact(
        project_id=job.project_id,
        enzyme_entry_id=job.enzyme_entry_id,
        job_id=job.id,
        artifact_type="family_profile_summary",
        bucket=bucket,
        object_key=f"jobs/{job.id}/family-profile-summary.json",
        content_type="application/json",
        size_bytes=2,
        source="worker",
    )
    db.add(artifact)
    job.status = JobStatus.FINISHED
    job.finished_at = datetime.utcnow()
    job.result_summary_json = {"message": "placeholder analysis completed"}
    db.commit()


@celery_app.task(name="worker.jobs.run_placeholder_analysis")
def run_placeholder_analysis(job_id: str) -> None:
    settings = get_settings()
    with SessionLocal() as db:
        finish_placeholder_job(db, job_id, bucket=settings.minio_bucket)
```

Create `apps/worker/worker/main.py`:

```python
from app.tasks.celery_app import celery_app

__all__ = ["celery_app"]
```

Create empty package markers:

```python
# apps/api/app/tasks/__init__.py
```

```python
# apps/worker/worker/__init__.py
```

- [ ] **Step 4: Run worker tests**

Run:

```powershell
pytest apps/worker/tests/test_worker_jobs.py -v
```

Expected: 1 passed.

- [ ] **Step 5: Commit**

Run:

```powershell
git add apps/api/app/tasks apps/worker
git commit -m "feat(worker): add placeholder analysis task"
```

Expected: commit succeeds.

---

### Task 8: Next.js Workbench Frontend

**Files:**
- Create: `apps/web/package.json`
- Create: `apps/web/next.config.mjs`
- Create: `apps/web/tsconfig.json`
- Create: `apps/web/tailwind.config.ts`
- Create: `apps/web/postcss.config.mjs`
- Create: `apps/web/app/layout.tsx`
- Create: `apps/web/app/page.tsx`
- Create: `apps/web/app/login/page.tsx`
- Create: `apps/web/app/search/page.tsx`
- Create: `apps/web/app/enzymes/[id]/page.tsx`
- Create: `apps/web/app/jobs/[id]/page.tsx`
- Create: `apps/web/lib/api.ts`
- Create: `apps/web/lib/types.ts`

- [ ] **Step 1: Create Next.js package files**

Create `apps/web/package.json`:

```json
{
  "name": "@iee-copilot/web",
  "private": true,
  "scripts": {
    "dev": "next dev -H 0.0.0.0",
    "build": "next build",
    "start": "next start -H 0.0.0.0",
    "lint": "next lint"
  },
  "dependencies": {
    "next": "15.1.0",
    "react": "19.0.0",
    "react-dom": "19.0.0"
  },
  "devDependencies": {
    "@types/node": "^22.10.0",
    "@types/react": "^19.0.0",
    "@types/react-dom": "^19.0.0",
    "autoprefixer": "^10.4.20",
    "postcss": "^8.4.49",
    "tailwindcss": "^3.4.17",
    "typescript": "^5.7.2"
  }
}
```

Create `apps/web/next.config.mjs`:

```js
const nextConfig = {
  output: "standalone"
};

export default nextConfig;
```

Create `apps/web/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["dom", "dom.iterable", "es2022"],
    "allowJs": false,
    "skipLibCheck": true,
    "strict": true,
    "noEmit": true,
    "esModuleInterop": true,
    "module": "esnext",
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "jsx": "preserve",
    "incremental": true,
    "plugins": [{"name": "next"}]
  },
  "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx", ".next/types/**/*.ts"],
  "exclude": ["node_modules"]
}
```

Create `apps/web/tailwind.config.ts`:

```ts
import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {}
  },
  plugins: []
};

export default config;
```

Create `apps/web/postcss.config.mjs`:

```js
const config = {
  plugins: {
    tailwindcss: {},
    autoprefixer: {}
  }
};

export default config;
```

- [ ] **Step 2: Add API client and types**

Create `apps/web/lib/types.ts`:

```ts
export type EnzymeSummary = {
  id: string;
  name: string;
  organism: string | null;
  ec_number: string | null;
  uniprot_id: string | null;
  pdb_id: string | null;
  alphafold_id: string | null;
  source: string;
};

export type SearchResponse = {
  enzyme: EnzymeSummary;
  job_id: string | null;
  cache_status: string;
  warnings: string[];
};

export type JobResponse = {
  id: string;
  job_type: string;
  status: string;
  error_message: string | null;
};
```

Create `apps/web/lib/api.ts`:

```ts
import type { SearchResponse } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export async function searchEnzyme(query: string, token: string): Promise<SearchResponse> {
  const response = await fetch(`${API_BASE}/enzymes/search`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      authorization: `Bearer ${token}`
    },
    body: JSON.stringify({ query })
  });
  if (!response.ok) {
    throw new Error(`Search failed with status ${response.status}`);
  }
  return response.json();
}
```

- [ ] **Step 3: Build workbench pages**

Create `apps/web/app/layout.tsx`:

```tsx
import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "IEE-Copilot",
  description: "Industrial Enzyme Engineering Copilot"
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
```

Create `apps/web/app/globals.css`:

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

body {
  background: #f7f8fb;
  color: #172033;
}
```

Create `apps/web/app/page.tsx`:

```tsx
import Link from "next/link";

export default function DashboardPage() {
  return (
    <main className="mx-auto max-w-6xl px-6 py-8">
      <header className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">IEE-Copilot</h1>
          <p className="text-sm text-slate-600">Industrial enzyme engineering workbench</p>
        </div>
        <Link className="rounded bg-slate-900 px-4 py-2 text-sm text-white" href="/search">
          Search enzyme
        </Link>
      </header>
      <section className="grid gap-4 md:grid-cols-3">
        {["Projects", "Recent searches", "Analysis jobs"].map((title) => (
          <div key={title} className="rounded border border-slate-200 bg-white p-5">
            <h2 className="font-medium">{title}</h2>
            <p className="mt-2 text-sm text-slate-600">Ready for the first vertical slice.</p>
          </div>
        ))}
      </section>
    </main>
  );
}
```

Create `apps/web/app/login/page.tsx`:

```tsx
export default function LoginPage() {
  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center px-6">
      <h1 className="text-2xl font-semibold">Sign in</h1>
      <p className="mt-2 text-sm text-slate-600">Development seed account: demo@iee.local</p>
      <form className="mt-6 grid gap-3">
        <input className="rounded border px-3 py-2" placeholder="Email" />
        <input className="rounded border px-3 py-2" placeholder="Password" type="password" />
        <button className="rounded bg-slate-900 px-4 py-2 text-white" type="button">
          Sign in
        </button>
      </form>
    </main>
  );
}
```

Create `apps/web/app/search/page.tsx`:

```tsx
export default function SearchPage() {
  return (
    <main className="mx-auto max-w-4xl px-6 py-8">
      <h1 className="text-2xl font-semibold">Search enzyme</h1>
      <p className="mt-2 text-sm text-slate-600">
        Search by enzyme name, EC number, UniProt ID, PDB ID, or organism.
      </p>
      <form className="mt-6 flex gap-3">
        <input
          className="min-w-0 flex-1 rounded border border-slate-300 px-3 py-2"
          defaultValue="microbial transglutaminase"
          name="query"
        />
        <button className="rounded bg-slate-900 px-4 py-2 text-white" type="submit">
          Search
        </button>
      </form>
      <section className="mt-8 rounded border border-dashed border-slate-300 bg-white p-5">
        <h2 className="font-medium">PDB upload</h2>
        <p className="mt-2 text-sm text-slate-600">
          Apo and enzyme-substrate complex upload enters this workflow after the skeleton is stable.
        </p>
      </section>
    </main>
  );
}
```

Create `apps/web/app/enzymes/[id]/page.tsx`:

```tsx
export default function EnzymeDetailPage({ params }: { params: { id: string } }) {
  return (
    <main className="mx-auto max-w-5xl px-6 py-8">
      <h1 className="text-2xl font-semibold">Enzyme detail</h1>
      <p className="mt-2 text-sm text-slate-600">Entry id: {params.id}</p>
      <section className="mt-6 rounded border bg-white p-5">
        <h2 className="font-medium">Summary</h2>
        <p className="mt-2 text-sm text-slate-600">
          Sequence, structure source, cache timestamp, and analysis job status render here.
        </p>
      </section>
    </main>
  );
}
```

Create `apps/web/app/jobs/[id]/page.tsx`:

```tsx
export default function JobDetailPage({ params }: { params: { id: string } }) {
  return (
    <main className="mx-auto max-w-4xl px-6 py-8">
      <h1 className="text-2xl font-semibold">Analysis job</h1>
      <p className="mt-2 text-sm text-slate-600">Job id: {params.id}</p>
      <section className="mt-6 rounded border bg-white p-5">
        <h2 className="font-medium">Status</h2>
        <p className="mt-2 text-sm text-slate-600">
          queued, running, finished, failed, and artifact list are shown here.
        </p>
      </section>
    </main>
  );
}
```

- [ ] **Step 4: Install and build web**

Run:

```powershell
pnpm install
pnpm --filter @iee-copilot/web build
```

Expected: Next.js build succeeds.

- [ ] **Step 5: Commit**

Run:

```powershell
git add apps/web package.json pnpm-workspace.yaml
git commit -m "feat(web): add workbench frontend skeleton"
```

Expected: commit succeeds.

---

### Task 9: Docker Compose And Service Containers

**Files:**
- Create: `docker-compose.yml`
- Create: `apps/api/Dockerfile`
- Create: `apps/worker/Dockerfile`
- Create: `apps/web/Dockerfile`

- [ ] **Step 1: Create API Dockerfile**

Create `apps/api/Dockerfile`:

```dockerfile
FROM python:3.12-slim

WORKDIR /app
ENV PYTHONPATH=/app/apps/api:/app/apps/worker

COPY pyproject.toml /app/pyproject.toml
RUN pip install --no-cache-dir ".[dev]"

COPY apps/api /app/apps/api
COPY apps/worker /app/apps/worker

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--app-dir", "apps/api"]
```

- [ ] **Step 2: Create worker Dockerfile**

Create `apps/worker/Dockerfile`:

```dockerfile
FROM python:3.12-slim

WORKDIR /app
ENV PYTHONPATH=/app/apps/api:/app/apps/worker

COPY pyproject.toml /app/pyproject.toml
RUN pip install --no-cache-dir ".[dev]"

COPY apps/api /app/apps/api
COPY apps/worker /app/apps/worker

CMD ["celery", "-A", "worker.main.celery_app", "worker", "--loglevel=INFO"]
```

- [ ] **Step 3: Create web Dockerfile**

Create `apps/web/Dockerfile`:

```dockerfile
FROM node:22-slim AS deps
WORKDIR /app
COPY package.json pnpm-workspace.yaml /app/
COPY apps/web/package.json /app/apps/web/package.json
RUN corepack enable && pnpm install --frozen-lockfile=false

FROM node:22-slim AS builder
WORKDIR /app
COPY --from=deps /app/node_modules /app/node_modules
COPY --from=deps /app/apps/web/node_modules /app/apps/web/node_modules
COPY . /app
RUN corepack enable && pnpm --filter @iee-copilot/web build

FROM node:22-slim
WORKDIR /app
ENV NODE_ENV=production
COPY --from=builder /app/apps/web/.next/standalone ./
COPY --from=builder /app/apps/web/.next/static ./apps/web/.next/static
COPY --from=builder /app/apps/web/public ./apps/web/public
CMD ["node", "apps/web/server.js"]
```

- [ ] **Step 4: Create compose file**

Create `docker-compose.yml`:

```yaml
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_DB: iee_copilot
      POSTGRES_USER: iee
      POSTGRES_PASSWORD: iee_dev_password
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data

  redis:
    image: redis:7
    ports:
      - "6379:6379"

  minio:
    image: minio/minio:RELEASE.2025-04-22T22-12-26Z
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: iee_minio
      MINIO_ROOT_PASSWORD: iee_minio_password
    ports:
      - "9000:9000"
      - "9001:9001"
    volumes:
      - minio_data:/data

  api:
    build:
      context: .
      dockerfile: apps/api/Dockerfile
    env_file: .env.example
    ports:
      - "8000:8000"
    depends_on:
      - postgres
      - redis
      - minio

  worker:
    build:
      context: .
      dockerfile: apps/worker/Dockerfile
    env_file: .env.example
    depends_on:
      - api
      - redis
      - postgres

  web:
    build:
      context: .
      dockerfile: apps/web/Dockerfile
    environment:
      NEXT_PUBLIC_API_BASE_URL: http://localhost:8000
    ports:
      - "3000:3000"
    depends_on:
      - api

volumes:
  postgres_data:
  minio_data:
```

- [ ] **Step 5: Build compose stack**

Run:

```powershell
docker compose build
```

Expected: all service images build.

- [ ] **Step 6: Commit**

Run:

```powershell
git add docker-compose.yml apps/api/Dockerfile apps/worker/Dockerfile apps/web/Dockerfile
git commit -m "chore: add local docker compose stack"
```

Expected: commit succeeds.

---

### Task 10: End-To-End Verification And Documentation Update

**Files:**
- Modify: `README.md`
- Modify: `tests/integration/test_compose_contract.md`

- [ ] **Step 1: Create README**

Create or replace `README.md`:

```markdown
# IEE-Copilot

Industrial Enzyme Engineering Copilot is a web platform skeleton for enzyme search, data caching, structure-aware analysis jobs, and future closed-loop enzyme engineering.

## Local Development

Copy environment settings:

```powershell
Copy-Item .env.example .env
```

Start the local stack:

```powershell
docker compose up --build
```

Open:

- Web: http://localhost:3000
- API health: http://localhost:8000/health
- MinIO console: http://localhost:9001

## First Vertical Slice

The first vertical slice supports:

1. Register or log in.
2. Create a project.
3. Search `microbial transglutaminase`.
4. Receive an enzyme summary and analysis job id.
5. Inspect job status.

## Development Checks

```powershell
pytest apps/api/tests apps/worker/tests -v
pnpm --filter @iee-copilot/web build
```
```

- [ ] **Step 2: Run Python tests**

Run:

```powershell
pytest apps/api/tests apps/worker/tests -v
```

Expected: all Python tests pass.

- [ ] **Step 3: Run web build**

Run:

```powershell
pnpm --filter @iee-copilot/web build
```

Expected: Next.js build succeeds.

- [ ] **Step 4: Run compose health check**

Run:

```powershell
docker compose up --build
```

In a second terminal, run:

```powershell
Invoke-WebRequest -Uri http://localhost:8000/health -UseBasicParsing
```

Expected response body:

```json
{"status":"ok","service":"iee-copilot-api"}
```

- [ ] **Step 5: Commit**

Run:

```powershell
git add README.md tests/integration/test_compose_contract.md
git commit -m "docs: add local development verification guide"
```

Expected: commit succeeds.

---

## Self-Review Checklist

- [ ] Task 1 covers repository initialization, root workspace files, shared enums, and compose contract documentation.
- [ ] Task 2 covers FastAPI app startup and health checks.
- [ ] Task 3 covers the first scientific core schema and Alembic.
- [ ] Task 4 covers query parsing, 15-day cache helper, and external client boundaries.
- [ ] Task 5 covers auth, projects, roles, and seed data.
- [ ] Task 6 covers the minimum search vertical slice and job creation.
- [ ] Task 7 covers Celery worker status transitions and artifact record creation.
- [ ] Task 8 covers the workbench-first frontend skeleton.
- [ ] Task 9 covers Docker Compose and service containers.
- [ ] Task 10 covers verification and README instructions.
- [ ] The plan intentionally excludes real Rosetta, real MAFFT/MSA, MD, MMPBSA, full active learning, and complete curator UI from the first implementation round.
