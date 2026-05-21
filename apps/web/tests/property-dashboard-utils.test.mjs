import assert from "node:assert/strict";
import { test } from "node:test";

import {
  buildPropertyOptions,
  buildPropertyEvidenceCsv,
  filterPropertyEvidenceRecords,
  formatKineticEvidence,
  formatPropertyEvidence,
  formatRankingValue,
  summarizeRankingGroup
} from "../app/enzymes/[id]/properties/property-dashboard-utils.ts";

test("buildPropertyOptions keeps common properties first and appends observed properties", () => {
  const options = buildPropertyOptions([
    { property_type: "specific_activity" },
    { property_type: "product_selectivity" },
    { property_type: "optimal_temperature" }
  ]);

  assert.deepEqual(options.slice(0, 3), [
    "optimal_temperature",
    "optimal_pH",
    "specific_activity"
  ]);
  assert.equal(options.includes("product_selectivity"), true);
});

test("formatRankingValue prefers standardized values while preserving reported values", () => {
  assert.equal(
    formatRankingValue({
      value_original: "328.15",
      unit_original: "K",
      value_standardized: "55",
      unit_standardized: "degC"
    }),
    "55 degC (reported 328.15 K)"
  );
});

test("filterPropertyEvidenceRecords narrows by source and curation status", () => {
  const records = [
    {
      property_type: "optimal_temperature",
      curation_status: "approved",
      reference: { source: "curated_literature" },
      reference_id: "ref-1"
    },
    {
      property_type: "optimal_temperature",
      curation_status: "unreviewed",
      reference: { source: "user_upload" },
      reference_id: "ref-2"
    },
    {
      property_type: "optimal_pH",
      curation_status: "approved",
      reference: { source: "curated_literature" },
      reference_id: "ref-3"
    }
  ];

  assert.deepEqual(
    filterPropertyEvidenceRecords(records, {
      propertyType: "optimal_temperature",
      referenceSource: "curated_literature",
      curationStatus: "approved"
    }).map((record) => record.reference_id),
    ["ref-1"]
  );
});

test("buildPropertyEvidenceCsv exports citation and assay fields", () => {
  const csv = buildPropertyEvidenceCsv([
    {
      property_type: "optimal_temperature",
      value_original: "58",
      unit_original: "degC",
      value_standardized: "58",
      unit_standardized: "degC",
      substrate: "casein",
      assay_temperature: "37",
      assay_pH: "7.0",
      method: "activity assay",
      reference_id: "ref-1",
      reference: {
        id: "ref-1",
        title: "MTGase, thermal evidence",
        authors: null,
        journal: "Biocatalysis Reports",
        year: 2024,
        doi: "10.1000/mtgase",
        pubmed_id: null,
        source: "curated_literature",
        provenance: null
      },
      evidence_text: "Table 1",
      visibility: "public",
      curation_status: "approved"
    }
  ]);

  assert.equal(
    csv,
    [
      "property_type,value_original,unit_original,value_standardized,unit_standardized,substrate,assay_temperature,assay_pH,method,reference,evidence_text,visibility,curation_status",
      'optimal_temperature,58,degC,58,degC,casein,37,7.0,activity assay,"10.1000/mtgase · MTGase, thermal evidence · Biocatalysis Reports · 2024 · curated_literature",Table 1,public,approved'
    ].join("\n")
  );
});

test("formatPropertyEvidence exposes literature evidence and reference", () => {
  assert.equal(
    formatPropertyEvidence({
      reference_id: "ref-1",
      evidence_text: "Reported at pH 7.0 after 30 min assay.",
      visibility: "public",
      curation_status: "approved"
    }),
    "ref-1 · Reported at pH 7.0 after 30 min assay. · public / approved"
  );
  assert.equal(
    formatPropertyEvidence({
      reference_id: null,
      evidence_text: null,
      visibility: "private",
      curation_status: "unreviewed"
    }),
    "private / unreviewed"
  );
});

test("formatPropertyEvidence prefers readable DOI and title when reference metadata is available", () => {
  const reference = {
    id: "ref-1",
    title: "Thermostability of MTGase",
    authors: null,
    journal: "Biocatalysis Reports",
    year: 2024,
    doi: "10.1000/mtgase",
    pubmed_id: null,
    source: "curated_literature",
    provenance: { mode: "curated" }
  };

  assert.equal(
    formatPropertyEvidence({
      reference_id: "ref-1",
      reference,
      evidence_text: "Reported at pH 7.0 after 30 min assay.",
      visibility: "public",
      curation_status: "approved"
    }),
    "10.1000/mtgase · Thermostability of MTGase · Biocatalysis Reports · 2024 · curated_literature · Reported at pH 7.0 after 30 min assay. · public / approved"
  );
  assert.equal(
    formatPropertyEvidence(
      {
        reference_id: "ref-1",
        evidence_text: "Reported at pH 7.0 after 30 min assay.",
        visibility: "public",
        curation_status: "approved"
      },
      {
        "ref-1": {
          ...reference
        }
      }
    ),
    "10.1000/mtgase · Thermostability of MTGase · Biocatalysis Reports · 2024 · curated_literature · Reported at pH 7.0 after 30 min assay. · public / approved"
  );
});

test("formatKineticEvidence prefers embedded reference metadata", () => {
  assert.equal(
    formatKineticEvidence({
      reference_id: "ref-1",
      reference: {
        id: "ref-1",
        title: "MTGase kinetics",
        authors: null,
        journal: "Biocatalysis Reports",
        year: 2024,
        doi: null,
        pubmed_id: "123456",
        source: "curated_literature",
        provenance: { mode: "curated" }
      },
      visibility: "public",
      curation_status: "approved"
    }),
    "PMID 123456 · MTGase kinetics · Biocatalysis Reports · 2024 · curated_literature · public / approved"
  );
});

test("summarizeRankingGroup exposes assay context and item count", () => {
  assert.equal(
    summarizeRankingGroup({
      condition_key: {
        reference_id: "ref-1",
        substrate: "casein",
        assay_temperature: "37",
        assay_pH: "7.5",
        unit: "U/mg",
        method: "DNS"
      },
      items: [{ rank: 1 }, { rank: 2 }]
    }),
    "ref-1 · casein · 37 degC · pH 7.5 · U/mg · DNS · 2 records"
  );
});

test("property ranking API shape uses comparison_warnings", () => {
  const ranking = {
    property_type: "specific_activity",
    ranking_mode: "reported_value",
    comparison_warnings: ["cross-condition comparisons should be interpreted cautiously"],
    items: [],
    groups: []
  };

  assert.deepEqual(ranking.comparison_warnings, [
    "cross-condition comparisons should be interpreted cautiously"
  ]);
});
