import type {
  AnalysisArtifactContentRecord,
  AnalysisArtifactRecord,
  AnalysisJobType,
  EnzymeRecordBundle,
  EnzymeSummary,
  ExpressionRecord,
  ExperimentImportPreview,
  ExperimentImportRequest,
  ExperimentImportResult,
  JobResponse,
  KineticRecord,
  PropertyRecord,
  ProjectRecord,
  SearchResponse,
  StructureRecord,
  SubstrateRecord,
  TokenResponse,
  UserExperimentRecord,
  VisibilityRequestDetailRecord,
  VisibilityRequestRecord
} from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export async function login(email: string, password: string): Promise<TokenResponse> {
  const response = await fetch(`${API_BASE}/auth/login`, {
    method: "POST",
    headers: {
      "content-type": "application/json"
    },
    body: JSON.stringify({ email, password })
  });

  if (!response.ok) {
    throw new Error(`Login failed with status ${response.status}`);
  }

  return response.json() as Promise<TokenResponse>;
}

export async function searchEnzyme(query: string, token: string): Promise<SearchResponse> {
  const response = await fetch(`${API_BASE}/enzymes/search`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      authorization: `Bearer ${token}`
    },
    body: JSON.stringify({ query })
  });

  if (!response.ok) {
    throw new Error(`Search failed with status ${response.status}`);
  }

  return response.json() as Promise<SearchResponse>;
}

async function fetchWithToken<T>(path: string, token: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "content-type": "application/json",
      authorization: `Bearer ${token}`,
      ...init?.headers
    }
  });

  if (!response.ok) {
    throw new Error(`API request failed with status ${response.status}`);
  }

  return response.json() as Promise<T>;
}

async function fetchWithTokenAndErrorMessage<T>(
  path: string,
  token: string,
  init?: RequestInit
): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "content-type": "application/json",
      authorization: `Bearer ${token}`,
      ...init?.headers
    }
  });

  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as
      | { error?: { message?: string } }
      | null;
    throw new Error(body?.error?.message ?? `API request failed with status ${response.status}`);
  }

  return response.json() as Promise<T>;
}

export async function getEnzyme(enzymeId: string, token: string): Promise<EnzymeSummary> {
  return fetchWithToken<EnzymeSummary>(`/enzymes/${enzymeId}`, token);
}

export async function listProjects(token: string): Promise<ProjectRecord[]> {
  return fetchWithToken<ProjectRecord[]>("/projects", token);
}

export async function listProjectExperiments(
  projectId: string,
  token: string
): Promise<UserExperimentRecord[]> {
  return fetchWithTokenAndErrorMessage<UserExperimentRecord[]>(
    `/projects/${projectId}/experiments`,
    token
  );
}

export async function getEnzymeRecordBundle(
  enzymeId: string,
  token: string
): Promise<EnzymeRecordBundle> {
  const [enzyme, substrates, structures, properties, kinetics, expression] = await Promise.all([
    getEnzyme(enzymeId, token),
    fetchWithToken<SubstrateRecord[]>(`/enzymes/${enzymeId}/substrates`, token),
    fetchWithToken<StructureRecord[]>(`/enzymes/${enzymeId}/structures`, token),
    fetchWithToken<PropertyRecord[]>(`/enzymes/${enzymeId}/properties`, token),
    fetchWithToken<KineticRecord[]>(`/enzymes/${enzymeId}/kinetics`, token),
    fetchWithToken<ExpressionRecord[]>(`/enzymes/${enzymeId}/expression`, token)
  ]);

  return { enzyme, substrates, structures, properties, kinetics, expression };
}

export async function getAnalysisArtifacts(
  enzymeId: string,
  token: string
): Promise<AnalysisArtifactRecord[]> {
  return fetchWithToken<AnalysisArtifactRecord[]>(`/enzymes/${enzymeId}/analysis-artifacts`, token);
}

export async function getAnalysisArtifactContent(
  enzymeId: string,
  artifactId: string,
  token: string
): Promise<AnalysisArtifactContentRecord> {
  return fetchWithToken<AnalysisArtifactContentRecord>(
    `/enzymes/${enzymeId}/analysis-artifacts/${artifactId}/content`,
    token
  );
}

export async function createAnalysisJob(
  enzymeId: string,
  token: string,
  jobType: AnalysisJobType,
  parametersJson?: Record<string, unknown>
): Promise<JobResponse> {
  return fetchWithToken<JobResponse>(`/enzymes/${enzymeId}/analysis-jobs`, token, {
    method: "POST",
    body: JSON.stringify({
      job_type: jobType,
      ...(parametersJson ? { parameters_json: parametersJson } : {})
    })
  });
}

export async function listJobs(token: string): Promise<JobResponse[]> {
  return fetchWithToken<JobResponse[]>("/jobs", token);
}

export async function retryJob(jobId: string, token: string): Promise<JobResponse> {
  return fetchWithToken<JobResponse>(`/jobs/${jobId}/retry`, token, {
    method: "POST"
  });
}

