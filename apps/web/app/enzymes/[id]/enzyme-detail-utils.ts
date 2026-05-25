import type {
  EnzymeSummary,
  KineticRecord,
  LiteratureReferenceRecord,
  PropertyRecord
} from "../../../lib/types";
import { formatReferenceCitation } from "./reference-utils.ts";

export type FamilyComparisonMetric =
  | "optimal_temperature"
  | "optimal_pH"
  | "specific_activity"
  | "kcat";

export type FamilyComparisonRow = {
  enzyme: EnzymeSummary;
  values: Record<FamilyComparisonMetric, string>;
};

const NOT_FOUND = "Not found";
const EVIDENCE_QUALITY_SEPARATOR = " | Evidence quality: ";
const EVIDENCE_SEPARATOR = " | Evidence: ";

export type OverviewTableKind = "properties" | "kinetics" | "expression" | "default";
export type ParsedEvidenceText = {
  source: string;
  quality: string | null;
  excerpt: string | null;
};

export function formatReferenceForTable(
  referenceId: string | null | undefined,
  referencesById: Record<string, LiteratureReferenceRecord>
): string {
  if (!referenceId) {
    return "-";
  }
  const reference = referencesById[referenceId];
  return reference ? formatReferenceCitation(reference) : referenceId;
}

export function formatVisibilityStatus(
  visibility: string | null | undefined,
  curationStatus: string | null | undefined
): string {
  return [visibility, curationStatus].filter(Boolean).join(" / ") || "-";
}

export function formatConditionEvidence(metadata: Record<string, unknown> | null | undefined): string {
  const evidence = metadata?.evidence;
  return typeof evidence === "string" && evidence.trim() ? evidence.trim() : "-";
}

export function parseEvidenceText(value: string | null | undefined): ParsedEvidenceText {
  const text = value?.trim();
  if (!text) {
    return { source: "-", quality: null, excerpt: null };
  }
  const separatorIndex = text.indexOf(EVIDENCE_SEPARATOR);
  const sourceAndQuality = separatorIndex < 0 ? text : text.slice(0, separatorIndex).trim();
  const qualitySeparatorIndex = sourceAndQuality.indexOf(EVIDENCE_QUALITY_SEPARATOR);
  const source =
    qualitySeparatorIndex < 0 ? sourceAndQuality : sourceAndQuality.slice(0, qualitySeparatorIndex).trim();
  const quality =
    qualitySeparatorIndex < 0
      ? null
      : sourceAndQuality.slice(qualitySeparatorIndex + EVIDENCE_QUALITY_SEPARATOR.length).trim() || null;
  return {
    source: source || "-",
    quality,
    excerpt: separatorIndex < 0 ? null : text.slice(separatorIndex + EVIDENCE_SEPARATOR.length).trim() || null
  };
}

export function formatRealDataRefreshSummary(
  created: Record<string, number>,
  sources: string[]
): string {
  const counts = ["references", "properties", "kinetics", "mutations", "structures"]
    .map((key) => `${key} ${created[key] ?? 0}`)
    .join(", ");
  const sourceText = sources.length > 0 ? sources.join(", ") : "real providers";
  return `Fetched real data: ${counts}. Sources: ${sourceText}.`;
}

export function shouldShowOverviewTable(kind: OverviewTableKind, recordCount: number): boolean {
  return recordCount > 0 || kind === "properties" || kind === "default";
}

export function overviewTableEmptyLabel(kind: OverviewTableKind): string {
  return kind === "properties" ? "not found" : "No records";
}

export function buildFamilyComparisonRow(
  enzyme: EnzymeSummary,
  records: {
    properties: Array<
      Pick<
        PropertyRecord,
        "property_type" | "value_original" | "unit_original" | "value_standardized" | "unit_standardized"
      >
    >;
    kinetics: Array<Pick<KineticRecord, "kcat" | "km" | "kcat_km">>;
  },
  metrics: FamilyComparisonMetric[]
): FamilyComparisonRow {
  return {
    enzyme,
    values: Object.fromEntries(
      metrics.map((metric) => [metric, comparisonMetricValue(metric, records)])
    ) as Record<FamilyComparisonMetric, string>
  };
}

export function formatFamilyComparisonMetric(metric: FamilyComparisonMetric): string {
  const labels: Record<FamilyComparisonMetric, string> = {
    optimal_temperature: "Optimal temperature",
    optimal_pH: "Optimal pH",
    specific_activity: "Specific activity",
    kcat: "kcat"
  };
  return labels[metric];
}

function comparisonMetricValue(
  metric: FamilyComparisonMetric,
  records: {
    properties: Array<
      Pick<
        PropertyRecord,
        "property_type" | "value_original" | "unit_original" | "value_standardized" | "unit_standardized"
      >
    >;
    kinetics: Array<Pick<KineticRecord, "kcat" | "km" | "kcat_km">>;
  }
): string {
  if (metric === "kcat") {
    return records.kinetics.map((record) => record.kcat).find(hasText)?.trim() ?? NOT_FOUND;
  }

  const property = records.properties.find((record) => record.property_type === metric);
  if (!property) {
    return NOT_FOUND;
  }
  const value = property.value_standardized?.trim() || property.value_original?.trim();
  if (!value) {
    return NOT_FOUND;
  }
  const unit = property.unit_standardized?.trim() || property.unit_original?.trim();
  return unit && !value.includes(unit) ? `${value} ${unit}` : value;
}

function hasText(value: string | null | undefined): value is string {
  return Boolean(value?.trim());
}
