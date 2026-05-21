export type EnzymeSummary = {
  id: string;
  family_id: string;
  name: string;
  organism: string | null;
  ec_number: string | null;
  uniprot_id: string | null;
  pdb_id: string | null;
  alphafold_id: string | null;
  source: string;
};

export type SearchResponse = {
  enzyme: EnzymeSummary;
  job_id: string;
  cache_status: string;
  query_kind: string;
  module: string;
};

export type TokenResponse = {
  access_token: string;
  token_type: string;
};

export type ProjectRecord = {
  id: string;
  owner_user_id: string;
  name: string;
  description: string | null;
  target_enzyme_module: string | null;
  default_visibility: string;
};

export type JobResponse = {
  id: string;
  project_id: string | null;
  enzyme_entry_id: string | null;
  job_type: string;
  status: string;
  parameters_json: Record<string, unknown> | null;
  result_summary_json: Record<string, unknown> | null;
  error_message: string | null;
  created_by: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
};

export type AnalysisArtifactRecord = {
  id: string;
  enzyme_entry_id: string | null;
  job_id: string | null;
  job_status: string | null;
  artifact_type: string;
  bucket: string;
  object_key: string;
  checksum: string | null;
  content_type: string | null;
  size_bytes: number | null;
  source: string;
  visibility: string;
  created_at: string;
  result_summary_json: Record<string, unknown> | null;
};

export type AnalysisArtifactContentRecord = {
  artifact_id: string;
  artifact_type: string;
  content_type: string | null;
  object_key: string;
  content_text: string | null;
  content_json: Record<string, unknown> | null;
};

export type AnalysisJobType =
  | "homolog_collection"
  | "msa"
  | "conservation_profile"
  | "mutation_recommendation"
  | "rosetta_ddg"
  | "library_design";

export type SubstrateRecord = {
  id: string;
  enzyme_family_id: string | null;
  enzyme_entry_id: string | null;
  user_experiment_id: string | null;
  name: string;
  substrate_class: string | null;
  smiles: string | null;
  inchi: string | null;
  metadata_json: Record<string, unknown> | null;
};

export type LigandRecord = {
  id: string;
  structure_entry_id: string;
  ligand_name: string;
  ligand_code: string | null;
  ligand_type: string;
  chain_id: string | null;
  residue_number: string | null;
  smiles: string | null;
  metadata_json: Record<string, unknown> | null;
};

export type StructureArtifactRecord = {
  id: string;
  bucket: string;
  object_key: string;
  checksum: string | null;
  content_type: string | null;
  size_bytes: number | null;
};

export type StructureRecord = {
  id: string;
  enzyme_entry_id: string;
  structure_type: string;
  complex_state: string;
  pdb_id: string | null;
  chain_summary: Record<string, unknown> | null;
  ligand_summary: Record<string, unknown> | null;
  artifact_id: string | null;
  artifact: StructureArtifactRecord | null;
  source: string;
  ligands: LigandRecord[];
};

export type PropertyRecord = {
  id: string;
  enzyme_entry_id: string;
  property_type: string;
  value_original: string;
  unit_original: string | null;
  value_standardized: string | null;
  unit_standardized: string | null;
  standardization_status: string;
  substrate: string | null;
  assay_temperature: string | null;
  assay_pH: string | null;
  buffer: string | null;
  method: string | null;
  reference_id: string | null;
  evidence_text: string | null;
  visibility: string;
  curation_status: string;
};

export type PropertyRankingMode = "reported_value" | "condition_grouped";

export type PropertyRankingItemRecord = {
  rank: number;
  property_record_id: string;
  enzyme_entry_id: string;
  enzyme_name: string;
  organism: string | null;
  value_original: string;
  unit_original: string | null;
  value_standardized: string | null;
  unit_standardized: string | null;
  substrate: string | null;
  assay_temperature: string | null;
  assay_pH: string | null;
  method: string | null;
  reference_id: string | null;
};

export type PropertyRankingGroupRecord = {
  condition_key: Record<string, string | null>;
  items: PropertyRankingItemRecord[];
};

export type PropertyRankingResponse = {
  property_type: string;
  ranking_mode: PropertyRankingMode;
  comparison_warnings: string[];
  items: PropertyRankingItemRecord[];
  groups: PropertyRankingGroupRecord[];
};

export type MutationPositionRecord = {
  wildtype: string;
  position: number;
  mutant: string;
};

