import type { LiteratureReferenceRecord, MutationRecord } from "../../../../lib/types";

export type MutationPositionSummary = {
  position: number;
  count: number;
  mutations: string[];
};

export function buildMutationPositionSummary(
  records: Array<Pick<MutationRecord, "mutation_string" | "mutation_positions">>
): MutationPositionSummary[] {
  const byPosition = new Map<number, Set<string>>();
  for (const record of records) {
    for (const mutation of record.mutation_positions) {
      if (!Number.isFinite(mutation.position)) {
        continue;
      }
      const mutations = byPosition.get(mutation.position) ?? new Set<string>();
      mutations.add(record.mutation_string);
      byPosition.set(mutation.position, mutations);
    }
  }

  return Array.from(byPosition.entries())
    .map(([position, mutations]) => ({
      position,
      count: mutations.size,
      mutations: Array.from(mutations).sort((left, right) => left.localeCompare(right))
    }))
    .sort((left, right) => left.position - right.position);
}

export function formatPropertyDelta(delta: Record<string, unknown> | null | undefined): string {
  if (!delta || Object.keys(delta).length === 0) {
    return "-";
  }
  return Object.entries(delta)
    .map(([key, value]) => `${key}: ${String(value)}`)
    .join(" · ");
}

export function formatMutationEvidence(
  record: Pick<MutationRecord, "assay_condition_summary" | "reference_id" | "reference">,
  referencesById: Record<string, LiteratureReferenceRecord> = {}
): string {
  const summary = record.assay_condition_summary;
  const reference = record.reference ?? (record.reference_id ? referencesById[record.reference_id] : null);
  if (!summary && !reference) {
    return "-";
  }
  const source = summary && typeof summary.source === "string" ? summary.source : "";
  const evidence = summary && typeof summary.evidence === "string" ? summary.evidence : "";
  const referenceLabel = reference ? formatMutationReferenceLabel(reference) : "";
  return [referenceLabel || source, evidence].filter(Boolean).join(" · ") || "-";
}

export function formatMutationReferenceLabel(reference: LiteratureReferenceRecord): string {
  const identifier = reference.doi || (reference.pubmed_id ? `PMID ${reference.pubmed_id}` : null);
  return [identifier, reference.title].filter(Boolean).join(" · ") || reference.id;
}

export function formatMutationPositions(record: Pick<MutationRecord, "mutation_positions">): string {
  if (record.mutation_positions.length === 0) {
    return "-";
  }
  return record.mutation_positions
    .map((mutation) => `${mutation.wildtype}${mutation.position}${mutation.mutant}`)
    .join(" / ");
}
