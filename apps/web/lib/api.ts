import type {
  EnzymeRecordBundle,
  EnzymeSummary,
  ExpressionRecord,
  KineticRecord,
  PropertyRecord,
  SearchResponse,
  StructureRecord,
  SubstrateRecord,
  TokenResponse
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

export async function getEnzyme(enzymeId: string, token: string): Promise<EnzymeSummary> {
  return fetchWithToken<EnzymeSummary>(`/enzymes/${enzymeId}`, token);
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
