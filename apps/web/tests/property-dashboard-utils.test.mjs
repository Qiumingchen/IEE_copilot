import assert from "node:assert/strict";
import { test } from "node:test";

import {
  buildPropertyOptions,
  buildPropertyEvidenceCsv,
  buildKineticEvidenceCsv,
  buildPropertyRankingCsv,
  buildKineticSummary,
  buildPropertyDistribution,
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

test("buildPropertyDistribution summarizes numeric values for charts", () => {
  assert.deepEqual(
    buildPropertyDistribution([
      {
        value_original: "328.15",
        unit_original: "K",
        value_standardized: "55",
        unit_standardized: "degC"
      },
      {
        value_original: "60",
        unit_original: "degC",
        value_standardized: "60",
        unit_standardized: "degC"
      },
      {
        value_original: "about 70",
        unit_original: "degC",
        value_standardized: null,
        unit_standardized: null
      }
    ]),
    {
      count: 2,
      unit: "degC",
      min: 55,
      median: 57.5,
      max: 60,
      bins: [
        { label: "55-56.3", count: 1 },
        { label: "56.3-57.5", count: 0 },
        { label: "57.5-58.8", count: 0 },
        { label: "58.8-60", count: 1 }
      ]
    }
  );
});

test("buildKineticSummary summarizes Km, kcat, and catalytic efficiency", () => {
  assert.deepEqual(
    buildKineticSummary([
      {
        km: "2.1",
        kcat: "31",
        kcat_km: "14.8"
      },
      {
        km: "1.5",
        kcat: "40",
        kcat_km: null
      },
      {
        km: "not reported",
        kcat: null,
        kcat_km: "20"
      }
    ]),
    [
      { label: "Km", count: 2, min: 1.5, median: 1.8, max: 2.1 },
      { label: "kcat", count: 2, min: 31, median: 35.5, max: 40 },
      { label: "kcat/Km", count: 2, min: 14.8, median: 17.4, max: 20 }
    ]
  );
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

test("buildKineticEvidenceCsv exports kinetic parameters and citation fields", () => {
  const csv = buildKineticEvidenceCsv([
    {
      substrate: "CBZ-Gln-Gly",
      km: "2.1",
      kcat: "31",
      kcat_km: "14.8",
      unit_original: "mM; s-1",
      assay_temperature: "37",
      assay_pH: "7.0",
      method: "HPLC assay",
      reference_id: "ref-kinetic",
      reference: {
        id: "ref-kinetic",
        title: "MTGase kinetics",
        authors: null,
        journal: "Enzyme Reports",
        year: 2025,
        doi: null,
        pubmed_id: "123456",
        source: "curated_literature",
        provenance: null
      },
      evidence_text: "Table 2",
      visibility: "public",
      curation_status: "approved"
    }
  ]);

  assert.equal(
    csv,
    [
      "substrate,km,kcat,kcat_km,unit_original,assay_temperature,assay_pH,method,reference,evidence_text,visibility,curation_status",
      "CBZ-Gln-Gly,2.1,31,14.8,mM; s-1,37,7.0,HPLC assay,PMID 123456 · MTGase kinetics · Enzyme Reports · 2025 · curated_literature,Table 2,public,approved"
    ].join("\n")
  );
});

test("buildPropertyRankingCsv exports reported ranking rows", () => {
  const csv = buildPropertyRankingCsv({
    property_type: "specific_activity",
    ranking_mode: "reported_value",
    comparison_warnings: [],
    groups: [],
    items: [
      {
        rank: 1,
        property_record_id: "prop-1",
        enzyme_entry_id: "enzyme-1",
        enzyme_name: "MTGase A",
        organism: "Streptomyces mobaraensis",
        value_original: "120",
        unit_original: "U/mg",
        value_standardized: "120",
        unit_standardized: "U/mg",
        substrate: "casein",
        assay_temperature: "37",
        assay_pH: "7.0",
        method: "activity assay",
        reference_id: "ref-1"
      }
    ]
  });

  assert.equal(
    csv,
    [
      "group_context,rank,enzyme_name,organism,value,substrate,assay_temperature,assay_pH,method,reference_id",
      ",1,MTGase A,Streptomyces mobaraensis,120 U/mg,casein,37,7.0,activity assay,ref-1"
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

test("formatKineticEvidence includes kinetic evidence text", () => {
  assert.equal(
    formatKineticEvidence({
      reference_id: null,
      reference: null,
      evidence_text: "Table 2 reports Km and kcat for CBZ-Gln-Gly.",
      visibility: "public",
      curation_status: "approved"
    }),
    "Table 2 reports Km and kcat for CBZ-Gln-Gly. · public / approved"
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
