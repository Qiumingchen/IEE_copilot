import assert from "node:assert/strict";
import { test } from "node:test";

import {
  buildDistanceMatrixCsv,
  buildResidueMappingCsv,
  buildStructureReportJson,
  buildStructureWarnings,
  buildStructureDownloadFileName,
  getChainOptions,
  getDefaultStructureId,
  getDistanceMatrixRows,
  getLigandViews,
  getStructureQualityChecks,
  getStructurePreviewAtoms,
  getStructureProvenanceView,
  getStructureReadiness,
  getStructureStats,
  getStructureWorkflowActions,
  isStructureUploadFileName,
  structureUploadAccept,
  summarizeStructureUploadResult
} from "../app/enzymes/[id]/structures/structure-utils.ts";

const structure = {
  id: "structure-1",
  enzyme_entry_id: "enzyme-1",
  structure_type: "uploaded_pdb",
  complex_state: "enzyme_substrate_complex",
  pdb_id: null,
  source: "user_upload",
  artifact_id: "artifact-1",
  artifact: {
    id: "artifact-1",
    bucket: "iee-artifacts",
    object_key: "structures/structure-1/complex.pdb",
    checksum: "abc",
    content_type: "chemical/x-pdb",
    size_bytes: 1234
  },
  ligands: [],
  chain_summary: {
    chain_count: 1,
    provenance: {
      provider: "alphafold_mock",
      mode: "fallback",
      warning: "AlphaFold provider failed",
      source_url: "mock://alphafold/AF-P99998-F1.pdb"
    },
    warnings: ["missing residue around A3"],
    preview_atoms: [
      {
        kind: "protein",
        chain_id: "A",
        residue_number: "1",
        sequence_position: 1,
        label: "M1",
        x: 12.56,
        y: 13.407,
        z: 9.142
      },
      {
        kind: "ligand",
        chain_id: "B",
        residue_number: "501",
        sequence_position: null,
        label: "AQ1",
        x: 16.1,
        y: 11.1,
        z: 8.1
      }
    ],
    chains: [
      {
        chain_id: "A",
        residue_count: 2,
        sequence: "MG",
        residue_numbers: ["1", "2"],
        mapping_quality: "complete",
        residues: [
          {
            chain_id: "A",
            residue_number: "1",
            insertion_code: "",
            sequence_position: 1,
            residue_name: "MET",
            one_letter: "M"
          },
          {
            chain_id: "A",
            residue_number: "2",
            insertion_code: "",
            sequence_position: 2,
            residue_name: "GLY",
            one_letter: "G"
          }
        ]
      }
    ]
  },
  ligand_summary: {
    ligand_count: 1,
    metal_count: 1,
    ligands: [
      {
        ligand_name: "AQ1",
        ligand_code: "AQ1",
        chain_id: "B",
        residue_number: "501",
        atom_count: 2,
        ligand_type: "hetero_ligand",
        nearest_residues: {
          "4A": [
            {
              chain_id: "A",
              residue_number: "2",
              insertion_code: "",
              sequence_position: 2,
              residue_name: "GLY",
              one_letter: "G",
              min_distance_angstrom: 0.6
            }
          ],
          "6A": [
            {
              chain_id: "A",
              residue_number: "2",
              insertion_code: "",
              sequence_position: 2,
              residue_name: "GLY",
              one_letter: "G",
              min_distance_angstrom: 0.6
            },
            {
              chain_id: "A",
              residue_number: "1",
              insertion_code: "",
              sequence_position: 1,
              residue_name: "MET",
              one_letter: "M",
              min_distance_angstrom: 5.0
            }
          ],
          "8A": []
        }
      }
    ],
    metal_ions: [
      {
        ligand_name: "ZN",
        ligand_code: "ZN",
        chain_id: "C",
        residue_number: "601",
        atom_count: 1,
        ligand_type: "metal_ion"
      }
    ],
    distance_matrix: [
      {
        ligand_code: "AQ1",
        ligand_chain_id: "B",
        ligand_residue_number: "501",
        residue_chain_id: "A",
        residue_number: "2",
        insertion_code: "",
        sequence_position: 2,
        min_distance_angstrom: 0.6
      },
      {
        ligand_code: "AQ1",
        ligand_chain_id: "B",
        ligand_residue_number: "501",
        residue_chain_id: "A",
        residue_number: "1",
        insertion_code: "",
        sequence_position: 1,
        min_distance_angstrom: 5.0
      }
    ]
  }
};

test("builds chain options from structure chain summaries", () => {
  assert.deepEqual(getChainOptions([structure]), [
    {
      structure_id: "structure-1",
      chain_id: "A",
      label: "structure-1 / chain A",
      residue_count: 2,
      sequence: "MG",
      mapping_quality: "complete"
    }
  ]);
});

