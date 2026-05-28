import type {
  EnzymeSummary,
  JobResponse,
  KineticRecord,
  LiteratureReferenceRecord,
  PropertyRecord,
  StructureRecord
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
export type RealDataRefreshProgress = {
  percent: number;
  title: string;
  detail: string;
  summary: string | null;
  warnings: string[];
  checkedSources: number;
  foundRecords: number;
  notFoundSources: number;
  processedEnzymes: number;
  totalEnzymes: number;
  stage: string | null;
  candidateArticles: number;
  articlesScanned: number;
  filteredArticles: number;
  relevantArticles: number;
  extractedRecords: number;
  candidatePapers: CandidatePaperSummary[];
  canPause: boolean;
};

export type CandidatePaperSummary = {
  title: string;
  source: string;
  year: number | null;
  doi: string | null;
  pubmedId: string | null;
  relevanceScore: number | null;
  decision: string | null;
  reason: string | null;
  extractedFields: string[];
  missingFields: string[];
  extractionNotes: string[];
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

export function sortLiteratureReferencesForDisplay(
  references: LiteratureReferenceRecord[]
): LiteratureReferenceRecord[] {
  return [...references].sort((left, right) => {
    const leftYear = left.year ?? Number.NEGATIVE_INFINITY;
    const rightYear = right.year ?? Number.NEGATIVE_INFINITY;
    if (leftYear !== rightYear) {
      return rightYear - leftYear;
    }
    return left.title.localeCompare(right.title);
  });
}

export function sortStructuresForDisplay<T extends Pick<StructureRecord, "structure_type" | "source">>(
  structures: T[]
): T[] {
  return [...structures].sort((left, right) => structureDisplayPriority(left) - structureDisplayPriority(right));
}

export function isUserUploadedStructure(
  structure: Pick<StructureRecord, "structure_type" | "source">
): boolean {
  return (
    structure.source.toLowerCase() === "user_upload" &&
    ["uploaded_pdb", "uploaded_cif"].includes(structure.structure_type.toLowerCase())
  );
}

function structureDisplayPriority(structure: Pick<StructureRecord, "structure_type" | "source">): number {
  const source = structure.source.toLowerCase();
  const structureType = structure.structure_type.toLowerCase();
  if (source.includes("rcsb") || structureType === "pdb") {
    return 0;
  }
  if (source.includes("alphafold") || structureType === "alphafold") {
    return 1;
  }
  return isUserUploadedStructure(structure) ? 3 : 2;
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

export function buildRealDataRefreshProgress(
  job: Pick<JobResponse, "id" | "status" | "job_type" | "parameters_json" | "result_summary_json" | "error_message">
): RealDataRefreshProgress {
  const scope = job.parameters_json?.scope === "family" ? "Family" : "Enzyme";
  const progress = realDataRefreshProgressDetails(job);
  const created = isRecordCountMap(job.result_summary_json?.created) ? job.result_summary_json.created : {};
  const sources = stringArray(job.result_summary_json?.sources);
  const summary =
    Object.values(created).some((count) => count > 0) || sources.length > 0
      ? formatRealDataRefreshSummary(created, sources)
      : null;
  if (job.status === "finished") {
    return {
      percent: 100,
      title: "Fetch real data complete",
      detail: `${scope} real-data refresh job ${job.id} finished.`,
      summary: formatRealDataRefreshSummary(created, sources),
      warnings: stringArray(job.result_summary_json?.warnings),
      ...progress,
      canPause: false
    };
  }
  if (job.status === "failed") {
    return {
      percent: 100,
      title: "Fetch real data failed",
      detail: job.error_message || `Real-data refresh job ${job.id} failed.`,
      summary: null,
      warnings: [],
      ...progress,
      canPause: false
    };
  }
  if (job.status === "cancelled") {
    return {
      percent: 100,
      title: "Fetch real data paused",
      detail: `${scope} real-data refresh job ${job.id} was paused. Saved records can be reviewed now.`,
      summary,
      warnings: stringArray(job.result_summary_json?.warnings),
      ...progress,
      canPause: false
    };
  }
  if (job.status === "running") {
    return {
      percent: realDataRefreshPercent(job.status, progress),
      title: "Fetching real data",
      detail: `${scope} real-data refresh job ${job.id} is collecting external records.`,
      summary,
      warnings: stringArray(job.result_summary_json?.warnings),
      ...progress,
      canPause: true
    };
  }
  return {
    percent: 15,
    title: "Fetch real data queued",
    detail: `${scope} real-data refresh job ${job.id} is waiting for the worker.`,
    summary: null,
    warnings: [],
    ...progress,
    canPause: true
  };
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

function realDataRefreshProgressDetails(
  job: Pick<JobResponse, "parameters_json" | "result_summary_json">
): Omit<RealDataRefreshProgress, "percent" | "title" | "detail" | "summary" | "warnings" | "canPause"> {
  const progress =
    isProgressRecord(job.result_summary_json?.progress) ? job.result_summary_json.progress
    : isProgressRecord(job.parameters_json?.progress) ? job.parameters_json.progress
    : null;
  return {
    checkedSources: numberFromProgress(progress?.checked_sources),
    foundRecords: numberFromProgress(progress?.found_records),
    notFoundSources: numberFromProgress(progress?.not_found_sources),
    processedEnzymes: numberFromProgress(progress?.processed_enzymes),
    totalEnzymes: numberFromProgress(progress?.total_enzymes),
    stage: typeof progress?.stage === "string" ? progress.stage : null,
    candidateArticles: numberFromProgress(progress?.candidate_articles),
    articlesScanned: numberFromProgress(progress?.articles_scanned),
    filteredArticles: numberFromProgress(progress?.filtered_articles),
    relevantArticles: numberFromProgress(progress?.relevant_articles),
    extractedRecords: numberFromProgress(progress?.extracted_records),
    candidatePapers: candidatePapersFromProgress(progress?.candidate_papers)
  };
}

function realDataRefreshPercent(
  status: string,
  progress: Pick<RealDataRefreshProgress, "checkedSources" | "totalEnzymes">
): number {
  if (status !== "running") {
    return status === "queued" ? 15 : 100;
  }
  const expectedChecks = Math.max(1, progress.totalEnzymes * 3);
  if (progress.checkedSources <= 0) {
    return 25;
  }
  return Math.min(95, Math.max(25, Math.round(20 + (progress.checkedSources / expectedChecks) * 90)));
}

function isProgressRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function numberFromProgress(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function isRecordCountMap(value: unknown): value is Record<string, number> {
  return (
    typeof value === "object" &&
    value !== null &&
    Object.values(value).every((item) => typeof item === "number")
  );
}

function stringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function candidatePapersFromProgress(value: unknown): CandidatePaperSummary[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.flatMap((item) => {
    if (typeof item !== "object" || item === null) {
      return [];
    }
    const record = item as Record<string, unknown>;
    if (typeof record.title !== "string" || !record.title.trim()) {
      return [];
    }
    return [
      {
        title: record.title.trim(),
        source: typeof record.source === "string" && record.source.trim() ? record.source.trim() : "-",
        year: typeof record.year === "number" && Number.isFinite(record.year) ? record.year : null,
        doi: typeof record.doi === "string" && record.doi.trim() ? record.doi.trim() : null,
        pubmedId: typeof record.pubmed_id === "string" && record.pubmed_id.trim() ? record.pubmed_id.trim() : null,
        relevanceScore:
          typeof record.relevance_score === "number" && Number.isFinite(record.relevance_score)
            ? record.relevance_score
            : null,
        decision: typeof record.decision === "string" && record.decision.trim() ? record.decision.trim() : null,
        reason: typeof record.reason === "string" && record.reason.trim() ? record.reason.trim() : null,
        extractedFields: stringArray(record.extracted_fields),
        missingFields: stringArray(record.missing_fields),
        extractionNotes: stringArray(record.extraction_notes)
      }
    ];
  });
}
