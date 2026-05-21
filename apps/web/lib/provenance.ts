export type ProvenanceRecord = {
  provider?: unknown;
  mode?: unknown;
  retrieved_at?: unknown;
  source_url?: unknown;
  warning?: unknown;
  version?: unknown;
  [key: string]: unknown;
};

export type ProvenanceTone = "real" | "fallback" | "unknown";

export function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

export function provenanceFromRecord(
  record: Record<string, unknown> | null | undefined,
  field: string
): ProvenanceRecord | null {
  const nested = record?.[field];
  if (!isRecord(nested)) {
    return null;
  }
  const provenance = nested.provenance;
  return isRecord(provenance) ? provenance : null;
}

export function formatProvenanceLabel(provenance: ProvenanceRecord | null | undefined): string {
  if (!provenance) {
    return "source unknown";
  }

  const provider = typeof provenance.provider === "string" && provenance.provider.length > 0
    ? provenance.provider
    : "provider";
  const mode = typeof provenance.mode === "string" && provenance.mode.length > 0
    ? provenance.mode
    : "unknown";
  const retrievedAt = typeof provenance.retrieved_at === "string" && provenance.retrieved_at.length > 0
    ? ` / ${provenance.retrieved_at}`
    : "";
  return `${provider} ${mode}${retrievedAt}`;
}

export function getProvenanceModeTone(provenance: Pick<ProvenanceRecord, "mode"> | null): ProvenanceTone {
  if (provenance?.mode === "real") {
    return "real";
  }
  if (provenance?.mode === "fallback") {
    return "fallback";
  }
  return "unknown";
}

export function provenanceUrl(provenance: ProvenanceRecord | null | undefined): string | null {
  return typeof provenance?.source_url === "string" && provenance.source_url.length > 0
    ? provenance.source_url
    : null;
}

export function provenanceWarning(provenance: ProvenanceRecord | null | undefined): string | null {
  return typeof provenance?.warning === "string" && provenance.warning.length > 0
    ? provenance.warning
    : null;
}