test("builds ligand views with nearest residues by cutoff", () => {
  assert.deepEqual(getLigandViews(structure), [
    {
      ligand_code: "AQ1",
      ligand_name: "AQ1",
      ligand_type: "hetero_ligand",
      location: "B501",
      atom_count: 2,
      nearest_residues: {
        "4A": ["A2 G 0.6A"],
        "6A": ["A2 G 0.6A", "A1 M 5.0A"],
        "8A": []
      }
    }
  ]);
});

test("summarizes structure stats and warnings", () => {
  assert.deepEqual(getStructureStats(structure), {
    chain_count: 1,
    ligand_count: 1,
    metal_count: 1,
    residue_count: 2,
    complex_state: "enzyme_substrate_complex",
    artifact_object_key: "structures/structure-1/complex.pdb"
  });
  assert.deepEqual(buildStructureWarnings(structure), ["missing residue around A3"]);
});

test("builds structure quality checks from parsed chains and ligand contacts", () => {
  assert.deepEqual(getStructureQualityChecks(structure), [
    {
      label: "Protein chains",
      status: "pass",
      detail: "1 chain detected."
    },
    {
      label: "Residue mapping",
      status: "pass",
      detail: "2 residues mapped to sequence positions."
    },
    {
      label: "Parser warnings",
      status: "warn",
      detail: "1 warning reported."
    },
    {
      label: "Ligand contact matrix",
      status: "pass",
      detail: "2 ligand-residue distances available."
    }
  ]);

  const incompleteStructure = {
    ...structure,
    chain_summary: { chains: [], warnings: [] },
    ligand_summary: { ligand_count: 1, distance_matrix: [] }
  };

  assert.deepEqual(getStructureQualityChecks(incompleteStructure), [
    {
      label: "Protein chains",
      status: "fail",
      detail: "No protein chain was detected."
    },
    {
      label: "Residue mapping",
      status: "fail",
      detail: "No residues could be mapped to sequence positions."
    },
    {
      label: "Parser warnings",
      status: "pass",
      detail: "No parser warnings reported."
    },
    {
      label: "Ligand contact matrix",
      status: "warn",
      detail: "Complex-like structure has ligands, but no ligand distance matrix is available."
    }
  ]);
});

test("builds structure provenance display view", () => {
  assert.deepEqual(getStructureProvenanceView(structure), {
    label: "alphafold_mock fallback",
    mode: "fallback",
    source_url: "mock://alphafold/AF-P99998-F1.pdb",
    warning: "AlphaFold provider failed"
  });
});

test("prefers structures with residue mapping for the default selection", () => {
  const unmappedStructure = {
    ...structure,
    id: "structure-without-mapping",
    chain_summary: {
      chains: [
        {
          chain_id: "A",
          residue_count: 2,
          sequence: "MG"
        }
      ]
    }
  };

  assert.equal(getDefaultStructureId([unmappedStructure, structure]), "structure-1");
});

test("validates supported structure upload file names", () => {
  assert.equal(structureUploadAccept.includes(".pdb"), true);
  assert.equal(structureUploadAccept.includes(".cif"), true);
  assert.equal(isStructureUploadFileName("complex.PDB"), true);
  assert.equal(isStructureUploadFileName("model.cif"), true);
  assert.equal(isStructureUploadFileName("notes.txt"), false);
});

test("summarizes uploaded structure parsing result", () => {
  assert.equal(
    summarizeStructureUploadResult(structure),
    "Uploaded enzyme_substrate_complex structure with 1 chain, 1 ligand, and 1 metal ion."
  );
});

test("builds structure download file names from artifact keys", () => {
  assert.equal(buildStructureDownloadFileName(structure), "complex.pdb");
  assert.equal(
    buildStructureDownloadFileName({ ...structure, artifact: { ...structure.artifact, object_key: "" } }),
    "structure-1.pdb"
  );
  assert.equal(
    buildStructureDownloadFileName({
      ...structure,
      id: "structure-cif",
      structure_type: "uploaded_cif",
      artifact: null
    }),
    "structure-cif.cif"
  );
});

test("extracts structure preview atoms from parsed coordinate summaries", () => {
  assert.deepEqual(getStructurePreviewAtoms(structure), [
    {
      kind: "protein",
      chain_id: "A",
      residue_number: "1",
      sequence_position: 1,
      label: "M1",
      x: 12.56,
      y: 13.407,
      z: 9.142
    },
    {
      kind: "ligand",
      chain_id: "B",
      residue_number: "501",
      sequence_position: "-",
      label: "AQ1",
      x: 16.1,
      y: 11.1,
      z: 8.1
    }
  ]);
  assert.deepEqual(getStructurePreviewAtoms({ ...structure, chain_summary: {} }), []);
});

