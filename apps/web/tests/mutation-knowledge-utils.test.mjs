import assert from "node:assert/strict";
import { test } from "node:test";

import {
  buildMutationPositionSummary,
  formatMutationEvidence,
  formatPropertyDelta
} from "../app/enzymes/[id]/mutations/mutation-knowledge-utils.ts";

const records = [
  {
    mutation_string: "S2P",
    mutation_positions: [{ wildtype: "S", position: 2, mutant: "P" }],
    property_delta: { optimal_temperature_delta_degC: 5 },
    assay_condition_summary: {
      source: "enzyme_data_mock",
      evidence: "Mock mutant data record"
    }
  },
  {
    mutation_string: "S2P/D3Y",
    mutation_positions: [
      { wildtype: "S", position: 2, mutant: "P" },
      { wildtype: "D", position: 3, mutant: "Y" }
    ],
    property_delta: { specific_activity_fold_change: 1.8 },
    assay_condition_summary: { source: "literature" }
  }
];

test("buildMutationPositionSummary counts records per mutated site", () => {
  assert.deepEqual(buildMutationPositionSummary(records), [
    { position: 2, count: 2, mutations: ["S2P", "S2P/D3Y"] },
    { position: 3, count: 1, mutations: ["S2P/D3Y"] }
  ]);
});

test("formatPropertyDelta renders key value pairs", () => {
  assert.equal(
    formatPropertyDelta({ optimal_temperature_delta_degC: 5, specific_activity_fold_change: 1.8 }),
    "optimal_temperature_delta_degC: 5 · specific_activity_fold_change: 1.8"
  );
  assert.equal(formatPropertyDelta(null), "-");
});

test("formatMutationEvidence combines source and evidence text", () => {
  assert.equal(formatMutationEvidence(records[0]), "enzyme_data_mock · Mock mutant data record");
  assert.equal(formatMutationEvidence({ assay_condition_summary: null }), "-");
});

test("formatMutationEvidence prefers readable reference metadata when available", () => {
  const reference = {
    id: "ref-1",
    title: "Thermostable MTGase variant",
    authors: null,
    journal: "Biocatalysis Reports",
    year: 2024,
    doi: "10.1000/s2p",
    pubmed_id: null,
    source: "curated_literature",
    provenance: { mode: "curated" }
  };

  assert.equal(
    formatMutationEvidence({
      reference_id: "ref-1",
      reference,
      assay_condition_summary: {
        source: "curated_literature",
        evidence: "S2P increased half-life"
      }
    }),
    "10.1000/s2p · Thermostable MTGase variant · Biocatalysis Reports · 2024 · curated_literature · S2P increased half-life"
  );
  assert.equal(
    formatMutationEvidence(
      {
        reference_id: "ref-1",
        assay_condition_summary: {
          source: "curated_literature",
          evidence: "S2P increased half-life"
        }
      },
      {
        "ref-1": {
          ...reference
        }
      }
    ),
    "10.1000/s2p · Thermostable MTGase variant · Biocatalysis Reports · 2024 · curated_literature · S2P increased half-life"
  );
});
