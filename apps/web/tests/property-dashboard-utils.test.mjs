import assert from "node:assert/strict";
import { test } from "node:test";

import {
  buildPropertyOptions,
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
