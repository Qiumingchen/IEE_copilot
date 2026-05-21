import type { CuratedEvidenceImportResponse, VisibilityRequestDetailRecord } from "../../lib/types";

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
