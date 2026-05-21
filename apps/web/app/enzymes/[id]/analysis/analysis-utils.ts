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
  scored_suggestions: ScoredMutationSuggestionView[];
  rationale: string;
};

export type MutationScoreComponentView = {
  name: string;
  value: number | string;
  weight: number | string;
  contribution: number | string;
  rationale: string;
};

export type ScoredMutationSuggestionView = {
  mutation_string: string;
  total_score: number | string;
  components: MutationScoreComponentView[];
  risk_summary: string[];
  parsed_mutations: Array<Record<string, number | string>>;
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
  member_scores: Array<{ mutation_string: string; total_score: number | string }>;
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

export function buildMutationLibraryWorkbookBytes(library: MutationLibraryView): Uint8Array {
  const variantRows = [
    ["variant_id", "mutation_string", "order", "score", "member_scores", "risk_flags", "reasons"],
    ...library.variants.map((variant) => [
      variant.variant_id,
      variant.mutation_string,
      String(variant.order),
      String(variant.score),
      formatMemberScores(variant.member_scores),
      variant.risk_flags.join("; "),
      variant.reasons.join("; ")
    ])
  ];
  const plateRows = [
    ["well", "variant_id", "mutation_string", "role", "score", "risk_flags"],
    ...library.plate_layout.map((well) => [
      well.well,
      well.variant_id,
      well.mutation_string,
      well.role,
      String(well.score),
      well.risk_flags.join("; ")
    ])
  ];
  const worksheetXml = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>
${worksheetRowsXml([
  ["Mutation library"],
  [`library_size: ${library.library_size}`, `plate_format: ${library.plate_format}`, `variant_count: ${library.variant_count}`],
  [],
  ["Variants"],
  ...variantRows,
  [],
  ["Plate layout"],
  ...plateRows
])}
  </sheetData>
</worksheet>`;

  return zipStore([
    {
      name: "[Content_Types].xml",
      content: `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>`
    },
    {
      name: "_rels/.rels",
      content: `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>`
    },
    {
      name: "xl/workbook.xml",
      content: `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="Library" sheetId="1" r:id="rId1"/>
  </sheets>
</workbook>`
    },
    {
      name: "xl/_rels/workbook.xml.rels",
      content: `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>`
    },
    {
      name: "xl/worksheets/sheet1.xml",
      content: worksheetXml
    }
  ]);
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
      scored_suggestions: getScoredSuggestions(candidate.scored_suggestions),
      rationale: String(valueOrDash(candidate.rationale))
    }));
}

function getScoredSuggestions(value: unknown): ScoredMutationSuggestionView[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .filter((suggestion): suggestion is Record<string, unknown> => (
      typeof suggestion === "object" && suggestion !== null
    ))
    .map((suggestion) => ({
      mutation_string: String(valueOrDash(suggestion.mutation_string)),
      total_score: valueOrDash(suggestion.total_score),
      components: getScoreComponents(suggestion.components),
      risk_summary: Array.isArray(suggestion.risk_summary) ? suggestion.risk_summary.map(String) : [],
      parsed_mutations: getParsedMutations(suggestion.parsed_mutations)
    }));
}

function getScoreComponents(value: unknown): MutationScoreComponentView[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .filter((component): component is Record<string, unknown> => (
      typeof component === "object" && component !== null
    ))
    .map((component) => ({
      name: String(valueOrDash(component.name)),
      value: valueOrDash(component.value),
      weight: valueOrDash(component.weight),
      contribution: valueOrDash(component.contribution),
      rationale: String(valueOrDash(component.rationale))
    }));
}

function getParsedMutations(value: unknown): Array<Record<string, number | string>> {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .filter((mutation): mutation is Record<string, unknown> => (
      typeof mutation === "object" && mutation !== null
    ))
    .map((mutation) => ({
      wildtype: valueOrDash(mutation.wildtype),
      position: valueOrDash(mutation.position),
      mutant: valueOrDash(mutation.mutant)
    }));
}

function getMemberScores(value: unknown): Array<{ mutation_string: string; total_score: number | string }> {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .filter((score): score is Record<string, unknown> => (
      typeof score === "object" && score !== null
    ))
    .map((score) => ({
      mutation_string: String(valueOrDash(score.mutation_string)),
      total_score: valueOrDash(score.total_score)
    }));
}

function formatMemberScores(memberScores: Array<{ mutation_string: string; total_score: number | string }>): string {
  return memberScores
    .map((memberScore) => `${memberScore.mutation_string}: ${memberScore.total_score}`)
    .join("; ");
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
          reasons: Array.isArray(variant.reasons) ? variant.reasons.map(String) : [],
          member_scores: getMemberScores(variant.member_scores)
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

function worksheetRowsXml(rows: string[][]): string {
  return rows
    .map((row, rowIndex) => {
      const cells = row
        .map((value, columnIndex) => {
          const ref = `${columnName(columnIndex + 1)}${rowIndex + 1}`;
          return `<c r="${ref}" t="inlineStr"><is><t>${escapeXml(value)}</t></is></c>`;
        })
        .join("");
      return `    <row r="${rowIndex + 1}">${cells}</row>`;
    })
    .join("\n");
}

function columnName(index: number): string {
  let name = "";
  let next = index;
  while (next > 0) {
    const remainder = (next - 1) % 26;
    name = String.fromCharCode(65 + remainder) + name;
    next = Math.floor((next - 1) / 26);
  }
  return name;
}

function escapeXml(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&apos;");
}

function zipStore(files: Array<{ name: string; content: string }>): Uint8Array {
  const encoder = new TextEncoder();
  const localParts: Uint8Array[] = [];
  const centralParts: Uint8Array[] = [];
  let offset = 0;

  for (const file of files) {
    const nameBytes = encoder.encode(file.name);
    const contentBytes = encoder.encode(file.content);
    const crc = crc32(contentBytes);
    const localHeader = concatBytes(
      u32(0x04034b50),
      u16(20),
      u16(0),
      u16(0),
      u16(0),
      u16(0),
      u32(crc),
      u32(contentBytes.length),
      u32(contentBytes.length),
      u16(nameBytes.length),
      u16(0),
      nameBytes
    );
    localParts.push(localHeader, contentBytes);

    centralParts.push(
      concatBytes(
        u32(0x02014b50),
        u16(20),
        u16(20),
        u16(0),
        u16(0),
        u16(0),
        u16(0),
        u32(crc),
        u32(contentBytes.length),
        u32(contentBytes.length),
        u16(nameBytes.length),
        u16(0),
        u16(0),
        u16(0),
        u16(0),
        u32(0),
        u32(offset),
        nameBytes
      )
    );
    offset += localHeader.length + contentBytes.length;
  }

  const centralDirectory = concatBytes(...centralParts);
  const endOfCentralDirectory = concatBytes(
    u32(0x06054b50),
    u16(0),
    u16(0),
    u16(files.length),
    u16(files.length),
    u32(centralDirectory.length),
    u32(offset),
    u16(0)
  );
  return concatBytes(...localParts, centralDirectory, endOfCentralDirectory);
}

function crc32(bytes: Uint8Array): number {
  let crc = 0xffffffff;
  for (const byte of bytes) {
    crc ^= byte;
    for (let bit = 0; bit < 8; bit += 1) {
      crc = (crc >>> 1) ^ (0xedb88320 & -(crc & 1));
    }
  }
  return (crc ^ 0xffffffff) >>> 0;
}

function u16(value: number): Uint8Array {
  return new Uint8Array([value & 0xff, (value >>> 8) & 0xff]);
}

function u32(value: number): Uint8Array {
  return new Uint8Array([
    value & 0xff,
    (value >>> 8) & 0xff,
    (value >>> 16) & 0xff,
    (value >>> 24) & 0xff
  ]);
}

function concatBytes(...chunks: Uint8Array[]): Uint8Array {
  const result = new Uint8Array(chunks.reduce((total, chunk) => total + chunk.length, 0));
  let offset = 0;
  for (const chunk of chunks) {
    result.set(chunk, offset);
    offset += chunk.length;
  }
  return result;
}
