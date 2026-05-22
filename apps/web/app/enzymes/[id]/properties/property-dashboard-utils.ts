import type {
  KineticRecord,
  LiteratureReferenceRecord,
  PropertyRankingGroupRecord,
  PropertyRankingItemRecord,
  PropertyRecord
} from "../../../../lib/types";
import { formatReferenceCitation } from "../reference-utils.ts";

export const defaultPropertyTypes = [
  "optimal_temperature",
  "optimal_pH",
  "specific_activity",
  "Km",
  "kcat",
  "kcat/Km",
  "expression_level",
  "soluble_expression",
  "product_selectivity",
  "substrate_specificity"
];

export function buildPropertyOptions(
  records: Array<Pick<PropertyRecord, "property_type">>
): string[] {
  const observed = new Set(records.map((record) => record.property_type).filter(Boolean));
  const defaults = defaultPropertyTypes.filter((propertyType) => propertyType);
  const extras = Array.from(observed)
    .filter((propertyType) => !defaults.includes(propertyType))
    .sort((left, right) => left.localeCompare(right));

  return [...defaults, ...extras];
}

export type PropertyEvidenceFilters = {
  curationStatus?: string;
  propertyType?: string;
  referenceSource?: string;
};

export type PropertyDistributionBin = {
  label: string;
  count: number;
};

export type PropertyDistribution = {
  count: number;
  unit: string | null;
  min: number | null;
  median: number | null;
  max: number | null;
  bins: PropertyDistributionBin[];
};

export function buildPropertyDistribution(
  records: Array<
    Pick<
      PropertyRecord,
      "value_original" | "unit_original" | "value_standardized" | "unit_standardized"
    >
  >,
  binCount = 4
): PropertyDistribution {
  const values = records
    .map((record) => numericValue(record.value_standardized ?? record.value_original))
    .filter((value): value is number => value !== null)
    .sort((left, right) => left - right);
  const unit = records.find((record) => record.unit_standardized || record.unit_original);
  const displayUnit = unit?.unit_standardized ?? unit?.unit_original ?? null;
  if (values.length === 0) {
    return { count: 0, unit: displayUnit, min: null, median: null, max: null, bins: [] };
  }

  const min = values[0];
  const max = values[values.length - 1];
  const median = medianValue(values);
  return {
    count: values.length,
    unit: displayUnit,
    min,
    median,
    max,
    bins: buildBins(values, min, max, binCount)
  };
}

export function filterPropertyEvidenceRecords<T extends {
  curation_status?: string | null;
  property_type?: string | null;
  reference?: Pick<LiteratureReferenceRecord, "source"> | null;
}>(
  records: T[],
  filters: PropertyEvidenceFilters
): T[] {
  return records.filter((record) => {
    const source = record.reference?.source ?? "";
    return (
      (!filters.propertyType || record.property_type === filters.propertyType) &&
      (!filters.referenceSource || source === filters.referenceSource) &&
      (!filters.curationStatus || record.curation_status === filters.curationStatus)
    );
  });
}

export function buildPropertyEvidenceCsv(
  records: Array<
    Pick<
      PropertyRecord,
      | "property_type"
      | "value_original"
      | "unit_original"
      | "value_standardized"
      | "unit_standardized"
      | "substrate"
      | "assay_temperature"
      | "assay_pH"
      | "method"
      | "reference"
      | "reference_id"
      | "evidence_text"
      | "visibility"
      | "curation_status"
    >
  >
): string {
  const header = [
    "property_type",
    "value_original",
    "unit_original",
    "value_standardized",
    "unit_standardized",
    "substrate",
    "assay_temperature",
    "assay_pH",
    "method",
    "reference",
    "evidence_text",
    "visibility",
    "curation_status"
  ];
  const rows = records.map((record) =>
    [
      record.property_type,
      record.value_original,
      record.unit_original,
      record.value_standardized,
      record.unit_standardized,
      record.substrate,
      record.assay_temperature,
      record.assay_pH,
      record.method,
      record.reference ? formatReferenceCitation(record.reference) : record.reference_id,
      record.evidence_text,
      record.visibility,
      record.curation_status
    ].map(formatCsvCell).join(",")
  );
  return [header.join(","), ...rows].join("\n");
}

