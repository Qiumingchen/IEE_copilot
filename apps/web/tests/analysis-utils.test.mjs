import assert from "node:assert/strict";
import { test } from "node:test";

import {
  buildConservationDownloadJson,
  filterConservationSites,
  getConservationSites,
  getMutationRecommendationCandidates,
  getRosettaDdgResults,
  getRosettaDdgRunViews
} from "../app/enzymes/[id]/analysis/analysis-utils.ts";

const conservationContent = {
  artifact_id: "artifact-1",
  artifact_type: "conservation_profile",
  content_type: "application/json",
  object_key: "analysis-jobs/job-1/conservation-profile.json",
  content_text: null,
  content_json: {
    sequence_count: 3,
    sites: [
      {
        query_position: 1,
        wildtype_residue: "A",
        shannon_entropy: 0,
        wildtype_frequency: 1,
        conservation_category: "highly_conserved"
      },
      {
        query_position: 2,
        wildtype_residue: "C",
        shannon_entropy: 0.918,
        wildtype_frequency: 0.667,
        conservation_category: "moderately_conserved"
      }
    ]
  }
};

test("filters conservation sites by selected category", () => {
  const sites = getConservationSites(conservationContent);

  assert.equal(filterConservationSites(sites, "all").length, 2);
  assert.deepEqual(
    filterConservationSites(sites, "highly_conserved").map((site) => site.query_position),
    [1]
  );
  assert.deepEqual(
    filterConservationSites(sites, "variable").map((site) => site.query_position),
    []
  );
});

test("builds conservation download json with artifact metadata and sites", () => {
  const sites = getConservationSites(conservationContent);
  const payload = JSON.parse(buildConservationDownloadJson(conservationContent, sites));

  assert.equal(payload.artifact_id, "artifact-1");
  assert.equal(payload.object_key, "analysis-jobs/job-1/conservation-profile.json");
  assert.equal(payload.sites.length, 2);
  assert.equal(payload.sites[1].conservation_category, "moderately_conserved");
});

test("extracts mutation recommendation candidates from artifact content", () => {
  const content = {
    artifact_id: "artifact-2",
    artifact_type: "mutation_recommendations",
    content_type: "application/json",
    object_key: "analysis-jobs/job-2/mutation-recommendations.json",
    content_text: null,
    content_json: {
      candidates: [
        {
          query_position: 10,
          wildtype_residue: "L",
          conservation_category: "variable",
          priority_score: 1.8,
          suggested_mutations: ["L10A", "L10V", "L10S"],
          rationale: "variable site"
        }
      ]
    }
  };

  assert.deepEqual(getMutationRecommendationCandidates(content), [
    {
      query_position: 10,
      wildtype_residue: "L",
      conservation_category: "variable",
      priority_score: 1.8,
      suggested_mutations: ["L10A", "L10V", "L10S"],
      rationale: "variable site"
    }
  ]);
});

test("extracts rosetta ddg results from artifact content", () => {
  const content = {
    artifact_id: "artifact-3",
    artifact_type: "rosetta_ddg",
    content_type: "application/json",
    object_key: "analysis-jobs/job-3/rosetta-ddg.json",
    content_text: null,
    content_json: {
      mutation_string: "L10A",
      mutation_file: "L 10 A",
      ddg_kcal_per_mol: -0.6,
      interpretation: "stabilizing",
      structure_id: "structure-1",
      runner: "mock_rosetta_ddg"
    }
  };

  assert.deepEqual(getRosettaDdgResults(content), [
    {
      mutation_string: "L10A",
      mutation_file: "L 10 A",
      ddg_kcal_per_mol: -0.6,
      interpretation: "stabilizing",
      structure_id: "structure-1",
      runner: "mock_rosetta_ddg"
    }
  ]);
});

test("builds rosetta ddg run views with status and error messages", () => {
  const jobs = [
    {
      id: "job-failed",
      enzyme_entry_id: "enzyme-1",
      job_type: "rosetta_ddg",
      status: "failed",
      parameters_json: { mutation_string: "G2A" },
      result_summary_json: null,
      error_message: "expected G at position 2 but found C",
      created_at: "2026-05-19T10:00:00",
      finished_at: "2026-05-19T10:00:05"
    },
    {
      id: "job-finished",
      enzyme_entry_id: "enzyme-1",
      job_type: "rosetta_ddg",
      status: "finished",
      parameters_json: { mutation_string: "L10A" },
      result_summary_json: {
        mutation_string: "L10A",
        mutation_file: "L 10 A",
        ddg_kcal_per_mol: -0.6,
        interpretation: "stabilizing",
        runner: "mock_rosetta_ddg"
      },
      error_message: null,
      created_at: "2026-05-19T10:01:00",
      finished_at: "2026-05-19T10:01:05"
    },
    {
      id: "job-other",
      enzyme_entry_id: "enzyme-1",
      job_type: "msa",
      status: "finished",
      parameters_json: null,
      result_summary_json: null,
      error_message: null,
      created_at: "2026-05-19T10:02:00",
      finished_at: "2026-05-19T10:02:05"
    }
  ];

  assert.deepEqual(getRosettaDdgRunViews(jobs, "enzyme-1"), [
    {
      job_id: "job-failed",
      status: "failed",
      mutation_string: "G2A",
      mutation_file: "-",
      ddg_kcal_per_mol: "-",
      interpretation: "-",
      runner: "-",
      error_message: "expected G at position 2 but found C",
      can_retry: true,
      created_at: "2026-05-19T10:00:00",
      finished_at: "2026-05-19T10:00:05"
    },
    {
      job_id: "job-finished",
      status: "finished",
      mutation_string: "L10A",
      mutation_file: "L 10 A",
      ddg_kcal_per_mol: -0.6,
      interpretation: "stabilizing",
      runner: "mock_rosetta_ddg",
      error_message: "-",
      can_retry: false,
      created_at: "2026-05-19T10:01:00",
      finished_at: "2026-05-19T10:01:05"
    }
  ]);
});
