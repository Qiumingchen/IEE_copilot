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

export type StructureReadinessView = {
  status: "ready" | "limited" | "blocked";
  title: string;
  description: string;
};

export type StructureWorkflowActionView = {
  label: string;
  status: "ready" | "reserved" | "blocked";
  description: string;
  href: string | null;
  cta_label: string | null;
};

export type DistanceMatrixRowView = {
  ligand: string;
  residue: string;
  sequence_position: string | number;
  distance_angstrom: string | number;
};

export type StructurePreviewAtomView = {
  kind: string;
  chain_id: string;
  residue_number: string;
  sequence_position: string | number;
  label: string;
  x: number;
  y: number;
  z: number;
};

export type StructureQualityCheckView = {
  label: string;
  status: "pass" | "warn" | "fail";
  detail: string;
};

export const structureUploadAccept = ".pdb,.cif,chemical/x-pdb,chemical/x-cif,text/plain";

export function isStructureUploadFileName(fileName: string): boolean {
  const normalized = fileName.trim().toLowerCase();
  return normalized.endsWith(".pdb") || normalized.endsWith(".cif");
}

export function summarizeStructureUploadResult(structure: StructureRecord): string {
  const stats = getStructureStats(structure);
  const chainLabel = pluralize(stats.chain_count, "chain");
  const ligandLabel = pluralize(stats.ligand_count, "ligand");
  const metalLabel = pluralize(stats.metal_count, "metal ion");
  return `Uploaded ${structure.complex_state} structure with ${chainLabel}, ${ligandLabel}, and ${metalLabel}.`;
}

export function buildStructureDownloadFileName(structure: StructureRecord): string {
  const objectKey = structure.artifact?.object_key ?? "";
  const fileName = objectKey.split("/").filter(Boolean).at(-1);
  return fileName || `${structure.id}.pdb`;
}

export function getStructurePreviewAtoms(structure: StructureRecord): StructurePreviewAtomView[] {
  const previewAtoms = structure.chain_summary?.preview_atoms;
  if (!Array.isArray(previewAtoms)) {
    return [];
  }
  return previewAtoms.filter(isRecord).flatMap((atom) => {
    const x = numberOrNull(atom.x);
    const y = numberOrNull(atom.y);
    const z = numberOrNull(atom.z);
    if (x === null || y === null || z === null) {
      return [];
    }
    return [
      {
        kind: String(valueOrDash(atom.kind)),
        chain_id: String(valueOrDash(atom.chain_id)),
        residue_number: String(valueOrDash(atom.residue_number)),
        sequence_position: valueOrDash(atom.sequence_position),
        label: String(valueOrDash(atom.label)),
        x,
        y,
        z
      }
    ];
  });
}

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

