import type { AnalysisArtifactContentRecord, JobResponse } from "../../../../lib/types";

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

export type MutationRecommendationCandidateView = {
  query_position: number | string;
  wildtype_residue: string;
  conservation_category: string;
  priority_score: number | string;
  suggested_mutations: string[];
  rationale: string;
};

export type RosettaDdgResultView = {
  mutation_string: string;
  mutation_file: string;
  ddg_kcal_per_mol: number | string;
  interpretation: string;
  structure_id: string;
  runner: string;
};

export type RosettaDdgRunView = {
  job_id: string;
  status: string;
  mutation_string: string;
  mutation_file: string;
  ddg_kcal_per_mol: number | string;
  interpretation: string;
  runner: string;
  error_message: string;
  can_retry: boolean;
  created_at: string;
  finished_at: string | null;
};

export type MutationLibraryVariantView = {
  variant_id: string;
  mutation_string: string;
  order: number | string;
  score: number | string;
  risk_flags: string[];
  reasons: string[];
};

export type MutationLibraryPlateWellView = {
  well: string;
  variant_id: string;
  mutation_string: string;
  role: string;
  score: number | string;
  risk_flags: string[];
};

export type MutationLibraryView = {
  library_size: number | string;
  plate_format: number | string;
  variant_count: number | string;
  variants: MutationLibraryVariantView[];
  plate_layout: MutationLibraryPlateWellView[];
  csv_text: string;
};

export function buildLibraryDesignParameters(
  librarySize: number,
  maxOrder: number,
  plateFormat: number
): Record<string, number> {
  return {
    library_size: librarySize,
    max_order: maxOrder,
    plate_format: plateFormat
  };
}

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

export function getMutationRecommendationCandidates(
  content: AnalysisArtifactContentRecord
): MutationRecommendationCandidateView[] {
  const rawCandidates = content.content_json?.candidates;
  if (!Array.isArray(rawCandidates)) {
    return [];
  }
  return rawCandidates
    .filter((candidate): candidate is Record<string, unknown> => (
      typeof candidate === "object" && candidate !== null
    ))
    .map((candidate) => ({
      query_position: valueOrDash(candidate.query_position),
      wildtype_residue: String(valueOrDash(candidate.wildtype_residue)),
      conservation_category: String(valueOrDash(candidate.conservation_category)),
      priority_score: valueOrDash(candidate.priority_score),
      suggested_mutations: Array.isArray(candidate.suggested_mutations)
        ? candidate.suggested_mutations.map(String)
        : [],
      rationale: String(valueOrDash(candidate.rationale))
    }));
}

export function getRosettaDdgResults(content: AnalysisArtifactContentRecord): RosettaDdgResultView[] {
  if (content.artifact_type !== "rosetta_ddg" || !content.content_json) {
    return [];
  }
  const mutationString = content.content_json.mutation_string;
  if (typeof mutationString !== "string" || mutationString.length === 0) {
    return [];
  }
  return [
    {
      mutation_string: mutationString,
      mutation_file: String(valueOrDash(content.content_json.mutation_file)),
      ddg_kcal_per_mol: valueOrDash(content.content_json.ddg_kcal_per_mol),
      interpretation: String(valueOrDash(content.content_json.interpretation)),
      structure_id: String(valueOrDash(content.content_json.structure_id)),
      runner: String(valueOrDash(content.content_json.runner))
    }
  ];
}

export function getRosettaDdgRunViews(
  jobs: JobResponse[],
  enzymeId: string
): RosettaDdgRunView[] {
  return jobs
    .filter((job) => job.enzyme_entry_id === enzymeId && job.job_type === "rosetta_ddg")
    .map((job) => {
      const parameters = job.parameters_json ?? {};
      const summary = job.result_summary_json ?? {};
      const mutationString = valueOrDash(summary.mutation_string ?? parameters.mutation_string);
      return {
        job_id: job.id,
        status: job.status,
        mutation_string: String(mutationString),
        mutation_file: String(valueOrDash(summary.mutation_file)),
        ddg_kcal_per_mol: valueOrDash(summary.ddg_kcal_per_mol),
        interpretation: String(valueOrDash(summary.interpretation)),
        runner: String(valueOrDash(summary.runner)),
        error_message: String(valueOrDash(job.error_message)),
        can_retry: job.status === "failed",
        created_at: job.created_at,
        finished_at: job.finished_at
      };
    });
}

export function getMutationLibrary(content: AnalysisArtifactContentRecord): MutationLibraryView | null {
  if (content.artifact_type !== "mutation_library" || !content.content_json) {
    return null;
  }
  const rawVariants = content.content_json.variants;
  const rawPlateLayout = content.content_json.plate_layout;
  return {
    library_size: valueOrDash(content.content_json.library_size),
    plate_format: valueOrDash(content.content_json.plate_format),
    variant_count: valueOrDash(content.content_json.variant_count),
    variants: Array.isArray(rawVariants)
      ? rawVariants
        .filter((variant): variant is Record<string, unknown> => (
          typeof variant === "object" && variant !== null
        ))
        .map((variant) => ({
          variant_id: String(valueOrDash(variant.variant_id)),
          mutation_string: String(valueOrDash(variant.mutation_string)),
          order: valueOrDash(variant.order),
          score: valueOrDash(variant.score),
          risk_flags: Array.isArray(variant.risk_flags) ? variant.risk_flags.map(String) : [],
          reasons: Array.isArray(variant.reasons) ? variant.reasons.map(String) : []
        }))
      : [],
    plate_layout: Array.isArray(rawPlateLayout)
      ? rawPlateLayout
        .filter((well): well is Record<string, unknown> => (
          typeof well === "object" && well !== null
        ))
        .map((well) => ({
          well: String(valueOrDash(well.well)),
          variant_id: String(valueOrDash(well.variant_id)),
          mutation_string: String(valueOrDash(well.mutation_string)),
          role: String(valueOrDash(well.role)),
          score: valueOrDash(well.score),
          risk_flags: Array.isArray(well.risk_flags) ? well.risk_flags.map(String) : []
        }))
      : [],
    csv_text: typeof content.content_json.csv_text === "string" ? content.content_json.csv_text : ""
  };
}

function valueOrDash(value: unknown): string | number {
  if (typeof value === "number" || typeof value === "string") {
    return value;
  }
  return "-";
}
