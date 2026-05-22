import assert from "node:assert/strict";
import { test } from "node:test";

import {
  buildCuratedEvidenceTemplateCsv,
  buildCuratedEvidenceReviewLinks,
  canSubmitRejection,
  curatedEvidenceCsvTemplate,
  curatedEvidenceCsvUploadAccept,
  curatedEvidenceTemplateFileName,
  formatImportedReference,
  formatPreviewWarnings,
  formatPreviewReference,
  isCuratedEvidenceCsvFileName,
  summarizeCuratedEvidenceFileLoad,
  summarizeCuratedEvidencePreview,
  summarizeCuratedEvidenceImport,
  summarizeVisibilityRequest
} from "../app/curation/curation-utils.ts";

test("summarizeVisibilityRequest combines variant, mutation, and measurement", () => {
  const summary = summarizeVisibilityRequest({
    id: "request-1",
    project_id: "project-1",
    target_type: "user_experiment",
    target_id: "experiment-1",
    requested_visibility: "public",
    status: "pending",
    requested_by: "user-1",
    reviewed_by: null,
    review_comment: null,
    experiment: {
      id: "experiment-1",
      project_id: "project-1",
      enzyme_entry_id: "enzyme-1",
      variant_name: "L10A variant",
      mutation_string: "L10A",
      sequence: null,
      measured_property: "specific_activity",
      measured_value: "125.4",
      unit: "U/mg",
      assay_condition_json: { substrate: "casein" },
      visibility: "private",
      curation_status: "unreviewed",
      created_by: "user-1"
    }
  });

  assert.equal(summary, "L10A variant · L10A · specific_activity 125.4 U/mg");
});

test("canSubmitRejection requires a non-empty review comment", () => {
  assert.equal(canSubmitRejection("   "), false);
  assert.equal(canSubmitRejection("Missing assay condition."), true);
});

test("summarizeCuratedEvidenceImport reports created evidence counts", () => {
  assert.equal(
    summarizeCuratedEvidenceImport({
      created: { properties: 2, kinetics: 1, mutations: 3, expressions: 4 },
      reference_ids: ["ref-1", "ref-2"],
      references: [],
      warnings: []
    }),
    "Created 2 property, 1 kinetic, 3 mutation, 4 expression records from 2 references."
  );
});

test("summarizeCuratedEvidencePreview reports parsed evidence counts", () => {
  assert.equal(
    summarizeCuratedEvidencePreview({
      fields: ["record_type", "property_type"],
      row_count: 4,
      record_counts: { properties: 2, kinetics: 1, mutations: 1, expressions: 3 },
      records: [],
      errors: [],
      valid: true,
      warnings: []
    }),
    "4 rows parsed: 2 property, 1 kinetic, 1 mutation, 3 expression records."
  );
});

test("summarizeCuratedEvidencePreview includes validation error count", () => {
  assert.equal(
    summarizeCuratedEvidencePreview({
      fields: ["record_type"],
      row_count: 2,
      record_counts: { properties: 1, kinetics: 0, mutations: 0 },
      records: [],
      errors: [
        { row_number: 3, field: "mutation_string", message: "invalid mutation format: S2" }
      ],
      warnings: [],
      valid: false
    }),
    "2 rows parsed: 1 property, 0 kinetic, 0 mutation, 0 expression records. 1 validation error."
  );
});

test("summarizeCuratedEvidencePreview includes warning count", () => {
  assert.equal(
    summarizeCuratedEvidencePreview({
      fields: ["record_type"],
      row_count: 2,
      record_counts: { properties: 1, kinetics: 0, mutations: 0 },
      records: [],
      errors: [],
      warnings: ["row 2: no reference identifier supplied"],
      valid: true
    }),
    "2 rows parsed: 1 property, 0 kinetic, 0 mutation, 0 expression records. 1 warning."
  );
});

test("curatedEvidenceCsvTemplate includes all supported evidence record types", () => {
  assert.equal(curatedEvidenceCsvTemplate.includes("record_type"), true);
  assert.equal(curatedEvidenceCsvTemplate.includes("property,"), true);
  assert.equal(curatedEvidenceCsvTemplate.includes("kinetic,"), true);
  assert.equal(curatedEvidenceCsvTemplate.includes("mutation,"), true);
  assert.equal(curatedEvidenceCsvTemplate.includes("expression,"), true);
});

