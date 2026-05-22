import assert from "node:assert/strict";
import { test } from "node:test";

import {
  buildStructureWarnings,
  getChainOptions,
  getDefaultStructureId,
  getLigandViews,
  getStructureProvenanceView,
  getStructureStats,
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
    distance_matrix: []
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
