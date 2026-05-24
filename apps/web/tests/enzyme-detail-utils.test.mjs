import assert from "node:assert/strict";
import { test } from "node:test";

import {
  formatConditionEvidence,
  formatRealDataRefreshSummary,
  formatReferenceForTable,
  formatVisibilityStatus
} from "../app/enzymes/[id]/enzyme-detail-utils.ts";

const referencesById = {
  "ref-1": {
    id: "ref-1",
    title: "Curated MTGase thermostability",
    authors: null,
    journal: "Biocatalysis Reports",
    year: 2024,
    doi: "10.1000/detail",
    pubmed_id: null,
    source: "curated_literature",
    provenance: { mode: "curated" }
  }
};

test("formatReferenceForTable prefers readable literature metadata", () => {
  assert.equal(
    formatReferenceForTable("ref-1", referencesById),
    "10.1000/detail | Curated MTGase thermostability | Biocatalysis Reports | 2024 | curated_literature"
  );
});

test("formatReferenceForTable falls back to id or dash", () => {
  assert.equal(formatReferenceForTable("missing-ref", referencesById), "missing-ref");
  assert.equal(formatReferenceForTable(null, referencesById), "-");
});

test("formatVisibilityStatus combines visibility and curation status", () => {
  assert.equal(formatVisibilityStatus("public", "approved"), "public / approved");
  assert.equal(formatVisibilityStatus(undefined, undefined), "-");
});

test("formatConditionEvidence extracts curated evidence from condition metadata", () => {
  assert.equal(
    formatConditionEvidence({
      source: "curated_literature",
      evidence: "Soluble expression reported in Fig. 2"
    }),
    "Soluble expression reported in Fig. 2"
  );
  assert.equal(formatConditionEvidence({ evidence: "   " }), "-");
  assert.equal(formatConditionEvidence({ evidence: 123 }), "-");
  assert.equal(formatConditionEvidence(null), "-");
});

test("formatRealDataRefreshSummary reports created records and sources", () => {
  assert.equal(
    formatRealDataRefreshSummary(
      { references: 1, properties: 2, kinetics: 1, mutations: 1, structures: 0 },
      ["crossref", "europepmc"]
    ),
    "Fetched real data: references 1, properties 2, kinetics 1, mutations 1, structures 0. Sources: crossref, europepmc."
  );
});
