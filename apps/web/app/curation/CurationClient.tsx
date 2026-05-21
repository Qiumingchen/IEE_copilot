"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import {
  approveVisibilityRequest,
  importCuratedEvidence,
  listVisibilityRequests,
  previewCuratedEvidence,
  rejectVisibilityRequest
} from "../../lib/api";
import type {
  CuratedEvidenceImportResponse,
  CuratedEvidencePreviewResponse,
  VisibilityRequestDetailRecord
} from "../../lib/types";
import {
  canSubmitRejection,
  curatedEvidenceCsvTemplate,
  summarizeCuratedEvidenceImport,
  summarizeCuratedEvidencePreview,
  summarizeVisibilityRequest
} from "./curation-utils";

const TOKEN_KEY = "iee-copilot-token";

export default function CurationClient() {
  const router = useRouter();
  const [token, setToken] = useState<string | null>(null);
  const [requests, setRequests] = useState<VisibilityRequestDetailRecord[]>([]);
  const [reviewComments, setReviewComments] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [activeRequestId, setActiveRequestId] = useState<string | null>(null);
  const [importEnzymeId, setImportEnzymeId] = useState("");
  const [importCsvText, setImportCsvText] = useState("");
  const [importResult, setImportResult] = useState<CuratedEvidenceImportResponse | null>(null);
  const [importPreview, setImportPreview] = useState<CuratedEvidencePreviewResponse | null>(null);
  const [isImporting, setIsImporting] = useState(false);
  const [isPreviewingImport, setIsPreviewingImport] = useState(false);

  async function loadRequests(nextToken: string) {
    setError(null);
    setIsLoading(true);
    try {
      setRequests(await listVisibilityRequests(nextToken));
    } catch (exc) {
      setRequests([]);
      setError(exc instanceof Error ? exc.message : "Unable to load curation queue.");
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    const storedToken = window.localStorage.getItem(TOKEN_KEY);
    if (!storedToken) {
      router.replace("/login");
      return;
    }
    setToken(storedToken);
    void loadRequests(storedToken);
  }, [router]);

  async function handleApprove(requestId: string) {
    if (!token) {
      return;
    }
    setActiveRequestId(requestId);
    setError(null);
    setSuccessMessage(null);
    try {
      await approveVisibilityRequest(requestId, token);
      setSuccessMessage("Visibility request approved.");
      await loadRequests(token);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Unable to approve visibility request.");
    } finally {
      setActiveRequestId(null);
    }
  }

  async function handleReject(requestId: string) {
    if (!token) {
      return;
    }
    const comment = reviewComments[requestId] ?? "";
    if (!canSubmitRejection(comment)) {
      setError("Review comment is required.");
      return;
    }
    setActiveRequestId(requestId);
    setError(null);
    setSuccessMessage(null);
    try {
      await rejectVisibilityRequest(requestId, token, comment);
      setReviewComments((current) => ({ ...current, [requestId]: "" }));
      setSuccessMessage("Visibility request rejected.");
      await loadRequests(token);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Unable to reject visibility request.");
    } finally {
      setActiveRequestId(null);
    }
  }

  async function handleCuratedPreview() {
    if (!token || !importEnzymeId.trim() || !importCsvText.trim()) {
      setError("Enzyme ID and CSV text are required.");
      return;
    }
    setIsPreviewingImport(true);
    setError(null);
    setSuccessMessage(null);
    setImportResult(null);
    setImportPreview(null);
    try {
      const preview = await previewCuratedEvidence(importEnzymeId.trim(), token, importCsvText);
      setImportPreview(preview);
      setSuccessMessage(summarizeCuratedEvidencePreview(preview));
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Unable to preview curated evidence.");
    } finally {
      setIsPreviewingImport(false);
    }
  }

  async function handleCuratedImport() {
    if (!token || !importEnzymeId.trim() || !importCsvText.trim()) {
      setError("Enzyme ID and CSV text are required.");
      return;
    }
    setIsImporting(true);
    setError(null);
    setSuccessMessage(null);
    setImportResult(null);
    try {
      const result = await importCuratedEvidence(importEnzymeId.trim(), token, importCsvText);
      setImportResult(result);
      setImportPreview(null);
      setSuccessMessage(summarizeCuratedEvidenceImport(result));
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Unable to import curated evidence.");
    } finally {
      setIsImporting(false);
    }
  }

  return (
    <main className="mx-auto max-w-6xl px-6 py-8">
      <header className="border-b border-slate-200 pb-6">
        <p className="text-sm font-medium text-slate-500">Curation</p>
        <div className="mt-2 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold text-slate-950">Visibility review queue</h1>
            <p className="mt-2 text-sm text-slate-600">
              Review user-uploaded experiment data before it enters the public knowledge base.
            </p>
          </div>
          <button
            className="rounded-md border border-slate-300 px-3 py-2 text-sm font-medium text-slate-800 disabled:cursor-not-allowed disabled:text-slate-400"
            disabled={!token || isLoading}
            onClick={() => token && void loadRequests(token)}
            type="button"
          >
            Refresh
          </button>
        </div>
      </header>

      {error ? (
        <p className="mt-4 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          {error}
        </p>
      ) : null}
      {successMessage ? (
        <p className="mt-4 rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-700">
          {successMessage}
        </p>
      ) : null}

      {isLoading ? <p className="mt-6 text-sm text-slate-600">Loading visibility requests...</p> : null}

      <section className="mt-8 rounded-md border border-slate-200 bg-white p-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h2 className="text-base font-semibold text-slate-950">Curated evidence import</h2>
            <p className="mt-1 max-w-3xl text-sm text-slate-600">
              Import literature-curated property, kinetic, and mutation rows into one enzyme record.
            </p>
          </div>
          <button
            className="rounded-md border border-slate-300 px-4 py-2 text-sm font-medium text-slate-800 disabled:cursor-not-allowed disabled:text-slate-400"
            disabled={isPreviewingImport || isImporting}
            onClick={() => {
              setImportCsvText(curatedEvidenceCsvTemplate);
              setImportPreview(null);
              setImportResult(null);
              setError(null);
              setSuccessMessage(null);
            }}
            type="button"
          >
            Use template
          </button>
          <button
            className="rounded-md border border-slate-300 px-4 py-2 text-sm font-medium text-slate-800 disabled:cursor-not-allowed disabled:text-slate-400"
            disabled={!token || isPreviewingImport || isImporting}
            onClick={() => void handleCuratedPreview()}
            type="button"
          >
            {isPreviewingImport ? "Previewing..." : "Preview CSV"}
          </button>
          <button
            className="rounded-md bg-slate-950 px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:bg-slate-400"
            disabled={!token || isImporting || !importPreview}
            onClick={() => void handleCuratedImport()}
            type="button"
          >
            {isImporting ? "Importing..." : "Import CSV"}
          </button>
        </div>

        <div className="mt-4 grid gap-4 lg:grid-cols-[minmax(0,320px)_1fr]">
          <label className="grid gap-2 text-sm font-medium text-slate-700">
            Enzyme ID
            <input
              className="rounded-md border border-slate-300 px-3 py-2 font-mono text-sm text-slate-950 outline-none focus:border-slate-500"
              onChange={(event) => setImportEnzymeId(event.target.value)}
              placeholder="UUID from enzyme detail URL"
              value={importEnzymeId}
            />
          </label>
          <label className="grid gap-2 text-sm font-medium text-slate-700">
            CSV text
            <textarea
              className="min-h-36 rounded-md border border-slate-300 px-3 py-2 font-mono text-xs text-slate-950 outline-none focus:border-slate-500"
              onChange={(event) => setImportCsvText(event.target.value)}
              placeholder="record_type,property_type,value_original,unit_original,doi,reference_title,evidence_text"
              value={importCsvText}
            />
          </label>
        </div>

        {importResult?.warnings.length ? (
          <div className="mt-4 grid gap-2">
            {importResult.warnings.map((warning) => (
              <p
                className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800"
                key={warning}
              >
                {warning}
              </p>
            ))}
          </div>
        ) : null}

        {importPreview ? (
          <div className="mt-5 border-t border-slate-200 pt-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h3 className="text-sm font-semibold text-slate-950">Preview</h3>
                <p className="mt-1 text-sm text-slate-600">{summarizeCuratedEvidencePreview(importPreview)}</p>
              </div>
              <p className="max-w-xl break-words font-mono text-xs text-slate-500">
                {importPreview.fields.join(" / ")}
              </p>
            </div>
            <div className="mt-3 overflow-x-auto">
              <table className="min-w-full divide-y divide-slate-200 text-sm">
                <thead className="bg-slate-50 text-left text-xs font-medium uppercase text-slate-500">
                  <tr>
                    <th className="px-3 py-2">Row</th>
                    <th className="px-3 py-2">Type</th>
                    <th className="px-3 py-2">Summary</th>
                    <th className="px-3 py-2">Reference</th>
                    <th className="px-3 py-2">Evidence</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {importPreview.records.slice(0, 20).map((record) => (
                    <tr key={`${record.row_number}-${record.summary}`}>
                      <td className="whitespace-nowrap px-3 py-2 text-slate-600">{record.row_number}</td>
                      <td className="whitespace-nowrap px-3 py-2 text-slate-800">{record.record_type}</td>
                      <td className="min-w-48 px-3 py-2 text-slate-800">{record.summary}</td>
                      <td className="min-w-44 px-3 py-2 text-slate-600">{record.reference_key ?? "-"}</td>
                      <td className="min-w-64 px-3 py-2 text-slate-600">{record.evidence_text ?? "-"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ) : null}
      </section>

      {!isLoading && requests.length === 0 && !error ? (
        <section className="mt-8 border-t border-slate-200 pt-6">
          <h2 className="text-base font-semibold text-slate-950">No pending requests</h2>
          <p className="mt-2 text-sm text-slate-600">The curation queue is currently clear.</p>
        </section>
      ) : null}

      <section className="mt-8 grid gap-4">
        {requests.map((request) => {
          const experiment = request.experiment;
          const comment = reviewComments[request.id] ?? "";
          return (
            <article className="rounded-md border border-slate-200 bg-white p-5 shadow-sm" key={request.id}>
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <p className="text-xs font-medium uppercase text-slate-500">Pending public request</p>
                  <h2 className="mt-2 text-lg font-semibold text-slate-950">
                    {summarizeVisibilityRequest(request)}
                  </h2>
                  <p className="mt-2 text-sm text-slate-600">
                    Project {request.project_id} · Experiment {experiment.id}
                  </p>
                </div>
                <span className="rounded-md border border-amber-200 bg-amber-50 px-2 py-1 text-xs font-medium text-amber-700">
                  {request.status}
                </span>
              </div>

              <dl className="mt-5 grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-4">
                <div>
                  <dt className="font-medium text-slate-500">Variant</dt>
                  <dd className="mt-1 text-slate-950">{experiment.variant_name}</dd>
                </div>
                <div>
                  <dt className="font-medium text-slate-500">Mutation</dt>
                  <dd className="mt-1 text-slate-950">{experiment.mutation_string ?? "WT"}</dd>
                </div>
                <div>
                  <dt className="font-medium text-slate-500">Measurement</dt>
                  <dd className="mt-1 text-slate-950">
                    {experiment.measured_property}: {experiment.measured_value}
                    {experiment.unit ? ` ${experiment.unit}` : ""}
                  </dd>
                </div>
                <div>
                  <dt className="font-medium text-slate-500">Visibility</dt>
                  <dd className="mt-1 text-slate-950">
                    {experiment.visibility} / {experiment.curation_status}
                  </dd>
                </div>
                <div className="sm:col-span-2">
                  <dt className="font-medium text-slate-500">Assay condition</dt>
                  <dd className="mt-1 break-words font-mono text-xs text-slate-700">
                    {JSON.stringify(experiment.assay_condition_json ?? {})}
                  </dd>
                </div>
                <div>
                  <dt className="font-medium text-slate-500">Requested by</dt>
                  <dd className="mt-1 text-slate-950">{request.requested_by}</dd>
                </div>
                <div>
                  <dt className="font-medium text-slate-500">Target</dt>
                  <dd className="mt-1 text-slate-950">{request.requested_visibility}</dd>
                </div>
              </dl>

              <div className="mt-5 grid gap-3 lg:grid-cols-[1fr_auto_auto]">
                <input
                  className="rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-950 outline-none focus:border-slate-500"
                  placeholder="Reject comment"
                  value={comment}
                  onChange={(event) =>
                    setReviewComments((current) => ({
                      ...current,
                      [request.id]: event.target.value
                    }))
                  }
                />
                <button
                  className="rounded-md border border-red-300 px-4 py-2 text-sm font-medium text-red-700 disabled:cursor-not-allowed disabled:text-slate-400"
                  disabled={activeRequestId === request.id || !canSubmitRejection(comment)}
                  onClick={() => void handleReject(request.id)}
                  type="button"
                >
                  Reject
                </button>
                <button
                  className="rounded-md bg-slate-950 px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:bg-slate-400"
                  disabled={activeRequestId === request.id}
                  onClick={() => void handleApprove(request.id)}
                  type="button"
                >
                  Approve
                </button>
              </div>
            </article>
          );
        })}
      </section>
    </main>
  );
}
