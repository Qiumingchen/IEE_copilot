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

export function buildExperimentUploadRequest(
  projectId: string,
  fileName: string,
  fileContentBase64: string
): ExperimentImportRequest {
  return {
    project_id: projectId.trim(),
    file_name: fileName,
    file_content_base64: fileContentBase64
  };
}

export function arrayBufferToBase64(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (const byte of bytes) {
    binary += String.fromCharCode(byte);
  }
  return btoa(binary);
}

export function summarizeExperimentPreview(preview: ExperimentImportPreview): string {
  return `${preview.row_count} rows, ${preview.record_count} measurements, ${preview.fields.length} fields`;
}
