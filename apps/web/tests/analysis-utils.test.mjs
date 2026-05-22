import assert from "node:assert/strict";
import { test } from "node:test";

import {
  buildConservationJobParameters,
  buildHomologCsv,
  buildHomologFasta,
  buildMsaJobParameters,
  buildMutationRecommendationJobParameters,
  buildMsaDownloadFasta,
  buildRosettaDdgJobParameters,
  buildMutationLibraryWorkbookBytes,
  buildLibraryDesignParameters,
  buildConservationDownloadJson,
  formatAnalysisArtifactSource,
  buildAnalysisArtifactLineageJson,
  buildAnalysisRunManifestJson,
  filterConservationSites,
  getConservationSites,
  getConservationArtifactOptions,
  getArtifactRunnerLabel,
  getHomologDiagnostics,
  getHomologArtifactOptions,
  getMsaArtifactOptions,
  getMsaRecords,
  getMutationLibrary,
  getRecommendationArtifactOptions,
  getMutationRecommendationCandidates,
  getRosettaDdgResults,
  getRosettaDdgRunViews,
  getStructureContextOptions
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

test("formats homolog filter diagnostics from artifact content", () => {
  const diagnostics = getHomologDiagnostics({
    artifact_id: "artifact-homologs",
    artifact_type: "homolog_sequences",
    content_type: "application/json",
    object_key: "analysis-jobs/job-homologs/homolog-sequences.json",
    content_text: null,
    content_json: {
      diagnostics: {
        candidate_count: 25,
        scored_count: 25,
        passed_identity_count: 6,
        filtered_identity_count: 19,
        passed_coverage_count: 2,
        filtered_coverage_count: 4,
        deduplicated_count: 2,
        duplicate_count: 0,
        returned_count: 2,
        max_sequences: 25
      }
    }
  });

  assert.deepEqual(diagnostics, {
    candidate_count: 25,
    scored_count: 25,
    passed_identity_count: 6,
    filtered_identity_count: 19,
    passed_coverage_count: 2,
    filtered_coverage_count: 4,
    deduplicated_count: 2,
    duplicate_count: 0,
    returned_count: 2,
    max_sequences: 25,
    summary: "Fetched 25 candidates -> scored 25 -> identity pass 6 -> coverage pass 2 -> returned 2"
  });
});

test("builds homolog FASTA export from artifact content", () => {
  const content = {
    artifact_id: "artifact-homologs",
    artifact_type: "homolog_sequences",
    content_type: "application/json",
    object_key: "analysis-jobs/job-homologs/homolog-sequences.json",
    content_text: null,
    content_json: {
      homologs: [
        {
          accession: "A0A1",
          name: "Microbial transglutaminase",
          organism: "Streptomyces testensis",
          identity: 0.8123,
          coverage: 1,
          sequence: "ACDEFGHIKL"
        },
        {
          accession: "B0B2",
          name: "Candidate, quoted",
          organism: null,
          identity: 0.7,
          coverage: 0.9,
          sequence: "MNOP"
        }
      ]
    }
  };

  assert.equal(
    buildHomologFasta(content),
    [
      ">A0A1 Microbial transglutaminase [Streptomyces testensis] identity=81.2% coverage=100.0%",
      "ACDEFGHIKL",
      ">B0B2 Candidate, quoted identity=70.0% coverage=90.0%",
      "MNOP"
    ].join("\n")
  );
});

test("builds homolog CSV export from artifact content", () => {
  const content = {
    artifact_id: "artifact-homologs",
    artifact_type: "homolog_sequences",
    content_type: "application/json",
    object_key: "analysis-jobs/job-homologs/homolog-sequences.json",
    content_text: null,
    content_json: {
      homologs: [
        {
          accession: "A0A1",
          name: "Microbial transglutaminase",
          organism: "Streptomyces testensis",
          identity: 0.8123,
          coverage: 1,
          source: "uniprot",
          sequence: "ACDEFGHIKL"
        },
        {
          accession: "B0B2",
          name: "Candidate, quoted",
          organism: "",
          identity: 0.7,
          coverage: 0.9,
          source: "uniprot",
          sequence: "MNOP"
        }
      ]
    }
  };

  assert.equal(
    buildHomologCsv(content),
    [
      "accession,name,organism,identity,coverage,source,sequence_length,sequence",
      "A0A1,Microbial transglutaminase,Streptomyces testensis,81.2%,100.0%,uniprot,10,ACDEFGHIKL",
      'B0B2,"Candidate, quoted",,70.0%,90.0%,uniprot,4,MNOP'
    ].join("\n")
  );
});

test("extracts MSA records and builds FASTA download text", () => {
  const content = {
    artifact_id: "artifact-msa",
    artifact_type: "msa",
    content_type: "text/x-fasta",
    object_key: "analysis-jobs/job-msa/msa.fasta",
    content_text: ">query\nACD-EF\n>A0A1\nA-DGEF\n",
    content_json: {}
  };

  assert.deepEqual(getMsaRecords(content), [
    {
      identifier: "query",
      aligned_sequence: "ACD-EF",
      sequence_length: 6,
      gap_count: 1
    },
    {
      identifier: "A0A1",
      aligned_sequence: "A-DGEF",
      sequence_length: 6,
      gap_count: 1
    }
  ]);
  assert.equal(buildMsaDownloadFasta(content), ">query\nACD-EF\n>A0A1\nA-DGEF\n");
});

test("builds MSA input parameters from selected homolog source", () => {
  assert.equal(buildMsaJobParameters("latest", "artifact-1", ">a\nAAAA\n"), undefined);
  assert.deepEqual(buildMsaJobParameters("artifact", "artifact-1", ""), {
    homolog_artifact_id: "artifact-1"
  });
  assert.deepEqual(buildMsaJobParameters("custom_fasta", "", ">a\nAAAA\n"), {
    custom_fasta: ">a\nAAAA\n"
  });
});

test("builds homolog artifact options for MSA selection", () => {
  const options = getHomologArtifactOptions([
    {
      id: "artifact-1",
      enzyme_entry_id: "enzyme-1",
      job_id: "job-1",
      job_status: "finished",
      artifact_type: "homolog_sequences",
      bucket: "iee-artifacts",
      object_key: "analysis-jobs/job-1/homolog-sequences.json",
      checksum: null,
      content_type: "application/json",
      size_bytes: 100,
      source: "worker",
      visibility: "private",
      created_at: "2026-05-21T10:00:00",
      result_summary_json: {
        homolog_count: 2,
        runner: { provider: "uniprot", mode: "real" }
      }
    },
    {
      id: "artifact-2",
      enzyme_entry_id: "enzyme-1",
      job_id: "job-2",
      job_status: "finished",
      artifact_type: "msa",
      bucket: "iee-artifacts",
      object_key: "analysis-jobs/job-2/msa.fasta",
      checksum: null,
      content_type: "text/x-fasta",
      size_bytes: 100,
      source: "worker",
      visibility: "private",
      created_at: "2026-05-21T11:00:00",
      result_summary_json: {}
    }
  ]);

  assert.deepEqual(options, [
    {
      id: "artifact-1",
      label: "2026-05-21T10:00:00 | 2 hits | uniprot real"
    }
  ]);
});

test("builds conservation input parameters from selected MSA source", () => {
  assert.equal(buildConservationJobParameters("latest", "artifact-msa"), undefined);
  assert.deepEqual(buildConservationJobParameters("artifact", "artifact-msa"), {
    msa_artifact_id: "artifact-msa"
  });
});

test("builds MSA artifact options for conservation selection", () => {
  const options = getMsaArtifactOptions([
    {
      id: "artifact-1",
      enzyme_entry_id: "enzyme-1",
      job_id: "job-1",
      job_status: "finished",
      artifact_type: "msa",
      bucket: "iee-artifacts",
      object_key: "analysis-jobs/job-1/msa.fasta",
      checksum: null,
      content_type: "text/x-fasta",
      size_bytes: 100,
      source: "worker",
      visibility: "private",
      created_at: "2026-05-21T10:00:00",
      result_summary_json: {
        sequence_count: 3,
        alignment_length: 120,
        runner: { provider: "mafft", mode: "fallback" }
      }
    },
    {
      id: "artifact-2",
      enzyme_entry_id: "enzyme-1",
      job_id: "job-2",
      job_status: "finished",
      artifact_type: "homolog_sequences",
      bucket: "iee-artifacts",
      object_key: "analysis-jobs/job-2/homolog-sequences.json",
      checksum: null,
      content_type: "application/json",
      size_bytes: 100,
      source: "worker",
      visibility: "private",
      created_at: "2026-05-21T11:00:00",
      result_summary_json: {}
    }
  ]);

  assert.deepEqual(options, [
    {
      id: "artifact-1",
      label: "2026-05-21T10:00:00 | 3 seqs | 120 aa | mafft fallback"
    }
  ]);
});

test("builds mutation recommendation parameters from selected conservation source", () => {
  assert.equal(buildMutationRecommendationJobParameters("latest", "artifact-conservation"), undefined);
  assert.deepEqual(buildMutationRecommendationJobParameters("artifact", "artifact-conservation"), {
    conservation_artifact_id: "artifact-conservation"
  });
});

test("builds conservation artifact options for mutation recommendation selection", () => {
  const options = getConservationArtifactOptions([
    {
      id: "artifact-1",
      enzyme_entry_id: "enzyme-1",
      job_id: "job-1",
      job_status: "finished",
      artifact_type: "conservation_profile",
      bucket: "iee-artifacts",
      object_key: "analysis-jobs/job-1/conservation-profile.json",
      checksum: null,
      content_type: "application/json",
      size_bytes: 100,
      source: "worker",
      visibility: "private",
      created_at: "2026-05-21T10:00:00",
      result_summary_json: {
        site_count: 10,
        sequence_count: 3
      }
    },
    {
      id: "artifact-2",
      enzyme_entry_id: "enzyme-1",
      job_id: "job-2",
      job_status: "finished",
      artifact_type: "msa",
      bucket: "iee-artifacts",
      object_key: "analysis-jobs/job-2/msa.fasta",
      checksum: null,
      content_type: "text/x-fasta",
      size_bytes: 100,
      source: "worker",
      visibility: "private",
      created_at: "2026-05-21T11:00:00",
      result_summary_json: {}
    }
  ]);

  assert.deepEqual(options, [
    {
      id: "artifact-1",
      label: "2026-05-21T10:00:00 | 10 sites | 3 seqs"
    }
  ]);
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
      runner: {
        provider: "rosetta",
        mode: "fallback",
        warning: "Rosetta runner not configured; placeholder ddG used."
      }
    }
  };

  assert.deepEqual(getRosettaDdgResults(content), [
    {
      mutation_string: "L10A",
      mutation_file: "L 10 A",
      ddg_kcal_per_mol: -0.6,
      interpretation: "stabilizing",
      structure_id: "structure-1",
      runner: "rosetta fallback"
    }
  ]);
});

