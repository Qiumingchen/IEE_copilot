import type { ExperimentImportPreview, ExperimentImportRequest } from "../../../../lib/types";

export function buildExperimentImportRequest(
  projectId: string,
  csvText: string
): ExperimentImportRequest {
  return {
    project_id: projectId.trim(),
    csv_text: csvText
  };
}

export function summarizeExperimentPreview(preview: ExperimentImportPreview): string {
  return `${preview.row_count} rows, ${preview.record_count} measurements, ${preview.fields.length} fields`;
}
