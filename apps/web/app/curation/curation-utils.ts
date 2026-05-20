import type { VisibilityRequestDetailRecord } from "../../lib/types";

export function summarizeVisibilityRequest(request: VisibilityRequestDetailRecord): string {
  const experiment = request.experiment;
  const mutation = experiment.mutation_string || "WT";
  const unit = experiment.unit ? ` ${experiment.unit}` : "";
  return `${experiment.variant_name} · ${mutation} · ${experiment.measured_property} ${experiment.measured_value}${unit}`;
}

export function canSubmitRejection(reviewComment: string): boolean {
  return reviewComment.trim().length > 0;
}