test("builds Rosetta ddG parameters with selected structure context", () => {
  assert.deepEqual(buildRosettaDdgJobParameters("L10A", "structure-1"), {
    mutation_string: "L10A",
    source: "hotspot_recommendation",
    structure_id: "structure-1"
  });

  assert.deepEqual(buildRosettaDdgJobParameters("L10A", ""), {
    mutation_string: "L10A",
    source: "hotspot_recommendation"
  });
});

test("builds structure context options for Rosetta ddG selection", () => {
  const structures = [
    {
      id: "structure-apo",
      structure_type: "uploaded_pdb",
      complex_state: "apo",
      pdb_id: null,
      artifact: { object_key: "structures/apo.pdb" }
    },
    {
      id: "structure-complex",
      structure_type: "uploaded_pdb",
      complex_state: "enzyme_substrate_complex",
      pdb_id: null,
      artifact: { object_key: "structures/complex.pdb" }
    }
  ];

  assert.deepEqual(getStructureContextOptions(structures, "structure-complex"), {
    selectedStructureId: "structure-complex",
    options: [
      {
        id: "structure-apo",
        label: "uploaded_pdb | apo | structures/apo.pdb"
      },
      {
        id: "structure-complex",
        label: "uploaded_pdb | enzyme_substrate_complex | structures/complex.pdb"
      }
    ]
  });

  assert.deepEqual(getStructureContextOptions(structures, "missing-structure").selectedStructureId, "structure-apo");
});

