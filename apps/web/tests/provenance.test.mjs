import assert from "node:assert/strict";
import { test } from "node:test";

import {
  formatProvenanceLabel,
  getProvenanceModeTone,
  provenanceFromRecord
} from "../lib/provenance.ts";

test("formats real provenance with provider and retrieval time", () => {
  assert.equal(
    formatProvenanceLabel({
      provider: "uniprot",
      mode: "real",
      retrieved_at: "2026-05-21T00:00:00Z",
      source_url: "https://rest.uniprot.org/uniprotkb/P81453.json"
    }),
    "uniprot real / 2026-05-21T00:00:00Z"
  );
});

test("extracts provenance from nested JSON records", () => {
  assert.deepEqual(
    provenanceFromRecord({
      chain_summary: {
        provenance: {
          provider: "alphafold_mock",
          mode: "fallback",
          warning: "AlphaFold provider failed"
        }
      }
    }, "chain_summary"),
    {
      provider: "alphafold_mock",
      mode: "fallback",
      warning: "AlphaFold provider failed"
    }
  );
});

test("maps provenance mode to display tone", () => {
  assert.equal(getProvenanceModeTone({ mode: "real" }), "real");
  assert.equal(getProvenanceModeTone({ mode: "fallback" }), "fallback");
  assert.equal(getProvenanceModeTone(null), "unknown");
});
