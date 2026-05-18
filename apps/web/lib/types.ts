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

export type StructureRecord = {
  id: string;
  enzyme_entry_id: string;
  structure_type: string;
  complex_state: string;
  pdb_id: string | null;
  chain_summary: Record<string, unknown> | null;
  ligand_summary: Record<string, unknown> | null;
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

export type EnzymeRecordBundle = {
  enzyme: EnzymeSummary;
  substrates: SubstrateRecord[];
  structures: StructureRecord[];
  properties: PropertyRecord[];
  kinetics: KineticRecord[];
  expression: ExpressionRecord[];
};