test("formats fallback artifact runner labels", () => {
  const label = getArtifactRunnerLabel({
    content_json: {
      runner: {
        provider: "mafft",
        mode: "fallback",
        warning: "MAFFT executable not configured; mock alignment used."
      }
    }
  });

  assert.equal(label.text, "mafft fallback");
  assert.equal(label.warning, "MAFFT executable not configured; mock alignment used.");
});

test("formats artifact input source lineage from summaries", () => {
  assert.equal(
    formatAnalysisArtifactSource({
      result_summary_json: {
        homolog_source: {
          type: "homolog_artifact",
          artifact_id: "homolog-artifact-1",
          sequence_count: 12
        }
      }
    }),
    "homolog_artifact | 12 seqs | homolog-artifact-1"
  );
  assert.equal(
    formatAnalysisArtifactSource({
      result_summary_json: {
        msa_source: {
          type: "latest_msa_artifact",
          sequence_count: 3
        }
      }
    }),
    "latest_msa_artifact | 3 seqs"
  );
  assert.equal(
    formatAnalysisArtifactSource({
      result_summary_json: {
        conservation_source: {
          type: "conservation_artifact",
          artifact_id: "conservation-artifact-1",
          site_count: 20
        }
      }
    }),
    "conservation_artifact | 20 sites | conservation-artifact-1"
  );
  assert.equal(
    formatAnalysisArtifactSource({
      result_summary_json: {
        recommendation_source: {
          type: "recommendation_artifact",
          artifact_id: "recommendation-artifact-1",
          candidate_count: 4
        }
      }
    }),
    "recommendation_artifact | 4 candidates | recommendation-artifact-1"
  );
  assert.equal(formatAnalysisArtifactSource({ result_summary_json: null }), "-");
});

