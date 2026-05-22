import type {
  CuratedEvidenceImportResponse,
  CuratedEvidencePreviewResponse,
  LiteratureReferenceRecord,
  VisibilityRequestDetailRecord
} from "../../lib/types";

export const curatedEvidenceCsvTemplate = [
  "record_type,property_type,value_original,unit_original,substrate,assay_temperature,assay_pH,method,km,kcat,kcat_km,mutation_string,effect_summary,property_delta_key,property_delta_value,doi,pubmed_id,reference_title,journal,year,evidence_text,source",
  "property,optimal_temperature,58,degC,casein,37,7.0,activity assay,,,,,,,10.1000/example,,Example MTGase paper,Biocatalysis Reports,2024,Optimum temperature reported in Table 1,curated_literature",
  "kinetic,,,,CBZ-Gln-Gly,37,7.0,HPLC,2.1,31,14.8,,,,10.1000/example,,Example MTGase paper,Biocatalysis Reports,2024,Km and kcat reported in Table 2,curated_literature",
  "mutation,,,,casein,50,7.0,thermal assay,,,,S2P,Improved thermostability,optimal_temperature_delta_degC,5,10.1000/example,,Example MTGase paper,Biocatalysis Reports,2024,S2P increased thermal half-life,curated_literature"
].join("\n");

export const curatedEvidenceTemplateFileName = "curated-evidence-template.csv";

export const curatedEvidenceCsvUploadAccept = ".csv,text/csv";

export function buildCuratedEvidenceTemplateCsv(): string {
  return `${curatedEvidenceCsvTemplate}\n`;
}

export function isCuratedEvidenceCsvFileName(fileName: string): boolean {
  return fileName.trim().toLowerCase().endsWith(".csv");
}

export function summarizeCuratedEvidenceFileLoad(fileName: string): string {
  return `Loaded ${fileName} into CSV text.`;
}

export function summarizeVisibilityRequest(request: VisibilityRequestDetailRecord): string {
  const experiment = request.experiment;
  const mutation = experiment.mutation_string || "WT";
  const unit = experiment.unit ? ` ${experiment.unit}` : "";
  return `${experiment.variant_name} · ${mutation} · ${experiment.measured_property} ${experiment.measured_value}${unit}`;
}

export function canSubmitRejection(reviewComment: string): boolean {
  return reviewComment.trim().length > 0;
}

export function summarizeCuratedEvidenceImport(result: CuratedEvidenceImportResponse): string {
  const propertyCount = result.created.properties ?? 0;
  const kineticCount = result.created.kinetics ?? 0;
  const mutationCount = result.created.mutations ?? 0;
  return `Created ${propertyCount} property, ${kineticCount} kinetic, ${mutationCount} mutation records from ${result.reference_ids.length} references.`;
}

export function formatImportedReference(reference: LiteratureReferenceRecord): string {
  const pubmedId = normalizePubmedIdForDisplay(reference.pubmed_id);
  const identifier = normalizeDoiForDisplay(reference.doi) || (pubmedId ? `PMID ${pubmedId}` : null);
  const label = [identifier, reference.title].filter(Boolean).join(" · ") || reference.id;
  return `${label} · ${reference.source}`;
}

export function formatPreviewReference(record: {
  reference_key: string | null;
  reference_match_mode: string | null;
}): string {
  if (!record.reference_key) {
    return "-";
  }
  const matchModeLabels: Record<string, string> = {
    doi: "DOI",
    pubmed_id: "PMID",
    title_year_source: "title/year/source"
  };
  const matchMode = record.reference_match_mode
    ? (matchModeLabels[record.reference_match_mode] ?? record.reference_match_mode)
    : null;
  return [record.reference_key, matchMode].filter(Boolean).join(" · ");
}

export function normalizeDoiForDisplay(value: string | null | undefined): string {
  if (!value) {
    return "";
  }
  let doi = value.trim().replace(/^['"]|['"]$/g, "").toLowerCase();
  for (const prefix of ["https://doi.org/", "http://doi.org/", "doi:"]) {
    if (doi.startsWith(prefix)) {
      doi = doi.slice(prefix.length);
    }
  }
  return doi.trim();
}

export function normalizePubmedIdForDisplay(value: string | null | undefined): string {
  if (!value) {
    return "";
  }
  const normalized = value.trim().replace(/^['"]|['"]$/g, "").toLowerCase();
  return Array.from(normalized).filter((character) => /\d/.test(character)).join("");
}

export function summarizeCuratedEvidencePreview(preview: CuratedEvidencePreviewResponse): string {
  const propertyCount = preview.record_counts.properties ?? 0;
  const kineticCount = preview.record_counts.kinetics ?? 0;
  const mutationCount = preview.record_counts.mutations ?? 0;
  const errorCount = preview.errors.length;
  const warningCount = preview.warnings.length;
  const errorSummary =
    errorCount > 0 ? ` ${errorCount} validation ${errorCount === 1 ? "error" : "errors"}.` : "";
  const warningSummary =
    warningCount > 0 ? ` ${warningCount} ${warningCount === 1 ? "warning" : "warnings"}.` : "";
  return `${preview.row_count} rows parsed: ${propertyCount} property, ${kineticCount} kinetic, ${mutationCount} mutation records.${errorSummary}${warningSummary}`;
}
