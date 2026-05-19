"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { createAnalysisJob, getAnalysisArtifacts } from "../../../../lib/api";
import type { AnalysisArtifactRecord, AnalysisJobType } from "../../../../lib/types";

const TOKEN_KEY = "iee-copilot-token";

type AnalysisClientProps = {
  enzymeId: string;
};

const analysisModules = [
  {
    title: "Homolog sequences",
    artifactType: "homolog_sequences",
    jobType: "homolog_collection",
    metric: "identity / coverage",
    actionLabel: "Run homologs"
  },
  {
    title: "MSA",
    artifactType: "msa",
    jobType: "msa",
    metric: "aligned FASTA",
    actionLabel: "Run MSA"
  },
  {
    title: "Conservation",
    artifactType: "conservation_profile",
    jobType: "conservation_profile",
    metric: "entropy / WT frequency",
    actionLabel: "Run conservation"
  }
] satisfies Array<{
  title: string;
  artifactType: string;
  jobType: AnalysisJobType;
  metric: string;
  actionLabel: string;
}>;

const conservationPreview = [
  {
    position: "1",
    residue: "A",
    entropy: "0.000",
    frequency: "1.00",
    category: "highly_conserved"
  },
  {
    position: "2",
    residue: "C",
    entropy: "0.811",
    frequency: "0.75",
    category: "moderately_conserved"
  },
  {
    position: "3",
    residue: "D",
    entropy: "0.811",
    frequency: "0.75",
    category: "moderately_conserved"
  }
];

