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


  Karpathy skill

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" â†?"Write tests for invalid inputs, then make them pass"
- "Fix the bug" â†?"Write a test that reproduces it, then make it pass"
- "Refactor X" â†?"Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] â†?verify: [check]
2. [Step] â†?verify: [check]
3. [Step] â†?verify: [check]
```
