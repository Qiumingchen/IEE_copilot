import type { StructureRecord } from "../../../../lib/types";
import {
  formatProvenanceLabel,
  getProvenanceModeTone,
  provenanceFromRecord,
  provenanceUrl,
  provenanceWarning
} from "../../../../lib/provenance.ts";

export type ChainOptionView = {
  structure_id: string;
  chain_id: string;
  label: string;
  residue_count: number | string;
  sequence: string;
  mapping_quality: string;
};

export type LigandView = {
  ligand_code: string;
  ligand_name: string;
  ligand_type: string;
  location: string;
  atom_count: number | string;
  nearest_residues: Record<"4A" | "6A" | "8A", string[]>;
};

export type StructureStatsView = {
  chain_count: number | string;
  ligand_count: number | string;
  metal_count: number | string;
  residue_count: number;
  complex_state: string;
  artifact_object_key: string;
};

export type StructureProvenanceView = {
  label: string;
  mode: "real" | "fallback" | "unknown";
  source_url: string | null;
  warning: string | null;
};

export function getChainOptions(structures: StructureRecord[]): ChainOptionView[] {
  return structures.flatMap((structure) => {
    const chains = getRecordArray(structure.chain_summary, "chains");
    return chains.map((chain) => {
      const chainId = String(valueOrDash(chain.chain_id));
      return {
        structure_id: structure.id,
        chain_id: chainId,
        label: `${structure.id} / chain ${chainId}`,
        residue_count: valueOrDash(chain.residue_count),
        sequence: String(valueOrDash(chain.sequence)),
        mapping_quality: String(valueOrDash(chain.mapping_quality))
      };
    });
  });
}

export function getDefaultStructureId(structures: StructureRecord[]): string | null {
  return (
    structures.find((structure) => getResidueRows(structure, null).length > 0)?.id ??
    structures[0]?.id ??
    null
  );
}

export function getLigandViews(structure: StructureRecord): LigandView[] {
  const ligands = getRecordArray(structure.ligand_summary, "ligands");
  return ligands.map((ligand) => {
    const chainId = String(valueOrDash(ligand.chain_id));
    const residueNumber = String(valueOrDash(ligand.residue_number));
    return {
      ligand_code: String(valueOrDash(ligand.ligand_code)),
      ligand_name: String(valueOrDash(ligand.ligand_name)),
      ligand_type: String(valueOrDash(ligand.ligand_type)),
      location: `${chainId}${residueNumber}`,
      atom_count: valueOrDash(ligand.atom_count),
      nearest_residues: {
        "4A": formatNearestResidues(ligand, "4A"),
        "6A": formatNearestResidues(ligand, "6A"),
        "8A": formatNearestResidues(ligand, "8A")
      }
    };
  });
}

export function getStructureStats(structure: StructureRecord): StructureStatsView {
  const chains = getRecordArray(structure.chain_summary, "chains");
  return {
    chain_count: valueOrDash(structure.chain_summary?.chain_count ?? chains.length),
    ligand_count: valueOrDash(structure.ligand_summary?.ligand_count),
    metal_count: valueOrDash(structure.ligand_summary?.metal_count),
    residue_count: chains.reduce((total, chain) => total + numberValue(chain.residue_count), 0),
    complex_state: structure.complex_state,
    artifact_object_key: structure.artifact?.object_key ?? "-"
  };
}

export function buildStructureWarnings(structure: StructureRecord): string[] {
  const warnings = structure.chain_summary?.warnings;
  if (!Array.isArray(warnings)) {
    return [];
  }
  return warnings.map(String).filter(Boolean);
}

export function getStructureProvenanceView(structure: StructureRecord): StructureProvenanceView {
  const provenance = provenanceFromRecord(structure as unknown as Record<string, unknown>, "chain_summary");
  return {
    label: formatProvenanceLabel(provenance),
    mode: getProvenanceModeTone(provenance),
    source_url: provenanceUrl(provenance),
    warning: provenanceWarning(provenance)
  };
}

export function getResidueRows(structure: StructureRecord, selectedChainId: string | null) {
  const chains = getRecordArray(structure.chain_summary, "chains");
  const selectedChain = chains.find((chain) => String(chain.chain_id) === selectedChainId) ?? chains[0];
  if (!selectedChain) {
    return [];
  }
  const residues = selectedChain.residues;
  if (!Array.isArray(residues)) {
    return [];
  }
  return residues.filter(isRecord).map((residue) => ({
    sequence_position: valueOrDash(residue.sequence_position),
    pdb_residue: `${valueOrDash(residue.residue_number)}${String(residue.insertion_code ?? "")}`,
    residue_name: String(valueOrDash(residue.residue_name)),
    one_letter: String(valueOrDash(residue.one_letter))
  }));
}

function formatNearestResidues(ligand: Record<string, unknown>, cutoff: "4A" | "6A" | "8A"): string[] {
  const nearestResidues = ligand.nearest_residues;
  if (!isRecord(nearestResidues)) {
    return [];
  }
  const residues = nearestResidues[cutoff];
  if (!Array.isArray(residues)) {
    return [];
  }
  return residues.filter(isRecord).map((residue) => {
    const chainId = String(valueOrDash(residue.chain_id));
    const residueNumber = String(valueOrDash(residue.residue_number));
    const oneLetter = String(valueOrDash(residue.one_letter));
    const rawDistance = valueOrDash(residue.min_distance_angstrom);
    const distance = typeof rawDistance === "number" ? rawDistance.toFixed(1) : rawDistance;
    return `${chainId}${residueNumber} ${oneLetter} ${distance}A`;
  });
}

function getRecordArray(source: Record<string, unknown> | null | undefined, key: string): Record<string, unknown>[] {
  const value = source?.[key];
  return Array.isArray(value) ? value.filter(isRecord) : [];
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function valueOrDash(value: unknown): string | number {
  if (typeof value === "string" && value.length > 0) {
    return value;
  }
  if (typeof value === "number") {
    return value;
  }
  return "-";
}

function numberValue(value: unknown): number {
  return typeof value === "number" ? value : Number(value) || 0;
}
