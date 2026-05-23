import type { EnzymeSummary, PdbDiscoveryHit, SearchResponse } from "../../lib/types";

export type ApiErrorLike = {
  status?: number;
  detail?: string | null;
  message?: string;
};

export function searchResultMatches(result: SearchResponse): EnzymeSummary[] {
  const seen = new Set<string>();
  const matches = result.matches.length > 0 ? result.matches : [result.enzyme];
  return matches.filter((match) => {
    if (seen.has(match.id)) {
      return false;
    }
    seen.add(match.id);
    return true;
  });
}

export function formatSearchMatchSubtitle(match: EnzymeSummary): string {
  return [
    match.organism,
    match.ec_number ? `EC ${match.ec_number}` : null,
    match.uniprot_id ? `UniProt ${match.uniprot_id}` : null,
    match.pdb_id ? `RCSB PDB ${match.pdb_id}` : null,
    match.alphafold_id ? `AlphaFold ${match.alphafold_id}` : null
  ]
    .filter(Boolean)
    .join(" | ") || "Source details not reported";
}

export function formatPdbDiscoveryHitSubtitle(hit: PdbDiscoveryHit): string {
  return [
    `${(hit.identity * 100).toFixed(1)}% identity`,
    `${(hit.coverage * 100).toFixed(1)}% coverage`,
    `${hit.confidence} confidence`,
    hit.evidence.join(", ")
  ]
    .filter(Boolean)
    .join(" | ");
}

export function buildStructureAnalysisHref(enzymeId: string, structureId: string): string {
  return `/enzymes/${encodeURIComponent(enzymeId)}/structures?structure_id=${encodeURIComponent(structureId)}`;
}

export function pdbDiscoveryErrorMessage(error: ApiErrorLike): string {
  if (error.status === 401) {
    return "Your login session has expired. Please sign in again before uploading a PDB file.";
  }
  if (error.status === 422) {
    return error.detail ?? "The uploaded file could not be parsed as a protein PDB or mmCIF structure.";
  }
  return error.message ?? "PDB discovery failed. Please confirm the API is running.";
}