export function buildPropertyRankingCsv(ranking: {
  groups: PropertyRankingGroupRecord[];
  items: PropertyRankingItemRecord[];
  ranking_mode: string;
}): string {
  const header = [
    "group_context",
    "rank",
    "enzyme_name",
    "organism",
    "value",
    "substrate",
    "assay_temperature",
    "assay_pH",
    "method",
    "reference_id"
  ];
  const sourceRows =
    ranking.ranking_mode === "condition_grouped"
      ? ranking.groups.flatMap((group) =>
          group.items.map((item) => ({ groupContext: summarizeRankingGroup(group), item }))
        )
      : ranking.items.map((item) => ({ groupContext: "", item }));
  const rows = sourceRows.map(({ groupContext, item }) =>
    [
      groupContext,
      item.rank,
      item.enzyme_name,
      item.organism,
      formatRankingValue(item),
      item.substrate,
      item.assay_temperature,
      item.assay_pH,
      item.method,
      item.reference_id
    ].map(formatCsvCell).join(",")
  );
  return [header.join(","), ...rows].join("\n");
}

export function formatRankingValue(
  item: Pick<
    PropertyRankingItemRecord,
    "value_original" | "unit_original" | "value_standardized" | "unit_standardized"
  >
): string {
  const original = `${item.value_original}${item.unit_original ? ` ${item.unit_original}` : ""}`;
  if (!item.value_standardized) {
    return original;
  }

  const standardized = `${item.value_standardized}${
    item.unit_standardized ? ` ${item.unit_standardized}` : ""
  }`;
  return standardized === original ? original : `${standardized} (reported ${original})`;
}

export function summarizeRankingGroup(
  group: Pick<PropertyRankingGroupRecord, "condition_key" | "items">
): string {
  const parts = [
    group.condition_key.reference_id,
    group.condition_key.substrate,
    group.condition_key.assay_temperature ? `${group.condition_key.assay_temperature} degC` : null,
    group.condition_key.assay_pH ? `pH ${group.condition_key.assay_pH}` : null,
    group.condition_key.unit,
    group.condition_key.method,
    `${group.items.length} records`
  ];

  return parts.filter(Boolean).join(" · ");
}

export function formatAssayContext(item: PropertyRankingItemRecord): string {
  const parts = [
    item.substrate,
    item.assay_temperature ? `${item.assay_temperature} degC` : null,
    item.assay_pH ? `pH ${item.assay_pH}` : null,
    item.method,
    item.reference_id
  ];

  return parts.filter(Boolean).join(" · ") || "-";
}

export function formatPropertyEvidence(
  record: Pick<
    PropertyRecord,
    "reference_id" | "reference" | "evidence_text" | "visibility" | "curation_status"
  >,
  referencesById: Record<string, LiteratureReferenceRecord> = {}
): string {
  const reference = record.reference ?? (record.reference_id ? referencesById[record.reference_id] : null);
  const parts = [
    reference ? formatReferenceLabel(reference) : record.reference_id,
    record.evidence_text,
    `${record.visibility} / ${record.curation_status}`
  ];

  return parts.filter(Boolean).join(" · ") || "-";
}

export function formatKineticEvidence(
  record: Pick<KineticRecord, "reference_id" | "reference" | "evidence_text" | "visibility" | "curation_status">,
  referencesById: Record<string, LiteratureReferenceRecord> = {}
): string {
  const reference = record.reference ?? (record.reference_id ? referencesById[record.reference_id] : null);
  const parts = [
    reference ? formatReferenceLabel(reference) : record.reference_id,
    record.evidence_text,
    `${record.visibility} / ${record.curation_status}`
  ];

  return parts.filter(Boolean).join(" · ") || "-";
}

export function formatReferenceLabel(reference: LiteratureReferenceRecord): string {
  return formatReferenceCitation(reference);
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

function medianValue(values: number[]): number {
  const middle = Math.floor(values.length / 2);
  if (values.length % 2 === 1) {
    return values[middle];
  }
  return roundForDisplay((values[middle - 1] + values[middle]) / 2);
}

function buildBins(values: number[], min: number, max: number, binCount: number): PropertyDistributionBin[] {
  const safeBinCount = Math.max(1, binCount);
  if (min === max) {
    return [{ label: formatNumber(min), count: values.length }];
  }
  const width = (max - min) / safeBinCount;
  return Array.from({ length: safeBinCount }, (_, index) => {
    const start = min + width * index;
    const end = index === safeBinCount - 1 ? max : min + width * (index + 1);
    return {
      label: `${formatNumber(start)}-${formatNumber(end)}`,
      count: values.filter((value) =>
        index === safeBinCount - 1 ? value >= start && value <= end : value >= start && value < end
      ).length
    };
  });
}

function roundForDisplay(value: number): number {
  return Number(value.toFixed(1));
}

function formatNumber(value: number): string {
  return Number.isInteger(value) ? String(value) : String(roundForDisplay(value));
}
