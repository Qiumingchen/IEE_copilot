import assert from "node:assert/strict";
import { test } from "node:test";

import {
  buildMutationPositionSummary,
  buildMutationDeltaSummary,
  buildMutationPropertyDeltaOptions,
  buildMutationEvidenceCsv,
  filterMutationEvidenceRecords,
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

test("buildMutationDeltaSummary groups numeric property deltas by effect direction", () => {
  assert.deepEqual(
    buildMutationDeltaSummary([
      {
        mutation_string: "S2P",
        effect_summary: "Improved thermostability",
        property_delta: {
          optimal_temperature_delta_degC: 5,
          specific_activity_fold_change: 1.2
        }
      },
      {
        mutation_string: "D3Y",
        effect_summary: "Lower activity",
        property_delta: {
          optimal_temperature_delta_degC: -2,
          specific_activity_fold_change: 0.8
        }
      },
      {
        mutation_string: "G4A",
        effect_summary: null,
        property_delta: {
          optimal_temperature_delta_degC: 0,
          note: "qualitative only"
        }
      }
    ]),
    [
      {
        property: "optimal_temperature_delta_degC",
        improved: 1,
        worsened: 1,
        neutral: 1,
        top_mutations: [
          { mutation_string: "S2P", value: 5, effect_summary: "Improved thermostability" },
          { mutation_string: "G4A", value: 0, effect_summary: null },
          { mutation_string: "D3Y", value: -2, effect_summary: "Lower activity" }
        ]
      },
      {
        property: "specific_activity_fold_change",
        improved: 1,
        worsened: 1,
        neutral: 0,
        top_mutations: [
          { mutation_string: "S2P", value: 1.2, effect_summary: "Improved thermostability" },
          { mutation_string: "D3Y", value: 0.8, effect_summary: "Lower activity" }
        ]
      }
    ]
  );
});

test("buildMutationPropertyDeltaOptions keeps common keys first and appends observed keys", () => {
  assert.deepEqual(
    buildMutationPropertyDeltaOptions([
      {
        property_delta: {
          product_selectivity_delta: 0.3,
          thermostability_half_life_fold_change: 2.4
        }
      },
      {
        property_delta: {
          catalytic_efficiency_fold_change: 1.7,
          optimal_temperature_delta_degC: 5
        }
      }
    ]),
    [
      "",
      "optimal_temperature_delta_degC",
      "specific_activity_fold_change",
      "optimal_pH_delta",
      "soluble_expression_fold_change",
      "product_selectivity_delta",
      "catalytic_efficiency_fold_change",
      "thermostability_half_life_fold_change"
    ]
  );
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

test("filterMutationEvidenceRecords narrows by reference source and curation status", () => {
  const sourceRecords = [
    {
      mutation_string: "S2P",
      curation_status: "approved",
      reference: { source: "curated_literature" },
      assay_condition_summary: { source: "curated_literature" }
    },
    {
      mutation_string: "D3Y",
      curation_status: "unreviewed",
      reference: null,
      assay_condition_summary: { source: "user_upload" }
    }
  ];

  assert.deepEqual(
    filterMutationEvidenceRecords(sourceRecords, {
      referenceSource: "curated_literature",
      curationStatus: "approved"
    }).map((record) => record.mutation_string),
    ["S2P"]
  );
});

test("buildMutationEvidenceCsv exports mutation evidence fields", () => {
  const csv = buildMutationEvidenceCsv([
    {
      mutation_string: "S2P",
      effect_summary: "Improved thermostability",
      property_delta: { optimal_temperature_delta_degC: 5 },
      substrate: "casein",
      reference_id: "ref-1",
      reference: {
        id: "ref-1",
        title: "Thermostable MTGase variant",
        authors: null,
        journal: "Biocatalysis Reports",
        year: 2024,
        doi: null,
        pubmed_id: "123456",
        source: "curated_literature",
        provenance: null
      },
      assay_condition_summary: {
        source: "curated_literature",
        evidence: "S2P increased half-life"
      },
      visibility: "public",
      curation_status: "approved"
    }
  ]);

  assert.equal(
    csv,
    [
      "mutation_string,effect_summary,property_delta,substrate,reference,evidence_text,visibility,curation_status",
      'S2P,Improved thermostability,"{""optimal_temperature_delta_degC"":5}",casein,PMID 123456 · Thermostable MTGase variant · Biocatalysis Reports · 2024 · curated_literature,S2P increased half-life,public,approved'
    ].join("\n")
  );
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
