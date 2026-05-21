import type { LiteratureReferenceRecord } from "../../../lib/types";

export function formatReferenceForTable(
  referenceId: string | null | undefined,
  referencesById: Record<string, LiteratureReferenceRecord>
): string {
  if (!referenceId) {
    return "-";
  }
  const reference = referencesById[referenceId];
  if (!reference) {
    return referenceId;
  }
  const identifier = reference.doi || (reference.pubmed_id ? `PMID ${reference.pubmed_id}` : null);
  const label = [identifier, reference.title].filter(Boolean).join(" · ") || reference.id;
  return `${label} · ${reference.source}`;
}

export function formatVisibilityStatus(
  visibility: string | null | undefined,
  curationStatus: string | null | undefined
): string {
  return [visibility, curationStatus].filter(Boolean).join(" / ") || "-";
}
