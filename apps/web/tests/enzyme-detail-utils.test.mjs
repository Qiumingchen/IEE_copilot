import assert from "node:assert/strict";
import { test } from "node:test";

import {
  buildFamilyComparisonRow,
  formatConditionEvidence,
  parseEvidenceText,
  formatRealDataRefreshSummary,
  formatReferenceForTable,
  formatVisibilityStatus,
  overviewTableEmptyLabel,
  shouldShowOverviewTable
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

test("parseEvidenceText separates source metadata from extracted evidence sentence", () => {
  assert.deepEqual(
    parseEvidenceText(
      "Food Enzyme Reports 2021 doi:10.1000/full-text-enzyme | Evidence quality: literature sentence | Evidence: The enzyme showed optimum temperature at 55 degC"
    ),
    {
      source: "Food Enzyme Reports 2021 doi:10.1000/full-text-enzyme",
      quality: "literature sentence",
      excerpt: "The enzyme showed optimum temperature at 55 degC"
    }
  );
  assert.deepEqual(parseEvidenceText("SABIO-RK EntryID 12345 pmid:28193333"), {
    source: "SABIO-RK EntryID 12345 pmid:28193333",
    quality: null,
    excerpt: null
  });
  assert.deepEqual(parseEvidenceText(null), { source: "-", quality: null, excerpt: null });
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

test("buildFamilyComparisonRow formats selected property metrics", () => {
  const row = buildFamilyComparisonRow(
    {
      id: "enzyme-1",
      family_id: "family-1",
      family_name: "TGase",
      name: "Protein-glutamine gamma-glutamyltransferase",
      organism: "Streptomyces mobaraensis",
      ec_number: "2.3.2.13",
      uniprot_id: "P81453",
      pdb_id: "1IU4",
      alphafold_id: "P81453",
      source: "uniprot",
      uniprot_reviewed: true,
      optimal_temperature: 50,
      specific_activity: 1200,
      record_counts: {
        properties: 2,
        kinetics: 1,
        mutations: 0,
        structures: 1,
        expression: 0
      }
    },
    {
      properties: [
        {
          property_type: "optimal_temperature",
          value_original: "55",
          unit_original: "degC",
          value_standardized: "55",
          unit_standardized: "degC"
        },
        {
          property_type: "optimal_pH",
          value_original: "7.0",
          unit_original: "pH",
          value_standardized: "7.0",
          unit_standardized: "pH"
        },
        {
          property_type: "specific_activity",
          value_original: "120 U/mg",
          unit_original: "U/mg",
          value_standardized: "120",
          unit_standardized: "U/mg"
        }
      ],
      kinetics: [{ kcat: "41 s^-1", km: null, kcat_km: null }]
    },
    ["optimal_temperature", "optimal_pH", "specific_activity", "kcat"]
  );

  assert.deepEqual(row.values, {
    optimal_temperature: "55 degC",
    optimal_pH: "7.0 pH",
    specific_activity: "120 U/mg",
    kcat: "41 s^-1"
  });
});

test("buildFamilyComparisonRow reports Not found for missing comparison metrics", () => {
  const row = buildFamilyComparisonRow(
    {
      id: "enzyme-2",
      family_id: "family-1",
      family_name: "TGase",
      name: "Protein-glutamine gamma-glutamyltransferase",
      organism: "Bacillus subtilis",
      ec_number: "2.3.2.13",
      uniprot_id: "Q00000",
      pdb_id: null,
      alphafold_id: null,
      source: "uniprot",
      uniprot_reviewed: false,
      optimal_temperature: null,
      specific_activity: null,
      record_counts: {
        properties: 0,
        kinetics: 0,
        mutations: 0,
        structures: 0,
        expression: 0
      }
    },
    { properties: [], kinetics: [] },
    ["optimal_temperature", "optimal_pH", "specific_activity", "kcat"]
  );

  assert.deepEqual(row.values, {
    optimal_temperature: "Not found",
    optimal_pH: "Not found",
    specific_activity: "Not found",
    kcat: "Not found"
  });
});

test("overview table empty-state rules keep properties visible and hide kinetics or expression", () => {
  assert.equal(shouldShowOverviewTable("properties", 0), true);
  assert.equal(overviewTableEmptyLabel("properties"), "not found");

  assert.equal(shouldShowOverviewTable("kinetics", 0), false);
  assert.equal(shouldShowOverviewTable("expression", 0), false);

  assert.equal(shouldShowOverviewTable("kinetics", 1), true);
  assert.equal(shouldShowOverviewTable("expression", 1), true);
});
