import type { LiteratureReferenceRecord, MutationRecord } from "../../../../lib/types";
import { formatReferenceCitation } from "../reference-utils.ts";

export type MutationPositionSummary = {
  position: number;
  count: number;
  mutations: string[];
};

export type MutationDeltaSummaryItem = {
  property: string;
  improved: number;
  worsened: number;
  neutral: number;
  top_mutations: Array<{
    mutation_string: string;
    value: number;
    effect_summary: string | null;
  }>;
};

export const commonMutationPropertyDeltaKeys = [
  "",
  "optimal_temperature_delta_degC",
  "specific_activity_fold_change",
  "optimal_pH_delta",
  "soluble_expression_fold_change",
  "product_selectivity_delta"
];

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

export function buildMutationDeltaSummary(
  records: Array<Pick<MutationRecord, "mutation_string" | "effect_summary" | "property_delta">>
): MutationDeltaSummaryItem[] {
  const byProperty = new Map<
    string,
    Array<{ mutation_string: string; value: number; effect_summary: string | null }>
  >();

  for (const record of records) {
    for (const [property, rawValue] of Object.entries(record.property_delta ?? {})) {
      const value = numericValue(rawValue);
      if (value === null) {
        continue;
      }
      const rows = byProperty.get(property) ?? [];
      rows.push({
        mutation_string: record.mutation_string,
        value,
        effect_summary: record.effect_summary
      });
      byProperty.set(property, rows);
    }
  }

  return Array.from(byProperty.entries())
    .map(([property, rows]) => ({
      property,
      improved: rows.filter((row) => row.value > improvementBaseline(property)).length,
      worsened: rows.filter((row) => row.value < improvementBaseline(property)).length,
      neutral: rows.filter((row) => row.value === improvementBaseline(property)).length,
      top_mutations: [...rows].sort((left, right) => right.value - left.value).slice(0, 5)
    }))
    .sort((left, right) => left.property.localeCompare(right.property));
}

export function buildMutationPropertyDeltaOptions(
  records: Array<Pick<MutationRecord, "property_delta">>
): string[] {
  const observed = new Set<string>();
  for (const record of records) {
    for (const key of Object.keys(record.property_delta ?? {})) {
      if (key.trim()) {
        observed.add(key);
      }
    }
  }
  const extras = Array.from(observed)
    .filter((key) => !commonMutationPropertyDeltaKeys.includes(key))
    .sort((left, right) => left.localeCompare(right));

  return [...commonMutationPropertyDeltaKeys, ...extras];
}

export type MutationEvidenceFilters = {
  curationStatus?: string;
  referenceSource?: string;
};

export function filterMutationEvidenceRecords<T extends {
  assay_condition_summary?: Record<string, unknown> | null;
  curation_status?: string | null;
  reference?: Pick<LiteratureReferenceRecord, "source"> | null;
}>(
  records: T[],
  filters: MutationEvidenceFilters
): T[] {
  return records.filter((record) => {
    const assaySource =
      record.assay_condition_summary && typeof record.assay_condition_summary.source === "string"
        ? record.assay_condition_summary.source
        : "";
    const source = record.reference?.source ?? assaySource;
    return (
      (!filters.referenceSource || source === filters.referenceSource) &&
      (!filters.curationStatus || record.curation_status === filters.curationStatus)
    );
  });
}

export function buildMutationEvidenceCsv(
  records: Array<
    Pick<
      MutationRecord,
      | "mutation_string"
      | "effect_summary"
      | "property_delta"
      | "substrate"
      | "reference"
      | "reference_id"
      | "assay_condition_summary"
      | "visibility"
      | "curation_status"
    >
  >
): string {
  const header = [
    "mutation_string",
    "effect_summary",
    "property_delta",
    "substrate",
    "reference",
    "evidence_text",
    "visibility",
    "curation_status"
  ];
  const rows = records.map((record) => {
    const evidence =
      record.assay_condition_summary && typeof record.assay_condition_summary.evidence === "string"
        ? record.assay_condition_summary.evidence
        : "";
    return [
      record.mutation_string,
      record.effect_summary,
      record.property_delta ? JSON.stringify(record.property_delta) : "",
      record.substrate,
      record.reference ? formatReferenceCitation(record.reference) : record.reference_id,
      evidence,
      record.visibility,
      record.curation_status
    ].map(formatCsvCell).join(",");
  });
  return [header.join(","), ...rows].join("\n");
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
  return formatReferenceCitation(reference);
}

export function formatMutationPositions(record: Pick<MutationRecord, "mutation_positions">): string {
  if (record.mutation_positions.length === 0) {
    return "-";
  }
  return record.mutation_positions
    .map((mutation) => `${mutation.wildtype}${mutation.position}${mutation.mutant}`)
    .join(" / ");
}

function formatCsvCell(value: unknown): string {
  const text = value === null || value === undefined ? "" : String(value);
  return /[",\n\r]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

function numericValue(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value !== "string" || value.trim() === "") {
    return null;
  }
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function improvementBaseline(property: string): number {
  return property.endsWith("_fold_change") ? 1 : 0;
}