export type MutationRecord = {
  id: string;
  enzyme_entry_id: string;
  parent_enzyme_entry_id: string | null;
  mutation_string: string;
  mutation_positions: MutationPositionRecord[];
  effect_summary: string | null;
  property_delta: Record<string, unknown> | null;
  substrate: string | null;
  assay_condition_summary: Record<string, unknown> | null;
  reference_id: string | null;
  is_user_uploaded: boolean;
  visibility: string;
  curation_status: string;
};

export type MutationQueryFilters = {
  position?: string;
  property_delta_key?: string;
  beneficial_only?: boolean;
  source?: string;
  visibility?: "public" | "private";
};

export type KineticRecord = {
  id: string;
  enzyme_entry_id: string;
  substrate: string | null;
  km: string | null;
  kcat: string | null;
  kcat_km: string | null;
  unit_original: string | null;
  assay_temperature: string | null;
  assay_pH: string | null;
  method: string | null;
  reference_id: string | null;
  visibility: string;
  curation_status: string;
};

export type LiteratureReferenceRecord = {
  id: string;
  title: string;
  authors: string | null;
  journal: string | null;
  year: number | null;
  doi: string | null;
  pubmed_id: string | null;
  source: string;
  provenance: Record<string, unknown> | null;
};

export type ExperimentCondition = {
  id: string;
  enzyme_entry_id: string | null;
  substrate_entry_id: string | null;
  assay_temperature: string | null;
  assay_pH: string | null;
  buffer: string | null;
  method: string | null;
  reference_id: string | null;
  metadata_json: Record<string, unknown> | null;
};

export type ExpressionRecord = {
  id: string;
  enzyme_entry_id: string;
  expression_host: string | null;
  vector: string | null;
  expression_level_original: string | null;
  expression_level_standardized: string | null;
  soluble_expression: string | null;
  unit_original: string | null;
  unit_standardized: string | null;
  condition_id: string | null;
  condition: ExperimentCondition | null;
  reference_id: string | null;
  visibility: string;
  curation_status: string;
};

export type ExperimentImportRequest = {
  project_id: string;
  csv_text?: string;
  file_name?: string;
  file_content_base64?: string;
};

export type ExperimentImportRecordPreview = {
  row_number: number;
  variant_name: string;
  mutation_string: string | null;
  sequence: string | null;
  measured_property: string;
  measured_value: string;
  unit: string | null;
  assay_condition_json: Record<string, string>;
  visibility: string;
};

export type ExperimentImportPreview = {
  fields: string[];
  row_count: number;
  record_count: number;
  records: ExperimentImportRecordPreview[];
};

export type ExperimentImportResult = {
  created_count: number;
  experiment_ids: string[];
};

export type CuratedEvidenceImportResponse = {
  created: Record<string, number>;
  reference_ids: string[];
  references: LiteratureReferenceRecord[];
  warnings: string[];
};

export type CuratedEvidencePreviewRecord = {
  row_number: number;
  record_type: string;
  summary: string;
  reference_key: string | null;
  reference_match_mode: string | null;
  evidence_text: string | null;
};

export type CuratedEvidencePreviewError = {
  row_number: number;
  field: string;
  message: string;
};

export type CuratedEvidencePreviewResponse = {
  fields: string[];
  row_count: number;
  record_counts: Record<string, number>;
  records: CuratedEvidencePreviewRecord[];
  errors: CuratedEvidencePreviewError[];
  warnings: string[];
  valid: boolean;
};

export type UserExperimentRecord = {
  id: string;
  project_id: string;
  enzyme_entry_id: string | null;
  variant_name: string;
  mutation_string: string | null;
  sequence: string | null;
  measured_property: string;
  measured_value: string;
  unit: string | null;
  assay_condition_json: Record<string, unknown> | null;
  visibility: string;
  curation_status: string;
  created_by: string;
};

export type VisibilityRequestRecord = {
  id: string;
  project_id: string;
  target_type: string;
  target_id: string;
  requested_visibility: string;
  status: string;
  requested_by: string;
  reviewed_by: string | null;
  review_comment: string | null;
};

export type VisibilityRequestDetailRecord = VisibilityRequestRecord & {
  experiment: UserExperimentRecord;
};

export type EnzymeRecordBundle = {
  enzyme: EnzymeSummary;
  substrates: SubstrateRecord[];
  structures: StructureRecord[];
  properties: PropertyRecord[];
  kinetics: KineticRecord[];
  expression: ExpressionRecord[];
};