test("builds artifact lineage json for export", () => {
  const payload = JSON.parse(buildAnalysisArtifactLineageJson({
    id: "artifact-1",
    enzyme_entry_id: "enzyme-1",
    job_id: "job-1",
    job_status: "finished",
    artifact_type: "msa",
    bucket: "iee-artifacts",
    object_key: "analysis-jobs/job-1/msa.fasta",
    checksum: "abc123",
    content_type: "text/x-fasta",
    size_bytes: 120,
    source: "worker",
    visibility: "private",
    created_at: "2026-05-21T10:00:00",
    result_summary_json: {
      sequence_count: 3,
      alignment_length: 120,
      runner: { provider: "mafft", mode: "fallback" },
      homolog_source: {
        type: "homolog_artifact",
        artifact_id: "homolog-artifact-1",
        sequence_count: 2
      }
    }
  }));

  assert.equal(payload.artifact.id, "artifact-1");
  assert.equal(payload.artifact.object_key, "analysis-jobs/job-1/msa.fasta");
  assert.equal(payload.input_source.label, "homolog_artifact | 2 seqs | homolog-artifact-1");
  assert.deepEqual(payload.runner, { provider: "mafft", mode: "fallback" });
  assert.equal(payload.summary.sequence_count, 3);
});

test("builds analysis run manifest json for export", () => {
  const payload = JSON.parse(buildAnalysisRunManifestJson(
    "enzyme-1",
    [
      {
        id: "artifact-1",
        enzyme_entry_id: "enzyme-1",
        job_id: "job-1",
        job_status: "finished",
        artifact_type: "homolog_sequences",
        bucket: "iee-artifacts",
        object_key: "analysis-jobs/job-1/homolog-sequences.json",
        checksum: "hash-1",
        content_type: "application/json",
        size_bytes: 120,
        source: "worker",
        visibility: "private",
        created_at: "2026-05-21T10:00:00",
        result_summary_json: {
          homolog_count: 2,
          runner: { provider: "uniprot", mode: "real" }
        }
      },
      {
        id: "artifact-2",
        enzyme_entry_id: "enzyme-1",
        job_id: "job-2",
        job_status: "finished",
        artifact_type: "msa",
        bucket: "iee-artifacts",
        object_key: "analysis-jobs/job-2/msa.fasta",
        checksum: "hash-2",
        content_type: "text/x-fasta",
        size_bytes: 80,
        source: "worker",
        visibility: "private",
        created_at: "2026-05-21T10:05:00",
        result_summary_json: {
          sequence_count: 3,
          homolog_source: { type: "latest_homolog_artifact", sequence_count: 2 }
        }
      }
    ],
    "2026-05-21T12:00:00"
  ));

  assert.equal(payload.enzyme_entry_id, "enzyme-1");
  assert.equal(payload.generated_at, "2026-05-21T12:00:00");
  assert.deepEqual(payload.artifact_counts, { homolog_sequences: 1, msa: 1 });
  assert.equal(payload.artifacts.length, 2);
  assert.equal(payload.artifacts[1].input_source.label, "latest_homolog_artifact | 2 seqs");
});

