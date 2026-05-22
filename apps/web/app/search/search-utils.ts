import type { EnzymeSummary, PdbDiscoveryHit, SearchResponse } from "../../lib/types";

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
  return [match.organism, match.ec_number ? `EC ${match.ec_number}` : null, match.uniprot_id]
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
