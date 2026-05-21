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
  record: Pick<KineticRecord, "reference_id" | "reference" | "visibility" | "curation_status">,
  referencesById: Record<string, LiteratureReferenceRecord> = {}
): string {
  const reference = record.reference ?? (record.reference_id ? referencesById[record.reference_id] : null);
  const parts = [
    reference ? formatReferenceLabel(reference) : record.reference_id,
    `${record.visibility} / ${record.curation_status}`
  ];

  return parts.filter(Boolean).join(" · ") || "-";
}

export function formatReferenceLabel(reference: LiteratureReferenceRecord): string {
  return formatReferenceCitation(reference);
}