test("builds distance matrix rows for ligand contact review", () => {
  assert.deepEqual(getDistanceMatrixRows(structure), [
    {
      ligand: "AQ1 B501",
      residue: "A2",
      sequence_position: 2,
      distance_angstrom: "0.6"
    },
    {
      ligand: "AQ1 B501",
      residue: "A1",
      sequence_position: 1,
      distance_angstrom: "5.0"
    }
  ]);
});

test("builds ligand distance matrix CSV for export", () => {
  assert.equal(
    buildDistanceMatrixCsv(getDistanceMatrixRows(structure)),
    [
      "ligand,residue,sequence_position,distance_angstrom",
      "AQ1 B501,A2,2,0.6",
      "AQ1 B501,A1,1,5.0"
    ].join("\n")
  );
  assert.equal(
    buildDistanceMatrixCsv([
      {
        ligand: "AQ1, quoted",
        residue: "A\"2",
        sequence_position: 2,
        distance_angstrom: "0.6"
      }
    ]),
    [
      "ligand,residue,sequence_position,distance_angstrom",
      "\"AQ1, quoted\",\"A\"\"2\",2,0.6"
    ].join("\n")
  );
});

test("builds residue mapping CSV for export", () => {
  assert.equal(
    buildResidueMappingCsv([
      {
        sequence_position: 1,
        pdb_residue: "1",
        residue_name: "MET",
        one_letter: "M"
      },
      {
        sequence_position: 2,
        pdb_residue: "2A",
        residue_name: "GLY, quoted",
        one_letter: "G"
      }
    ]),
    [
      "sequence_position,pdb_residue,residue_name,one_letter",
      "1,1,MET,M",
      "2,2A,\"GLY, quoted\",G"
    ].join("\n")
  );
});

test("builds structure analysis report JSON for export", () => {
  const payload = JSON.parse(buildStructureReportJson(
    structure,
    "enzyme-1",
    {
      generatedAt: "2026-05-22T08:00:00.000Z",
      selectedChainId: "A"
    }
  ));

  assert.equal(payload.enzyme_entry_id, "enzyme-1");
  assert.equal(payload.structure.id, "structure-1");
  assert.equal(payload.generated_at, "2026-05-22T08:00:00.000Z");
  assert.equal(payload.selected_chain_id, "A");
  assert.equal(payload.stats.ligand_count, 1);
  assert.equal(payload.provenance.label, "alphafold_mock fallback");
  assert.equal(payload.quality_checks.length, 4);
  assert.equal(payload.readiness.status, "ready");
  assert.equal(payload.warnings[0], "missing residue around A3");
  assert.equal(payload.ligands[0].ligand_code, "AQ1");
  assert.equal(payload.distance_matrix[0].distance_angstrom, "0.6");
  assert.equal(payload.residue_mapping[0].one_letter, "M");
  assert.equal(payload.preview_atoms[1].kind, "ligand");
});

test("summarizes structure readiness for ligand-aware analysis", () => {
  assert.deepEqual(getStructureReadiness(structure), {
    status: "ready",
    title: "Ligand-aware structure ready",
    description: "Parsed chains, residue mapping, ligands, and ligand distance matrix are available."
  });

  assert.deepEqual(getStructureReadiness({ ...structure, complex_state: "apo", ligand_summary: { ligand_count: 0 } }), {
    status: "limited",
    title: "Apo structure ready",
    description: "Residue mapping is available, but ligand-aware contacts require an enzyme-substrate complex."
  });
});

test("builds structure workflow actions for reserved and available analyses", () => {
  assert.deepEqual(getStructureWorkflowActions(structure, "enzyme-1"), [
    {
      label: "Rosetta ddG",
      status: "ready",
      description: "Use this parsed structure as the structural context for mutation stability scoring.",
      href: "/enzymes/enzyme-1/analysis?structure_id=structure-1&focus=rosetta_ddg",
      cta_label: "Open Rosetta ddG"
    },
    {
      label: "Ligand-aware recommendations",
      status: "ready",
      description: "Use ligand contacts and residue mapping to prioritize substrate-proximal mutation sites.",
      href: "/enzymes/enzyme-1/analysis?structure_id=structure-1&focus=mutation_recommendation",
      cta_label: "Open recommendations"
    },
    {
      label: "MD simulation",
      status: "reserved",
      description: "Workflow slot is reserved; automated MD execution will be added later.",
      href: null,
      cta_label: null
    },
    {
      label: "MMPBSA",
      status: "reserved",
      description: "Complex structure detected; binding-energy workflow slot is reserved for later implementation.",
      href: null,
      cta_label: null
    }
  ]);
});
