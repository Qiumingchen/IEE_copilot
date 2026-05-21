"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { getJob } from "../../../lib/api";
import {
  formatProvenanceLabel,
  getProvenanceModeTone,
  isRecord,
  provenanceUrl,
  provenanceWarning
} from "../../../lib/provenance";
import type { JobResponse } from "../../../lib/types";

const TOKEN_KEY = "iee-copilot-token";

type JobDetailClientProps = {
  jobId: string;
};

export default function JobDetailClient({ jobId }: JobDetailClientProps) {
  const router = useRouter();
  const [token, setToken] = useState<string | null>(null);
  const [job, setJob] = useState<JobResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function loadJob(nextToken: string) {
    setError(null);
    setIsLoading(true);
    try {
      setJob(await getJob(jobId, nextToken));
    } catch {
      setError("Unable to load analysis job. Please check the API service and your login.");
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
    void loadJob(storedToken);
  }, [jobId, router]);

  const provenance = getJobRetrievalProvenance(job);

  return (
    <main className="mx-auto max-w-4xl px-6 py-8">
      <header className="border-b border-slate-200 pb-6">
        <p className="text-sm font-medium text-slate-500">Analysis queue</p>
        <div className="mt-2 flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold text-slate-950">Analysis job</h1>
            <p className="mt-2 break-words font-mono text-sm text-slate-600">Job id: {jobId}</p>
          </div>
          <button
            className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-800 disabled:cursor-not-allowed disabled:text-slate-400"
            disabled={!token || isLoading}
            onClick={() => token && void loadJob(token)}
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
      {isLoading ? <p className="mt-6 text-sm text-slate-600">Loading job...</p> : null}

      {job ? (
        <div className="mt-6 grid gap-5">
          <section className="rounded-md border border-slate-200 bg-white p-5">
            <h2 className="text-base font-semibold text-slate-950">Status</h2>
            <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
              <Definition label="Type" value={job.job_type} />
              <Definition label="Status" value={job.status} />
              <Definition label="Created" value={job.created_at} />
              <Definition label="Finished" value={job.finished_at ?? "-"} />
            </dl>
            {job.error_message ? (
              <p className="mt-4 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
                {job.error_message}
              </p>
            ) : null}
            {job.enzyme_entry_id ? (
              <Link
                className="mt-4 inline-flex rounded-md border border-slate-300 px-3 py-2 text-sm font-medium text-slate-800"
                href={`/enzymes/${job.enzyme_entry_id}`}
              >
                Open enzyme record
              </Link>
            ) : null}
          </section>

          <ProvenancePanel provenance={provenance} />

          <section className="rounded-md border border-slate-200 bg-white p-5">
            <h2 className="text-base font-semibold text-slate-950">Parameters</h2>
            <pre className="mt-3 max-h-96 overflow-auto rounded-md bg-slate-950 p-3 text-xs text-slate-100">
              {JSON.stringify(job.parameters_json ?? {}, null, 2)}
            </pre>
          </section>
        </div>
      ) : null}
    </main>
  );
}

function getJobRetrievalProvenance(job: JobResponse | null) {
  if (!job || !isRecord(job.parameters_json)) {
    return null;
  }
  const provenance = job.parameters_json.retrieval_provenance;
  return isRecord(provenance) ? provenance : null;
}

function ProvenancePanel({ provenance }: { provenance: Record<string, unknown> | null }) {
  const tone = getProvenanceModeTone(provenance);
  const toneClass =
    tone === "real"
      ? "border-emerald-200 bg-emerald-50 text-emerald-900"
      : tone === "fallback"
        ? "border-amber-200 bg-amber-50 text-amber-900"
        : "border-slate-200 bg-white text-slate-700";
  const sourceUrl = provenanceUrl(provenance);
  const warning = provenanceWarning(provenance);

  return (
    <section className={`rounded-md border p-5 ${toneClass}`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold">Retrieval provenance</h2>
          <p className="mt-2 break-words font-mono text-xs">{formatProvenanceLabel(provenance)}</p>
        </div>
        {sourceUrl ? (
          <a
            className="text-sm font-medium underline underline-offset-2"
            href={sourceUrl}
            rel="noreferrer"
            target="_blank"
          >
            Source
          </a>
        ) : null}
      </div>
      {warning ? <p className="mt-3 text-sm">{warning}</p> : null}
    </section>
  );
}

function Definition({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs font-medium uppercase text-slate-500">{label}</dt>
      <dd className="mt-1 break-words text-sm text-slate-950">{value}</dd>
    </div>
  );
}