test("builds rosetta ddg run views with status and error messages", () => {
  const jobs = [
    {
      id: "job-failed",
      enzyme_entry_id: "enzyme-1",
      job_type: "rosetta_ddg",
      status: "failed",
      parameters_json: { mutation_string: "G2A", structure_id: "structure-failed" },
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
        structure_id: "structure-finished",
        runner: {
          provider: "rosetta",
          mode: "fallback"
        }
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
      structure_id: "structure-failed",
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
      structure_id: "structure-finished",
      mutation_file: "L 10 A",
      ddg_kcal_per_mol: -0.6,
      interpretation: "stabilizing",
      runner: "rosetta fallback",
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
  assert.deepEqual(buildLibraryDesignParameters(384, 3, 384, "latest", "recommendation-1"), {
    library_size: 384,
    max_order: 3,
    plate_format: 384
  });
  assert.deepEqual(buildLibraryDesignParameters(48, 2, 96, "artifact", "recommendation-1"), {
    library_size: 48,
    max_order: 2,
    plate_format: 96,
    recommendation_artifact_id: "recommendation-1"
  });
});

test("builds recommendation artifact options for mutation library selection", () => {
  const options = getRecommendationArtifactOptions([
    {
      id: "artifact-1",
      enzyme_entry_id: "enzyme-1",
      job_id: "job-1",
      job_status: "finished",
      artifact_type: "mutation_recommendations",
      bucket: "iee-artifacts",
      object_key: "analysis-jobs/job-1/mutation-recommendations.json",
      checksum: null,
      content_type: "application/json",
      size_bytes: 100,
      source: "worker",
      visibility: "private",
      created_at: "2026-05-21T10:00:00",
      result_summary_json: {
        candidate_count: 4
      }
    }
  ]);

  assert.deepEqual(options, [
    {
      id: "artifact-1",
      label: "2026-05-21T10:00:00 | 4 candidates"
    }
  ]);
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