test("buildCuratedEvidenceTemplateCsv returns a downloadable CSV template", () => {
  const csv = buildCuratedEvidenceTemplateCsv();
  const [header, ...rows] = csv.trimEnd().split("\n");
  const columnCount = header.split(",").length;

  assert.equal(curatedEvidenceTemplateFileName, "curated-evidence-template.csv");
  assert.equal(
    header,
    "record_type,property_type,value_original,unit_original,substrate,assay_temperature,assay_pH,method,km,kcat,kcat_km,mutation_string,effect_summary,property_delta_key,property_delta_value,expression_host,vector,expression_level_original,unit_standardized,soluble_expression,doi,pubmed_id,reference_title,journal,year,evidence_text,source"
  );
  assert.equal(rows.length, 4);
  assert.equal(rows.some((row) => row.startsWith("property,")), true);
  assert.equal(rows.some((row) => row.startsWith("kinetic,")), true);
  assert.equal(rows.some((row) => row.startsWith("mutation,")), true);
  assert.equal(rows.some((row) => row.startsWith("expression,")), true);
  assert.deepEqual(
    rows.map((row) => row.split(",").length),
    Array.from({ length: rows.length }, () => columnCount)
  );
  assert.equal(csv.endsWith("\n"), true);
});

test("isCuratedEvidenceCsvFileName accepts csv files only", () => {
  assert.equal(curatedEvidenceCsvUploadAccept, ".csv,text/csv");
  assert.equal(isCuratedEvidenceCsvFileName("curated-evidence.csv"), true);
  assert.equal(isCuratedEvidenceCsvFileName("Curated-Evidence.CSV"), true);
  assert.equal(isCuratedEvidenceCsvFileName("curated-evidence.tsv"), false);
  assert.equal(isCuratedEvidenceCsvFileName("curated-evidence.csv.txt"), false);
});

test("summarizeCuratedEvidenceFileLoad reports the loaded CSV file name", () => {
  assert.equal(
    summarizeCuratedEvidenceFileLoad("curated-evidence.csv"),
    "Loaded curated-evidence.csv into CSV text."
  );
});

test("buildCuratedEvidenceReviewLinks points imported evidence back to enzyme views", () => {
  assert.deepEqual(buildCuratedEvidenceReviewLinks(" enzyme-1 "), [
    { label: "Open enzyme record", href: "/enzymes/enzyme-1" },
    { label: "Review properties", href: "/enzymes/enzyme-1/properties" },
    { label: "Review mutations", href: "/enzymes/enzyme-1/mutations" }
  ]);
  assert.deepEqual(buildCuratedEvidenceReviewLinks("enzyme/with space"), [
    { label: "Open enzyme record", href: "/enzymes/enzyme%2Fwith%20space" },
    { label: "Review properties", href: "/enzymes/enzyme%2Fwith%20space/properties" },
    { label: "Review mutations", href: "/enzymes/enzyme%2Fwith%20space/mutations" }
  ]);
  assert.deepEqual(buildCuratedEvidenceReviewLinks("   "), []);
});

test("formatPreviewWarnings removes empty curated evidence warnings", () => {
  assert.deepEqual(
    formatPreviewWarnings(["row 2: no reference identifier supplied", " ", "row 4: reference will be created"]),
    ["row 2: no reference identifier supplied", "row 4: reference will be created"]
  );
});

test("formatPreviewReference includes the reference match mode", () => {
  assert.equal(
    formatPreviewReference({
      row_number: 2,
      record_type: "property",
      summary: "optimal_pH 7.0 pH",
      reference_key: "10.1000/mode",
      reference_match_mode: "doi",
      evidence_text: "Optimum pH reported"
    }),
    "10.1000/mode · DOI"
  );
  assert.equal(
    formatPreviewReference({
      row_number: 3,
      record_type: "mutation",
      summary: "S2P",
      reference_key: "title mode paper:2022:curated_literature",
      reference_match_mode: "title_year_source",
      evidence_text: "S2P increased half-life"
    }),
    "title mode paper:2022:curated_literature · title/year/source"
  );
});

test("formatImportedReference shows DOI title and source", () => {
  assert.equal(
    formatImportedReference({
      id: "ref-1",
      title: "Curated MTGase paper",
      authors: null,
      journal: "Biocatalysis Reports",
      year: 2024,
      doi: "10.1000/curated",
      pubmed_id: null,
      source: "curated_literature",
      provenance: { mode: "curated" }
    }),
    "10.1000/curated · Curated MTGase paper · curated_literature"
  );
});

test("formatImportedReference normalizes DOI URLs for display", () => {
  assert.equal(
    formatImportedReference({
      id: "ref-1",
      title: "DOI URL paper",
      authors: null,
      journal: null,
      year: null,
      doi: "https://doi.org/10.1000/MixedCase",
      pubmed_id: null,
      source: "curated_literature",
      provenance: null
    }),
    "10.1000/mixedcase · DOI URL paper · curated_literature"
  );
});

test("formatImportedReference normalizes PubMed IDs for display", () => {
  assert.equal(
    formatImportedReference({
      id: "ref-1",
      title: "PMID paper",
      authors: null,
      journal: null,
      year: null,
      doi: null,
      pubmed_id: "PMID: 123456",
      source: "curated_literature",
      provenance: null
    }),
    "PMID 123456 · PMID paper · curated_literature"
  );
});
