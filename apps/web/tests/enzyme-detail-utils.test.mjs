import assert from "node:assert/strict";
import { test } from "node:test";

import {
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
    "10.1000/detail · Curated MTGase thermostability · Biocatalysis Reports · 2024 · curated_literature"
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
