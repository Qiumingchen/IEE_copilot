import type { AnalysisArtifactContentRecord } from "../../../../lib/types";

export type ConservationSiteView = {
  query_position: number | string;
  wildtype_residue: string;
  shannon_entropy: number | string;
  wildtype_frequency: number | string;
  conservation_category: string;
};

export type ConservationCategoryFilter =
  | "all"
  | "highly_conserved"
  | "moderately_conserved"
  | "variable";

export function getConservationSites(content: AnalysisArtifactContentRecord): ConservationSiteView[] {
  const rawSites = content.content_json?.sites;
  if (!Array.isArray(rawSites)) {
    return [];
  }
  return rawSites
    .filter((site): site is Record<string, unknown> => typeof site === "object" && site !== null)
    .map((site) => ({
      query_position: valueOrDash(site.query_position),
      wildtype_residue: String(valueOrDash(site.wildtype_residue)),
      shannon_entropy: valueOrDash(site.shannon_entropy),
      wildtype_frequency: valueOrDash(site.wildtype_frequency),
      conservation_category: String(valueOrDash(site.conservation_category))
    }));
}

export function filterConservationSites(
  sites: ConservationSiteView[],
  category: ConservationCategoryFilter
): ConservationSiteView[] {
  if (category === "all") {
    return sites;
  }
  return sites.filter((site) => site.conservation_category === category);
}

export function buildConservationDownloadJson(
  content: AnalysisArtifactContentRecord,
  sites: ConservationSiteView[]
): string {
  return JSON.stringify(
    {
      artifact_id: content.artifact_id,
      artifact_type: content.artifact_type,
      content_type: content.content_type,
      object_key: content.object_key,
      sites
    },
    null,
    2
  );
}

function valueOrDash(value: unknown): string | number {
  if (typeof value === "number" || typeof value === "string") {
    return value;
  }
  return "-";
}