export function getStructureQualityChecks(structure: StructureRecord): StructureQualityCheckView[] {
  const chains = getRecordArray(structure.chain_summary, "chains");
  const residueRows = getResidueRows(structure, null);
  const warnings = buildStructureWarnings(structure);
  const ligandCount = numberValue(structure.ligand_summary?.ligand_count);
  const distanceRows = getDistanceMatrixRows(structure);

  return [
    {
      label: "Protein chains",
      status: chains.length > 0 ? "pass" : "fail",
      detail: chains.length > 0 ? pluralize(chains.length, "chain") + " detected." : "No protein chain was detected."
    },
    {
      label: "Residue mapping",
      status: residueRows.length > 0 ? "pass" : "fail",
      detail:
        residueRows.length > 0
          ? pluralize(residueRows.length, "residue") + " mapped to sequence positions."
          : "No residues could be mapped to sequence positions."
    },
    {
      label: "Parser warnings",
      status: warnings.length > 0 ? "warn" : "pass",
      detail:
        warnings.length > 0
          ? pluralize(warnings.length, "warning") + " reported."
          : "No parser warnings reported."
    },
    {
      label: "Ligand contact matrix",
      status: ligandCount > 0 && distanceRows.length === 0 ? "warn" : "pass",
      detail:
        ligandCount > 0
          ? distanceRows.length > 0
            ? pluralize(distanceRows.length, "ligand-residue distance") + " available."
            : "Complex-like structure has ligands, but no ligand distance matrix is available."
          : "No ligand contact matrix is required for apo structures."
    }
  ];
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

export function getDistanceMatrixRows(structure: StructureRecord): DistanceMatrixRowView[] {
  const rows = getRecordArray(structure.ligand_summary, "distance_matrix");
  return rows.map((row) => {
    const ligandCode = String(valueOrDash(row.ligand_code));
    const ligandChainId = String(valueOrDash(row.ligand_chain_id));
    const ligandResidueNumber = String(valueOrDash(row.ligand_residue_number));
    const residueChainId = String(valueOrDash(row.residue_chain_id));
    const residueNumber = String(valueOrDash(row.residue_number));
    const insertionCode = typeof row.insertion_code === "string" ? row.insertion_code : "";
    const rawDistance = valueOrDash(row.min_distance_angstrom);
    return {
      ligand: `${ligandCode} ${ligandChainId}${ligandResidueNumber}`,
      residue: `${residueChainId}${residueNumber}${insertionCode}`,
      sequence_position: valueOrDash(row.sequence_position),
      distance_angstrom: typeof rawDistance === "number" ? rawDistance.toFixed(1) : rawDistance
    };
  });
}

export function buildDistanceMatrixCsv(rows: DistanceMatrixRowView[]): string {
  return [
    ["ligand", "residue", "sequence_position", "distance_angstrom"],
    ...rows.map((row) => [
      String(row.ligand),
      String(row.residue),
      String(row.sequence_position),
      String(row.distance_angstrom)
    ])
  ].map((row) => row.map(escapeCsvCell).join(",")).join("\n");
}

export function getStructureReadiness(structure: StructureRecord): StructureReadinessView {
  const residueRows = getResidueRows(structure, null);
  if (residueRows.length === 0) {
    return {
      status: "blocked",
      title: "Structure mapping incomplete",
      description: "Upload a PDB or CIF with protein coordinates so residues can be mapped to sequence positions."
    };
  }

  const ligandCount = numberValue(structure.ligand_summary?.ligand_count);
  const distanceRows = getDistanceMatrixRows(structure);
  if (structure.complex_state === "enzyme_substrate_complex" && ligandCount > 0 && distanceRows.length > 0) {
    return {
      status: "ready",
      title: "Ligand-aware structure ready",
      description: "Parsed chains, residue mapping, ligands, and ligand distance matrix are available."
    };
  }

  return {
    status: "limited",
    title: "Apo structure ready",
    description: "Residue mapping is available, but ligand-aware contacts require an enzyme-substrate complex."
  };
}

export function getStructureWorkflowActions(
  structure: StructureRecord,
  enzymeId: string
): StructureWorkflowActionView[] {
  const readiness = getStructureReadiness(structure);
  const hasLigandDistanceMatrix = getDistanceMatrixRows(structure).length > 0;
  const structureId = encodeURIComponent(structure.id);
  return [
    {
      label: "Rosetta ddG",
      status: readiness.status === "blocked" ? "blocked" : "ready",
      description: "Use this parsed structure as the structural context for mutation stability scoring.",
      href: readiness.status === "blocked"
        ? null
        : `/enzymes/${enzymeId}/analysis?structure_id=${structureId}&focus=rosetta_ddg`,
      cta_label: readiness.status === "blocked" ? null : "Open Rosetta ddG"
    },
    {
      label: "Ligand-aware recommendations",
      status: hasLigandDistanceMatrix ? "ready" : "blocked",
      description: hasLigandDistanceMatrix
        ? "Use ligand contacts and residue mapping to prioritize substrate-proximal mutation sites."
        : "Upload an enzyme-substrate complex to enable substrate-proximal mutation prioritization.",
      href: hasLigandDistanceMatrix
        ? `/enzymes/${enzymeId}/analysis?structure_id=${structureId}&focus=mutation_recommendation`
        : null,
      cta_label: hasLigandDistanceMatrix ? "Open recommendations" : null
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
      description:
        structure.complex_state === "enzyme_substrate_complex"
          ? "Complex structure detected; binding-energy workflow slot is reserved for later implementation."
          : "Upload an enzyme-substrate complex before this reserved workflow can use binding context.",
      href: null,
      cta_label: null
    }
  ];
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

function numberOrNull(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function escapeCsvCell(value: string): string {
  if (/[",\n\r]/.test(value)) {
    return `"${value.replaceAll('"', '""')}"`;
  }
  return value;
}

function pluralize(value: string | number, label: string): string {
  return `${value} ${label}${value === 1 ? "" : "s"}`;
}
