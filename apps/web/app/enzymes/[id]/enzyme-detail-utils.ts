import type { LiteratureReferenceRecord } from "../../../lib/types";
import { formatReferenceCitation } from "./reference-utils.ts";

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
