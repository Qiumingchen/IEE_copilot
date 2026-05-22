import type { EnzymeSummary, SearchResponse } from "../../lib/types";

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
    .join(" · ") || "Source details not reported";
}
