import assert from "node:assert/strict";
import { test } from "node:test";

import {
  buildMutationLibraryWorkbookBytes,
  buildLibraryDesignParameters,
  buildConservationDownloadJson,
  filterConservationSites,
  getConservationSites,
  getMutationLibrary,
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
          scored_suggestions: [
            {
              mutation_string: "L10A",
              total_score: 3.2,
              components: [
                {
                  name: "rosetta_stability",
                  value: 0.4,
                  weight: 2,
                  contribution: 0.8,
                  rationale: "stabilizing prediction"
                }
              ],
              risk_summary: ["medium_solubility_risk"],
              parsed_mutations: [{ wildtype: "L", position: 10, mutant: "A" }]
            }
          ],
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
      scored_suggestions: [
        {
          mutation_string: "L10A",
          total_score: 3.2,
          components: [
            {
              name: "rosetta_stability",
              value: 0.4,
              weight: 2,
              contribution: 0.8,
              rationale: "stabilizing prediction"
            }
          ],
          risk_summary: ["medium_solubility_risk"],
          parsed_mutations: [{ wildtype: "L", position: 10, mutant: "A" }]
        }
      ],
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

test("extracts mutation library variants and plate layout from artifact content", () => {
  const content = {
    artifact_id: "artifact-4",
    artifact_type: "mutation_library",
    content_type: "application/json",
    object_key: "analysis-jobs/job-4/mutation-library.json",
    content_text: null,
    content_json: {
      library_size: 24,
      plate_format: 96,
      variant_count: 1,
      variants: [
        {
          variant_id: "VAR-L10A-F12A",
          mutation_string: "L10A/F12A",
          order: 2,
          score: 2.1,
          risk_flags: ["ddg_destabilizing_member"],
          reasons: ["test reason"],
          member_scores: [
            { mutation_string: "L10A", total_score: 3.4 },
            { mutation_string: "F12A", total_score: 2.2 }
          ]
        }
      ],
      plate_layout: [
        {
          well: "A1",
          variant_id: "WT",
          mutation_string: "WT",
          role: "wt_control",
          score: null,
          risk_flags: []
        }
      ],
      csv_text: "well,variant_id,mutation_string,role,score,risk_flags"
    }
  };

  assert.deepEqual(getMutationLibrary(content), {
    library_size: 24,
    plate_format: 96,
    variant_count: 1,
    variants: [
      {
        variant_id: "VAR-L10A-F12A",
        mutation_string: "L10A/F12A",
        order: 2,
        score: 2.1,
        risk_flags: ["ddg_destabilizing_member"],
        reasons: ["test reason"],
        member_scores: [
          { mutation_string: "L10A", total_score: 3.4 },
          { mutation_string: "F12A", total_score: 2.2 }
        ]
      }
    ],
    plate_layout: [
      {
        well: "A1",
        variant_id: "WT",
        mutation_string: "WT",
        role: "wt_control",
        score: "-",
        risk_flags: []
      }
    ],
    csv_text: "well,variant_id,mutation_string,role,score,risk_flags"
  });
});

test("builds mutation library design parameters from selected controls", () => {
  assert.deepEqual(buildLibraryDesignParameters(384, 3, 384), {
    library_size: 384,
    max_order: 3,
    plate_format: 384
  });
});

test("builds xlsx workbook bytes for mutation library export", () => {
  const workbookBytes = buildMutationLibraryWorkbookBytes({
    library_size: 24,
    plate_format: 96,
    variant_count: 1,
    variants: [
      {
        variant_id: "VAR-L10A-F12A",
        mutation_string: "L10A/F12A",
        order: 2,
        score: 2.1,
        risk_flags: ["ddg_destabilizing_member"],
        reasons: ["test reason"],
        member_scores: [
          { mutation_string: "L10A", total_score: 3.4 },
          { mutation_string: "F12A", total_score: 2.2 }
        ]
      }
    ],
    plate_layout: [
      {
        well: "A1",
        variant_id: "WT",
        mutation_string: "WT",
        role: "wt_control",
        score: "-",
        risk_flags: []
      }
    ],
    csv_text: "well,variant_id,mutation_string,role,score,risk_flags"
  });

  assert.equal(workbookBytes[0], 0x50);
  assert.equal(workbookBytes[1], 0x4b);
  const workbookText = new TextDecoder().decode(workbookBytes);
  assert.match(workbookText, /\[Content_Types\]\.xml/);
  assert.match(workbookText, /xl\/worksheets\/sheet1\.xml/);
  assert.match(workbookText, /L10A\/F12A/);
  assert.match(workbookText, /L10A: 3\.4/);
});