export async function createSubstrate(
  enzymeId: string,
  token: string,
  payload: {
    name: string;
    substrate_class?: string;
    smiles?: string;
  }
): Promise<SubstrateRecord> {
  return fetchWithToken<SubstrateRecord>(`/enzymes/${enzymeId}/substrates`, token, {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function createPropertyRecord(
  enzymeId: string,
  token: string,
  payload: {
    property_type: string;
    value_original: string;
    unit_original?: string;
    substrate?: string;
    assay_temperature?: string;
    assay_pH?: string;
  }
): Promise<PropertyRecord> {
  return fetchWithToken<PropertyRecord>(`/enzymes/${enzymeId}/properties`, token, {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function createStructureRecord(
  enzymeId: string,
  token: string,
  payload: {
    structure_type: string;
    complex_state?: string;
    pdb_id?: string;
    source?: string;
    ligands?: Array<{
      ligand_name: string;
      ligand_code?: string;
      ligand_type?: string;
      smiles?: string;
    }>;
  }
): Promise<StructureRecord> {
  return fetchWithToken<StructureRecord>(`/enzymes/${enzymeId}/structures`, token, {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function uploadStructureFile(
  enzymeId: string,
  token: string,
  file: File
): Promise<StructureRecord> {
  const formData = new FormData();
  formData.append("file", file);
  const response = await fetch(`${API_BASE}/enzymes/${enzymeId}/structures/upload`, {
    method: "POST",
    headers: {
      authorization: `Bearer ${token}`
    },
    body: formData
  });

  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as
      | { error?: { message?: string } }
      | null;
    throw new Error(body?.error?.message ?? `Structure upload failed with status ${response.status}`);
  }

  return response.json() as Promise<StructureRecord>;
}

export async function createKineticRecord(
  enzymeId: string,
  token: string,
  payload: {
    substrate?: string;
    km?: string;
    kcat?: string;
    kcat_km?: string;
    unit_original?: string;
    assay_temperature?: string;
    assay_pH?: string;
  }
): Promise<KineticRecord> {
  return fetchWithToken<KineticRecord>(`/enzymes/${enzymeId}/kinetics`, token, {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function createExpressionRecord(
  enzymeId: string,
  token: string,
  payload: {
    expression_host?: string;
    vector?: string;
    expression_level_original?: string;
    expression_level_standardized?: string;
    soluble_expression?: string;
    unit_original?: string;
    unit_standardized?: string;
    condition?: {
      substrate_entry_id?: string;
      assay_temperature?: string;
      assay_pH?: string;
      buffer?: string;
      method?: string;
    };
  }
): Promise<ExpressionRecord> {
  return fetchWithToken<ExpressionRecord>(`/enzymes/${enzymeId}/expression`, token, {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function previewExperimentImport(
  enzymeId: string,
  token: string,
  payload: ExperimentImportRequest
): Promise<ExperimentImportPreview> {
  return fetchWithTokenAndErrorMessage<ExperimentImportPreview>(
    `/enzymes/${enzymeId}/experiments/import-preview`,
    token,
    {
      method: "POST",
      body: JSON.stringify(payload)
    }
  );
}

export async function importExperiments(
  enzymeId: string,
  token: string,
  payload: ExperimentImportRequest
): Promise<ExperimentImportResult> {
  return fetchWithTokenAndErrorMessage<ExperimentImportResult>(
    `/enzymes/${enzymeId}/experiments/import`,
    token,
    {
      method: "POST",
      body: JSON.stringify(payload)
    }
  );
}

export async function requestExperimentVisibility(
  experimentId: string,
  token: string
): Promise<VisibilityRequestRecord> {
  return fetchWithTokenAndErrorMessage<VisibilityRequestRecord>(
    `/experiments/${experimentId}/visibility-requests`,
    token,
    {
      method: "POST",
      body: JSON.stringify({ requested_visibility: "public" })
    }
  );
}

export async function listVisibilityRequests(
  token: string
): Promise<VisibilityRequestDetailRecord[]> {
  return fetchWithTokenAndErrorMessage<VisibilityRequestDetailRecord[]>(
    "/curation/visibility-requests",
    token
  );
}

export async function approveVisibilityRequest(
  requestId: string,
  token: string
): Promise<VisibilityRequestRecord> {
  return fetchWithTokenAndErrorMessage<VisibilityRequestRecord>(
    `/curation/visibility-requests/${requestId}/approve`,
    token,
    { method: "POST" }
  );
}

export async function rejectVisibilityRequest(
  requestId: string,
  token: string,
  reviewComment: string
): Promise<VisibilityRequestRecord> {
  return fetchWithTokenAndErrorMessage<VisibilityRequestRecord>(
    `/curation/visibility-requests/${requestId}/reject`,
    token,
    {
      method: "POST",
      body: JSON.stringify({ review_comment: reviewComment })
    }
  );
}
