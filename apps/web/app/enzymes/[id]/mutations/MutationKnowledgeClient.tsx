"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useMemo, useState } from "react";

import { getEnzyme, listEnzymeReferences, listMutationRecords } from "../../../../lib/api";
import type {
  EnzymeSummary,
  LiteratureReferenceRecord,
  MutationQueryFilters,
  MutationRecord
} from "../../../../lib/types";
import {
  buildMutationPositionSummary,
  buildMutationDeltaSummary,
  buildMutationPropertyDeltaOptions,
  buildMutationEvidenceCsv,
  filterMutationEvidenceRecords,
  formatMutationPositions,
  formatPropertyDelta
} from "./mutation-knowledge-utils";
import { ReferenceCitation } from "../ReferenceCitation";

const TOKEN_KEY = "iee-copilot-token";

type MutationKnowledgeClientProps = {
  enzymeId: string;
};

function emptyFilters(): MutationQueryFilters {
  return {
    position: "",
    property_delta_key: "",
    beneficial_only: false,
    source: "",
    visibility: "public"
  };
}

export default function MutationKnowledgeClient({ enzymeId }: MutationKnowledgeClientProps) {
  const router = useRouter();
  const [token, setToken] = useState<string | null>(null);
  const [enzyme, setEnzyme] = useState<EnzymeSummary | null>(null);
  const [mutations, setMutations] = useState<MutationRecord[]>([]);
  const [referencesById, setReferencesById] = useState<Record<string, LiteratureReferenceRecord>>({});
  const [filters, setFilters] = useState<MutationQueryFilters>(emptyFilters);
  const [evidenceCurationStatus, setEvidenceCurationStatus] = useState("");
  const [evidenceReferenceSource, setEvidenceReferenceSource] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const mutationsWithFallbackReferences = useMemo(
    () =>
      mutations.map((record) => ({
        ...record,
        reference: record.reference ?? referencesById[record.reference_id ?? ""] ?? null
      })),
    [mutations, referencesById]
  );
  const filteredMutations = useMemo(
    () =>
      filterMutationEvidenceRecords(mutationsWithFallbackReferences, {
        referenceSource: evidenceReferenceSource,
        curationStatus: evidenceCurationStatus
      }),
    [evidenceCurationStatus, evidenceReferenceSource, mutationsWithFallbackReferences]
  );
  const referenceSourceOptions = useMemo(() => {
    const sources = new Set(
      mutationsWithFallbackReferences
        .map((record) => {
          if (record.reference?.source) {
            return record.reference.source;
          }
          return typeof record.assay_condition_summary?.source === "string"
            ? record.assay_condition_summary.source
            : "";
        })
        .filter(Boolean)
    );
    return Array.from(sources).sort((left, right) => left.localeCompare(right));
  }, [mutationsWithFallbackReferences]);
  const positionSummary = useMemo(() => buildMutationPositionSummary(filteredMutations), [filteredMutations]);
  const deltaSummary = useMemo(() => buildMutationDeltaSummary(filteredMutations), [filteredMutations]);
  const propertyDeltaOptions = useMemo(
    () => buildMutationPropertyDeltaOptions(mutationsWithFallbackReferences),
    [mutationsWithFallbackReferences]
  );
  const maxPositionCount = Math.max(1, ...positionSummary.map((item) => item.count));

  useEffect(() => {
    const storedToken = window.localStorage.getItem(TOKEN_KEY);
    if (!storedToken) {
      router.replace("/login");
      return;
    }
    setToken(storedToken);
    void loadPage(storedToken, filters);
  }, [enzymeId, router]);

  async function loadPage(nextToken: string, nextFilters: MutationQueryFilters) {
    setError(null);
    setIsLoading(true);
    try {
      const [nextEnzyme, nextMutations, references] = await Promise.all([
        getEnzyme(enzymeId, nextToken),
        listMutationRecords(enzymeId, nextToken, nextFilters),
        listEnzymeReferences(enzymeId, nextToken)
      ]);
      setEnzyme(nextEnzyme);
      setMutations(nextMutations);
      setReferencesById(Object.fromEntries(references.map((reference) => [reference.id, reference])));
    } catch {
      setError("Unable to load mutation knowledge. Please check the API service and your login.");
    } finally {
      setIsLoading(false);
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token) {
      return;
    }
    void loadPage(token, filters);
  }

  function handleReset() {
    const nextFilters = emptyFilters();
    setFilters(nextFilters);
    setEvidenceCurationStatus("");
    setEvidenceReferenceSource("");
    if (token) {
      void loadPage(token, nextFilters);
    }
  }

  function handleDownloadMutationEvidenceCsv() {
    downloadCsv(`mutation-evidence-${enzymeId}.csv`, buildMutationEvidenceCsv(filteredMutations));
  }

  return (
    <main className="min-h-screen px-4 py-6 sm:px-6 lg:px-8">
      <section className="border-b border-slate-200 pb-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-sm font-medium text-slate-500">Mutation knowledge</p>
            <h1 className="mt-2 text-2xl font-semibold text-slate-950">
              {enzyme?.name ?? "Reported mutants"}
            </h1>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
              Review reported variants, property changes, source evidence, and mutation-site density.
            </p>
          </div>
          <Link
            className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700"
            href={`/enzymes/${enzymeId}/analysis`}
          >
            Analysis
          </Link>
        </div>
      </section>

      {error ? (
        <div className="mt-5 rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      ) : null}

      <section className="mt-6 grid gap-4 xl:grid-cols-[280px_1fr]">
        <aside className="rounded-md border border-slate-200 bg-white p-4">
          <form className="grid gap-4" onSubmit={handleSubmit}>
            <label className="grid gap-2 text-sm font-medium text-slate-700">
              Position
              <input
                className="rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-900"
                inputMode="numeric"
                onChange={(event) => setFilters((current) => ({ ...current, position: event.target.value }))}
                placeholder="e.g. 2"
                value={filters.position ?? ""}
              />
            </label>

            <label className="grid gap-2 text-sm font-medium text-slate-700">
              Property change
              <select
                className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900"
                onChange={(event) =>
                  setFilters((current) => ({ ...current, property_delta_key: event.target.value }))
                }
                value={filters.property_delta_key ?? ""}
              >
                {propertyDeltaOptions.map((key) => (
                  <option key={key || "any"} value={key}>
                    {key || "Any property"}
                  </option>
                ))}
              </select>
            </label>

            <label className="grid gap-2 text-sm font-medium text-slate-700">
              Source
              <input
                className="rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-900"
                onChange={(event) => setFilters((current) => ({ ...current, source: event.target.value }))}
                placeholder="europepmc, crossref"
                value={filters.source ?? ""}
              />
            </label>

            <label className="grid gap-2 text-sm font-medium text-slate-700">
              Visibility
              <select
                className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900"
                onChange={(event) =>
                  setFilters((current) => ({
                    ...current,
                    visibility: event.target.value as MutationQueryFilters["visibility"]
                  }))
                }
                value={filters.visibility ?? "public"}
              >
                <option value="public">Public</option>
                <option value="private">Private</option>
              </select>
            </label>

            <label className="flex items-center gap-2 text-sm font-medium text-slate-700">
              <input
                checked={Boolean(filters.beneficial_only)}
                className="h-4 w-4 rounded border-slate-300"
                onChange={(event) =>
                  setFilters((current) => ({ ...current, beneficial_only: event.target.checked }))
                }
                type="checkbox"
              />
              Beneficial only
            </label>

            <label className="grid gap-2 text-sm font-medium text-slate-700">
              Reference source
              <select
                className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900"
                onChange={(event) => setEvidenceReferenceSource(event.target.value)}
                value={evidenceReferenceSource}
              >
                <option value="">All sources</option>
                {referenceSourceOptions.map((source) => (
                  <option key={source} value={source}>
                    {source}
                  </option>
                ))}
              </select>
            </label>

            <label className="grid gap-2 text-sm font-medium text-slate-700">
              Curation status
              <select
                className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900"
                onChange={(event) => setEvidenceCurationStatus(event.target.value)}
                value={evidenceCurationStatus}
              >
                <option value="">All statuses</option>
                <option value="approved">approved</option>
                <option value="unreviewed">unreviewed</option>
                <option value="pending">pending</option>
                <option value="rejected">rejected</option>
              </select>
            </label>

            <div className="grid grid-cols-2 gap-2">
              <button
                className="rounded-md bg-slate-950 px-3 py-2 text-sm font-medium text-white disabled:bg-slate-400"
                disabled={!token || isLoading}
                type="submit"
              >
                Apply
              </button>
              <button
                className="rounded-md border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700"
                onClick={handleReset}
                type="button"
              >
                Reset
              </button>
            </div>
          </form>
        </aside>

        <div className="grid min-w-0 gap-4">
          <section className="rounded-md border border-slate-200 bg-white">
            <div className="border-b border-slate-200 px-4 py-4">
              <h2 className="text-base font-semibold text-slate-950">Mutation-site density</h2>
              <p className="mt-1 text-sm text-slate-500">
                {positionSummary.length} mutated positions from {filteredMutations.length} records
              </p>
            </div>
            {positionSummary.length ? (
              <div className="grid grid-cols-2 gap-2 p-4 sm:grid-cols-4 lg:grid-cols-6">
                {positionSummary.map((item) => (
                  <div
                    className="rounded-md border border-slate-200 p-3"
                    key={item.position}
                    title={item.mutations.join(", ")}
                  >
                    <p className="font-mono text-sm font-semibold text-slate-950">Position {item.position}</p>
                    <div className="mt-2 h-2 rounded bg-slate-100">
                      <div
                        className="h-2 rounded bg-slate-950"
                        style={{ width: `${Math.max(16, (item.count / maxPositionCount) * 100)}%` }}
                      />
                    </div>
                    <p className="mt-2 text-xs text-slate-500">{item.count} records</p>
                  </div>
                ))}
              </div>
            ) : (
              <EmptyMutationState />
            )}
          </section>

          <MutationDeltaSummaryPanel summary={deltaSummary} />

          <section className="rounded-md border border-slate-200 bg-white">
            <div className="border-b border-slate-200 px-4 py-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h2 className="text-base font-semibold text-slate-950">Reported mutants</h2>
                  <p className="mt-1 text-sm text-slate-500">
                    {isLoading ? "Loading mutations..." : `${filteredMutations.length} records`}
                  </p>
                </div>
                <button
                  className="rounded-md border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 disabled:text-slate-400"
                  disabled={filteredMutations.length === 0}
                  onClick={handleDownloadMutationEvidenceCsv}
                  type="button"
                >
                  Download CSV
                </button>
              </div>
            </div>
            {isLoading ? (
              <div className="px-4 py-10 text-sm text-slate-500">Loading mutation knowledge...</div>
            ) : filteredMutations.length ? (
              <MutationTable records={filteredMutations} referencesById={referencesById} />
            ) : (
              <EmptyMutationState />
            )}
          </section>
        </div>
      </section>
    </main>
  );
}

function MutationDeltaSummaryPanel({
  summary
}: {
  summary: ReturnType<typeof buildMutationDeltaSummary>;
}) {
  return (
    <section className="rounded-md border border-slate-200 bg-white">
      <div className="border-b border-slate-200 px-4 py-4">
        <h2 className="text-base font-semibold text-slate-950">Mutation effect summary</h2>
        <p className="mt-1 text-sm text-slate-500">
          Numeric property deltas grouped by reported effect direction.
        </p>
      </div>
      {summary.length > 0 ? (
        <div className="grid gap-4 p-4 xl:grid-cols-2">
          {summary.map((item) => (
            <article className="rounded-md border border-slate-200 p-4" key={item.property}>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h3 className="break-words text-sm font-semibold text-slate-950">{item.property}</h3>
                  <p className="mt-1 text-xs text-slate-500">
                    {item.improved} improved · {item.worsened} worsened · {item.neutral} neutral
                  </p>
                </div>
              </div>
              <div className="mt-4 grid gap-2">
                {item.top_mutations.map((mutation) => (
                  <div
                    className="grid gap-2 rounded-md bg-slate-50 px-3 py-2 text-sm sm:grid-cols-[8rem_5rem_1fr]"
                    key={`${item.property}-${mutation.mutation_string}-${mutation.value}`}
                  >
                    <span className="font-mono font-semibold text-slate-950">{mutation.mutation_string}</span>
                    <span className="font-medium text-slate-700">{mutation.value}</span>
                    <span className="min-w-0 text-slate-600">{mutation.effect_summary ?? "-"}</span>
                  </div>
                ))}
              </div>
            </article>
          ))}
        </div>
      ) : (
        <div className="px-4 py-10 text-sm text-slate-500">
          No numeric mutation effect deltas are available for the current filters.
        </div>
      )}
    </section>
  );
}

function downloadCsv(fileName: string, csvText: string) {
  const blob = new Blob([csvText], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = fileName;
  link.click();
  URL.revokeObjectURL(url);
}

function MutationTable({
  records,
  referencesById
}: {
  records: MutationRecord[];
  referencesById: Record<string, LiteratureReferenceRecord>;
}) {
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full divide-y divide-slate-200 text-sm">
        <thead className="bg-slate-50 text-left text-xs font-medium uppercase text-slate-500">
          <tr>
            <th className="px-4 py-3">Mutation</th>
            <th className="px-4 py-3">Sites</th>
            <th className="px-4 py-3">Property change</th>
            <th className="px-4 py-3">Evidence</th>
            <th className="px-4 py-3">Visibility</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {records.map((record) => (
            <tr key={record.id}>
              <td className="whitespace-nowrap px-4 py-3">
                <p className="font-mono font-semibold text-slate-950">{record.mutation_string}</p>
                <p className="mt-1 text-xs text-slate-500">{record.effect_summary ?? "-"}</p>
              </td>
              <td className="whitespace-nowrap px-4 py-3 font-mono text-slate-700">
                {formatMutationPositions(record)}
              </td>
              <td className="min-w-64 px-4 py-3 text-slate-700">{formatPropertyDelta(record.property_delta)}</td>
              <td className="min-w-64 px-4 py-3 text-slate-600">
                <div className="grid gap-1">
                  <ReferenceCitation
                    fallback={record.reference_id ?? null}
                    reference={record.reference ?? referencesById[record.reference_id ?? ""]}
                  />
                  {record.assay_condition_summary &&
                  typeof record.assay_condition_summary.evidence === "string" ? (
                    <span>{record.assay_condition_summary.evidence}</span>
                  ) : null}
                </div>
              </td>
              <td className="whitespace-nowrap px-4 py-3 text-slate-600">
                {record.visibility} · {record.curation_status}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function EmptyMutationState() {
  return (
    <div className="px-4 py-10 text-sm text-slate-500">
      No mutation records match the current filters.
    </div>
  );
}
