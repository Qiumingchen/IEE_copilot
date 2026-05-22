# AGENTS.md

## Project Overview

This repository contains **IEE-Copilot**, an agentic web platform for industrial enzyme engineering.

The platform focuses on two enzyme modules:

1. **Anthraquinone Glycosyltransferases**
   - For anthraquinone substrate glycosylation.
   - Supports user-defined anthraquinone substrates.
   - Main goals: specific activity, soluble expression, product selectivity, substrate specificity, thermostability.

2. **Mature Microbial Transglutaminases**
   - Only mature enzyme sequences are used as engineering targets.
   - Pro-region information may be stored as annotation, but should not be used for mutation design in the MVP.
   - Main goals: thermostability, optimal temperature, optimal pH, specific activity, soluble expression.

The platform supports:

- Enzyme search by name, EC number, organism, UniProt ID, PDB ID.
- Apo PDB and enzyme-substrate complex PDB upload.
- Local database caching with 15-day freshness policy.
- External data retrieval from UniProt, RCSB PDB, AlphaFold DB, and literature metadata sources.
- Homologous sequence collection, MSA, and conservation analysis.
- Reported enzyme property and mutant data dashboards.
- Structure-aware mutation recommendation.
- Rosetta ddG job queue.
- Placeholder interfaces for MD and MMPBSA.
- Wet-lab data upload.
- Private/public data visibility with curator review.
- Active-learning-based next-round mutation recommendation.

---

## Repository Structure

Expected structure:

```text
apps/
  web/              # Next.js frontend
  api/              # FastAPI backend
  worker/           # Celery/RQ worker tasks

packages/
  shared/           # Shared TypeScript/Python schemas if needed

docker/
  Dockerfiles and service configs

docs/
  Product documents, API docs, architecture notes

scripts/
  Utility scripts for data import, migration, analysis

tests/
  Unit and integration tests

写程序的时候，每完成了一小部分内容，如果检测通过，继续检索下一步需要干什么，如果没有什么太大的争议需要让用户决定，就直接进行下一步的编写，直到功能有了较大的更新升级为止