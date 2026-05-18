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
