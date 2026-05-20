import assert from "node:assert/strict";
import { test } from "node:test";

import {
  buildExperimentImportRequest,
  summarizeExperimentPreview
} from "../app/enzymes/[id]/experiments/experiment-import-utils.ts";

test("buildExperimentImportRequest trims project id and preserves csv text", () => {
  const request = buildExperimentImportRequest(" project-1 ", "variant_name,mutation_string\nWT,WT");

  assert.deepEqual(request, {
    project_id: "project-1",
    csv_text: "variant_name,mutation_string\nWT,WT"
  });
});

test("summarizeExperimentPreview reports rows, records, and fields", () => {
  const summary = summarizeExperimentPreview({
    fields: ["variant_name", "mutation_string", "specific_activity"],
    row_count: 2,
    record_count: 3,
    records: []
  });

  assert.equal(summary, "2 rows, 3 measurements, 3 fields");
});
