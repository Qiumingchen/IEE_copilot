import assert from "node:assert/strict";
import { test } from "node:test";

import {
  canSubmitRejection,
  curatedEvidenceCsvTemplate,
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
      created: { properties: 2, kinetics: 1, mutations: 3 },
      reference_ids: ["ref-1", "ref-2"],
      warnings: []
    }),
    "Created 2 property, 1 kinetic, 3 mutation records from 2 references."
  );
});

test("summarizeCuratedEvidencePreview reports parsed evidence counts", () => {
  assert.equal(
    summarizeCuratedEvidencePreview({
      fields: ["record_type", "property_type"],
      row_count: 4,
      record_counts: { properties: 2, kinetics: 1, mutations: 1 },
      records: [],
      warnings: []
    }),
    "4 rows parsed: 2 property, 1 kinetic, 1 mutation records."
  );
});

test("curatedEvidenceCsvTemplate includes all supported evidence record types", () => {
  assert.equal(curatedEvidenceCsvTemplate.includes("record_type"), true);
  assert.equal(curatedEvidenceCsvTemplate.includes("property,"), true);
  assert.equal(curatedEvidenceCsvTemplate.includes("kinetic,"), true);
  assert.equal(curatedEvidenceCsvTemplate.includes("mutation,"), true);
});
