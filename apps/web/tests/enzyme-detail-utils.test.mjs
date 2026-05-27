import assert from "node:assert/strict";
import { test } from "node:test";

import {
  buildFamilyComparisonRow,
  formatConditionEvidence,
  buildRealDataRefreshProgress,
  parseEvidenceText,
  formatRealDataRefreshSummary,
  formatReferenceForTable,
  isUserUploadedStructure,
  sortStructuresForDisplay,
  sortLiteratureReferencesForDisplay,
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

test("sortLiteratureReferencesForDisplay keeps newest known papers first", () => {
  const sorted = sortLiteratureReferencesForDisplay([
    { ...referencesById["ref-1"], id: "older", year: 2020 },
    { ...referencesById["ref-1"], id: "unknown", year: null },
    { ...referencesById["ref-1"], id: "newer", year: 2024 }
  ]);

  assert.deepEqual(
    sorted.map((reference) => reference.id),
    ["newer", "older", "unknown"]
  );
});

test("sortStructuresForDisplay keeps RCSB and AlphaFold structures before uploads", () => {
  const uploaded = {
    id: "uploaded-1",
    structure_type: "uploaded_pdb",
    source: "user_upload",
    created_at: "2026-01-01T00:00:00Z"
  };
  const alphafold = {
    id: "alphafold-1",
    structure_type: "alphafold",
    source: "alphafold",
    created_at: "2026-01-02T00:00:00Z"
  };
  const rcsb = {
    id: "rcsb-1",
    structure_type: "pdb",
    source: "rcsb",
    created_at: "2026-01-03T00:00:00Z"
  };

  assert.deepEqual(
    sortStructuresForDisplay([uploaded, alphafold, rcsb]).map((item) => item.id),
    ["rcsb-1", "alphafold-1", "uploaded-1"]
  );
});

test("isUserUploadedStructure only allows uploaded user structures to be deleted", () => {
  assert.equal(isUserUploadedStructure({ structure_type: "uploaded_pdb", source: "user_upload" }), true);
  assert.equal(isUserUploadedStructure({ structure_type: "uploaded_cif", source: "user_upload" }), true);
  assert.equal(isUserUploadedStructure({ structure_type: "alphafold", source: "alphafold" }), false);
  assert.equal(isUserUploadedStructure({ structure_type: "pdb", source: "rcsb" }), false);
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

test("buildRealDataRefreshProgress maps queued and running jobs to progress messages", () => {
  assert.deepEqual(
    buildRealDataRefreshProgress({
      id: "job-1",
      status: "queued",
      job_type: "real_data_refresh",
      parameters_json: { scope: "family" },
      result_summary_json: null,
      error_message: null
    }),
    {
      percent: 15,
      title: "Fetch real data queued",
      detail: "Family real-data refresh job job-1 is waiting for the worker.",
      summary: null,
      warnings: [],
      checkedSources: 0,
      foundRecords: 0,
      notFoundSources: 0,
      processedEnzymes: 0,
      totalEnzymes: 0,
      stage: null,
      candidateArticles: 0,
      articlesScanned: 0,
      filteredArticles: 0,
      relevantArticles: 0,
      extractedRecords: 0,
      candidatePapers: [],
      canPause: true
    }
  );
  assert.deepEqual(
    buildRealDataRefreshProgress({
      id: "job-2",
      status: "running",
      job_type: "real_data_refresh",
      parameters_json: { scope: "enzyme" },
      result_summary_json: {
        created: { references: 1, properties: 1, kinetics: 0, mutations: 0, structures: 0 },
        sources: ["crossref", "europepmc"],
        progress: {
          checked_sources: 2,
          found_records: 2,
          not_found_sources: 0,
          processed_enzymes: 0,
          total_enzymes: 1,
          stage: "extracting candidate literature",
          candidate_articles: 5,
          articles_scanned: 2,
          filtered_articles: 1,
          relevant_articles: 1,
          extracted_records: 2,
          candidate_papers: [
            {
              title: "Characterization of a recombinant cellobiose 2-epimerase",
              source: "europepmc",
              year: 2012,
              doi: "10.1007/s00253-012-4002-5",
              pubmed_id: null,
              relevance_score: 24,
              decision: "extracted",
              reason: "passed relevance filter and produced extractable records",
              extracted_fields: ["optimal_temperature", "optimal_pH"]
            }
          ]
        }
      },
      error_message: null
    }),
    {
      percent: 80,
      title: "Fetching real data",
      detail: "Enzyme real-data refresh job job-2 is collecting external records.",
      summary:
        "Fetched real data: references 1, properties 1, kinetics 0, mutations 0, structures 0. Sources: crossref, europepmc.",
      warnings: [],
      checkedSources: 2,
      foundRecords: 2,
      notFoundSources: 0,
      processedEnzymes: 0,
      totalEnzymes: 1,
      stage: "extracting candidate literature",
      candidateArticles: 5,
      articlesScanned: 2,
      filteredArticles: 1,
      relevantArticles: 1,
      extractedRecords: 2,
      candidatePapers: [
        {
          title: "Characterization of a recombinant cellobiose 2-epimerase",
          source: "europepmc",
          year: 2012,
          doi: "10.1007/s00253-012-4002-5",
          pubmedId: null,
          relevanceScore: 24,
          decision: "extracted",
          reason: "passed relevance filter and produced extractable records",
          extractedFields: ["optimal_temperature", "optimal_pH"]
        }
      ],
      canPause: true
    }
  );
});

test("buildRealDataRefreshProgress reports finished job counts and warnings", () => {
  assert.deepEqual(
    buildRealDataRefreshProgress({
      id: "job-3",
      status: "finished",
      job_type: "real_data_refresh",
      parameters_json: { scope: "enzyme" },
      result_summary_json: {
        created: { references: 2, properties: 3, kinetics: 1, mutations: 0, structures: 1 },
        sources: ["crossref", "europepmc"],
        warnings: ["Semantic Scholar unavailable"]
      },
      error_message: null
    }),
    {
      percent: 100,
      title: "Fetch real data complete",
      detail: "Enzyme real-data refresh job job-3 finished.",
      summary:
        "Fetched real data: references 2, properties 3, kinetics 1, mutations 0, structures 1. Sources: crossref, europepmc.",
      warnings: ["Semantic Scholar unavailable"],
      checkedSources: 0,
      foundRecords: 0,
      notFoundSources: 0,
      processedEnzymes: 0,
      totalEnzymes: 0,
      stage: null,
      candidateArticles: 0,
      articlesScanned: 0,
      filteredArticles: 0,
      relevantArticles: 0,
      extractedRecords: 0,
      candidatePapers: [],
      canPause: false
    }
  );
});

test("buildRealDataRefreshProgress reports failed job error", () => {
  assert.deepEqual(
    buildRealDataRefreshProgress({
      id: "job-4",
      status: "failed",
      job_type: "real_data_refresh",
      parameters_json: { scope: "family" },
      result_summary_json: null,
      error_message: "Europe PMC timed out"
    }),
    {
      percent: 100,
      title: "Fetch real data failed",
      detail: "Europe PMC timed out",
      summary: null,
      warnings: [],
      checkedSources: 0,
      foundRecords: 0,
      notFoundSources: 0,
      processedEnzymes: 0,
      totalEnzymes: 0,
      stage: null,
      candidateArticles: 0,
      articlesScanned: 0,
      filteredArticles: 0,
      relevantArticles: 0,
      extractedRecords: 0,
      candidatePapers: [],
      canPause: false
    }
  );
});

test("buildRealDataRefreshProgress reports paused job progress", () => {
  assert.deepEqual(
    buildRealDataRefreshProgress({
      id: "job-5",
      status: "cancelled",
      job_type: "real_data_refresh",
      parameters_json: {
        scope: "family",
        progress: {
          checked_sources: 4,
          found_records: 2,
          not_found_sources: 2,
          processed_enzymes: 1,
          total_enzymes: 3,
          stage: "cancelled",
          candidate_articles: 4,
          articles_scanned: 3,
          filtered_articles: 1,
          relevant_articles: 2,
          extracted_records: 2,
          candidate_papers: []
        }
      },
      result_summary_json: {
        created: { references: 1, properties: 1, kinetics: 0, mutations: 0, structures: 0 },
        sources: ["crossref"],
        warnings: ["OpenAlex unavailable"]
      },
      error_message: null
    }),
    {
      percent: 100,
      title: "Fetch real data paused",
      detail: "Family real-data refresh job job-5 was paused. Saved records can be reviewed now.",
      summary:
        "Fetched real data: references 1, properties 1, kinetics 0, mutations 0, structures 0. Sources: crossref.",
      warnings: ["OpenAlex unavailable"],
      checkedSources: 4,
      foundRecords: 2,
      notFoundSources: 2,
      processedEnzymes: 1,
      totalEnzymes: 3,
      stage: "cancelled",
      candidateArticles: 4,
      articlesScanned: 3,
      filteredArticles: 1,
      relevantArticles: 2,
      extractedRecords: 2,
      candidatePapers: [],
      canPause: false
    }
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