export default function AnalysisClient({ enzymeId }: AnalysisClientProps) {
  const router = useRouter();
  const [token, setToken] = useState<string | null>(null);
  const [artifacts, setArtifacts] = useState<AnalysisArtifactRecord[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [runningJobType, setRunningJobType] = useState<AnalysisJobType | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function loadArtifacts(nextToken: string) {
    setError(null);
    setIsLoading(true);
    try {
      setArtifacts(await getAnalysisArtifacts(enzymeId, nextToken));
    } catch {
      setError("Unable to load analysis artifacts. Please check the API service and your login.");
    } finally {
      setIsLoading(false);
    }
  }

  async function runAnalysis(jobType: AnalysisJobType) {
    if (!token) {
      return;
    }
    setError(null);
    setNotice(null);
    setRunningJobType(jobType);
    try {
      const job = await createAnalysisJob(enzymeId, token, jobType);
      setNotice(`${job.job_type} job queued: ${job.id}`);
      await loadArtifacts(token);
    } catch {
      setError("Unable to queue analysis job. Please check that this enzyme has a protein sequence.");
    } finally {
      setRunningJobType(null);
    }
  }

  useEffect(() => {
    const storedToken = window.localStorage.getItem(TOKEN_KEY);
    if (!storedToken) {
      router.replace("/login");
      return;
    }
    setToken(storedToken);
    void loadArtifacts(storedToken);
  }, [enzymeId, router]);

  return (
    <main className="mx-auto max-w-6xl px-6 py-8">
      <header className="border-b border-slate-200 pb-6">
        <p className="text-sm font-medium text-slate-500">MSA / Conservation</p>
        <div className="mt-2 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold text-slate-950">Evolutionary analysis</h1>
            <p className="mt-2 text-sm text-slate-600">Entry id: {enzymeId}</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-800 disabled:cursor-not-allowed disabled:text-slate-400"
              disabled={!token || isLoading}
              onClick={() => token && void loadArtifacts(token)}
              type="button"
            >
              Refresh
            </button>
            <Link
              className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-800"
              href={`/enzymes/${enzymeId}`}
            >
              Back to enzyme
            </Link>
          </div>
        </div>
      </header>

      {error ? (
        <p className="mt-4 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          {error}
        </p>
      ) : null}
      {notice ? (
        <p className="mt-4 rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-700">
          {notice}
        </p>
      ) : null}

      {isLoading ? <p className="mt-6 text-sm text-slate-600">Loading analysis artifacts...</p> : null}

      <section className="mt-6 grid gap-3 md:grid-cols-3">
        {analysisModules.map((item) => {
          const moduleArtifacts = artifacts.filter((artifact) => artifact.artifact_type === item.artifactType);
          const latestArtifact = moduleArtifacts[moduleArtifacts.length - 1];
          const isRunning = runningJobType === item.jobType;
          return (
            <article className="rounded-md border border-slate-200 bg-white p-4" key={item.artifactType}>
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h2 className="text-base font-semibold text-slate-950">{item.title}</h2>
                  <p className="mt-1 text-sm text-slate-600">{item.metric}</p>
                </div>
                <StatusPill value={latestArtifact?.job_status ?? "not_run"} />
              </div>
              <dl className="mt-4 grid gap-3">
                <div>
                  <dt className="text-xs font-medium uppercase text-slate-500">Artifact</dt>
                  <dd className="mt-1 break-words font-mono text-sm text-slate-950">{item.artifactType}</dd>
                </div>
                <div>
                  <dt className="text-xs font-medium uppercase text-slate-500">Latest object</dt>
                  <dd className="mt-1 break-words font-mono text-xs text-slate-700">
                    {latestArtifact?.object_key ?? "-"}
                  </dd>
                </div>
              </dl>
              <button
                className="mt-4 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-800 disabled:cursor-not-allowed disabled:text-slate-400"
                disabled={!token || Boolean(runningJobType)}
                onClick={() => void runAnalysis(item.jobType)}
                type="button"
              >
                {isRunning ? "Queueing..." : item.actionLabel}
              </button>
            </article>
          );
        })}
      </section>

      <section className="mt-8 overflow-hidden rounded-md border border-slate-200 bg-white">
        <div className="border-b border-slate-200 px-4 py-3">
          <h2 className="text-base font-semibold text-slate-950">Analysis artifacts</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-200 text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase text-slate-500">
              <tr>
                <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">
                  Type
                </th>
                <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">
                  Status
                </th>
                <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">
                  Object key
                </th>
                <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">
                  Size
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-slate-700">
              {artifacts.length > 0 ? (
                artifacts.map((artifact) => (
                  <tr key={artifact.id}>
                    <td className="px-4 py-3 font-mono text-slate-950">{artifact.artifact_type}</td>
                    <td className="px-4 py-3">
                      <StatusPill value={artifact.job_status ?? "-"} />
                    </td>
                    <td className="max-w-md px-4 py-3">
                      <span className="break-words font-mono text-xs">{artifact.object_key}</span>
                    </td>
                    <td className="px-4 py-3">{artifact.size_bytes ?? "-"}</td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td className="px-4 py-4 text-slate-500" colSpan={4}>
                    No analysis artifacts
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="mt-8 overflow-hidden rounded-md border border-slate-200 bg-white">
        <div className="border-b border-slate-200 px-4 py-3">
          <h2 className="text-base font-semibold text-slate-950">Conservation profile</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-200 text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase text-slate-500">
              <tr>
                <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">
                  Position
                </th>
                <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">
                  WT
                </th>
                <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">
                  Entropy
                </th>
                <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">
                  WT frequency
                </th>
                <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">
                  Category
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-slate-700">
              {conservationPreview.map((site) => (
                <tr key={site.position}>
                  <td className="px-4 py-3 font-medium text-slate-950">{site.position}</td>
                  <td className="px-4 py-3 font-mono">{site.residue}</td>
                  <td className="px-4 py-3">{site.entropy}</td>
                  <td className="px-4 py-3">{site.frequency}</td>
                  <td className="px-4 py-3">
                    <span className="rounded bg-slate-100 px-2 py-1 text-xs font-medium text-slate-700">
                      {site.category}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  );
}

function StatusPill({ value }: { value: string }) {
  return (
    <span className="rounded bg-slate-100 px-2 py-1 text-xs font-medium text-slate-700">
      {value}
    </span>
  );
}
