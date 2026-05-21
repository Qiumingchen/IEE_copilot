import type { LiteratureReferenceRecord } from "../../../lib/types";

type ReferenceIdentifierFields = Pick<LiteratureReferenceRecord, "doi" | "pubmed_id">;

export function buildReferenceHref(reference: ReferenceIdentifierFields): string | null {
  if (reference.doi) {
    const doi = reference.doi.trim().replace(/^['"]|['"]$/g, "");
    const normalizedDoi = doi.replace(/^https?:\/\/doi\.org\//i, "").replace(/^doi:/i, "");
    return normalizedDoi ? `https://doi.org/${normalizedDoi}` : null;
  }
  const pubmedId = normalizePubmedId(reference.pubmed_id);
  return pubmedId ? `https://pubmed.ncbi.nlm.nih.gov/${pubmedId}/` : null;
}

export function formatReferenceIdentifier(reference: ReferenceIdentifierFields): string | null {
  if (reference.doi) {
    const doi = reference.doi.trim().replace(/^['"]|['"]$/g, "").toLowerCase();
    return doi.replace(/^https?:\/\/doi\.org\//, "").replace(/^doi:/, "").trim() || null;
  }
  const pubmedId = normalizePubmedId(reference.pubmed_id);
  return pubmedId ? `PMID ${pubmedId}` : null;
}

export function formatReferenceCitation(reference: LiteratureReferenceRecord): string {
  const parts = [
    formatReferenceIdentifier(reference),
    reference.title,
    reference.journal,
    reference.year ? String(reference.year) : null,
    reference.source
  ];
  return parts.filter(Boolean).join(" · ") || reference.id;
}

function normalizePubmedId(value: string | null | undefined): string {
  if (!value) {
    return "";
  }
  return Array.from(value.trim().replace(/^['"]|['"]$/g, "")).filter((character) =>
    /\d/.test(character)
  ).join("");
}
