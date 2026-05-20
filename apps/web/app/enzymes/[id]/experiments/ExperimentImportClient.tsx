"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { ChangeEvent, FormEvent, useEffect, useMemo, useState } from "react";

import {
  importExperiments,
  listProjects,
  previewExperimentImport
} from "../../../../lib/api";
import type { ExperimentImportPreview, ProjectRecord } from "../../../../lib/types";
import {
  buildExperimentImportRequest,
  summarizeExperimentPreview
} from "./experiment-import-utils";

const TOKEN_KEY = "iee-copilot-token";

type ExperimentImportClientProps = {
  enzymeId: string;
};

const sampleCsv = [
  "variant_name,mutation_string,specific_activity,opt_temperature,substrate,assay_temperature,assay_pH,visibility",
  "WT control,WT,100,50,casein,37,7.0,private",
  "L10A variant,L10A,125.4,55,casein,37,7.5,private"
].join("\n");

export default function ExperimentImportClient({ enzymeId }: ExperimentImportClientProps) {
  const router = useRouter();
  const [token, setToken] = useState<string | null>(null);
  const [projects, setProjects] = useState<ProjectRecord[]>([]);
  const [projectId, setProjectId] = useState("");
  const [csvText, setCsvText] = useState(sampleCsv);
  const [preview, setPreview] = useState<ExperimentImportPreview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [isLoadingProjects, setIsLoadingProjects] = useState(true);
  const [isPreviewing, setIsPreviewing] = useState(false);
  const [isImporting, setIsImporting] = useState(false);

  const previewSummary = useMemo(
    () => (preview ? summarizeExperimentPreview(preview) : null),
    [preview]
  );

  useEffect(() => {
    const storedToken = window.localStorage.getItem(TOKEN_KEY);
    if (!storedToken) {
      router.replace("/login");
      return;
    }
    setToken(storedToken);
    setIsLoadingProjects(true);
    listProjects(storedToken)
      .then((items) => {
        setProjects(items);
        setProjectId((current) => current || items[0]?.id || "");
      })
      .catch(() => setError("Unable to load projects. Please check the API service and login."))
      .finally(() => setIsLoadingProjects(false));
  }, [router]);

  async function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }
    setError(null);
    setSuccessMessage(null);
    setPreview(null);
    setCsvText(await file.text());
  }

  async function handlePreview(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || !projectId || !csvText.trim()) {
      return;
    }
    setIsPreviewing(true);
    setError(null);
    setSuccessMessage(null);
    try {
      setPreview(
        await previewExperimentImport(
          enzymeId,
          token,
          buildExperimentImportRequest(projectId, csvText)
        )
      );
    } catch (exc) {
      setPreview(null);
      setError(exc instanceof Error ? exc.message : "Unable to preview experiment data.");
    } finally {
      setIsPreviewing(false);
    }
  }

  async function handleImport() {
    if (!token || !projectId || !csvText.trim()) {
      return;
    }
    setIsImporting(true);
    setError(null);
    setSuccessMessage(null);
    try {
      const result = await importExperiments(
        enzymeId,
        token,
        buildExperimentImportRequest(projectId, csvText)
      );
      setSuccessMessage(`Saved ${result.created_count} experiment measurements.`);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Unable to save experiment data.");
    } finally {
      setIsImporting(false);
    }
  }

  return (
    <main className="mx-auto max-w-6xl px-6 py-8">
      <header className="border-b border-slate-200 pb-6">
        <p className="text-sm font-medium text-slate-500">Wet-lab data</p>
        <div className="mt-2 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold text-slate-950">Experiment upload</h1>
            <p className="mt-2 text-sm text-slate-600">Enzyme id: {enzymeId}</p>
          </div>
          <Link
            className="rounded-md border border-slate-300 px-3 py-2 text-sm font-medium text-slate-800"
            href={`/enzymes/${enzymeId}`}
          >
            Enzyme detail
          </Link>
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

      <form className="mt-6 grid gap-5" onSubmit={handlePreview}>
        <section className="grid gap-4 border-b border-slate-200 pb-6 lg:grid-cols-[280px_1fr]">
          <div>
            <h2 className="text-base font-semibold text-slate-950">Upload settings</h2>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="grid gap-1 text-sm font-medium text-slate-700">
              Project
              <select
                className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-950 outline-none focus:border-slate-500"
                disabled={isLoadingProjects}
                value={projectId}
                onChange={(event) => setProjectId(event.target.value)}
              >
                {projects.map((project) => (
                  <option key={project.id} value={project.id}>
                    {project.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="grid gap-1 text-sm font-medium text-slate-700">
              CSV file
              <input
                accept=".csv,text/csv"
                className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-950 file:mr-3 file:rounded-md file:border-0 file:bg-slate-100 file:px-3 file:py-1 file:text-sm file:font-medium file:text-slate-800"
                type="file"
                onChange={handleFileChange}
              />
            </label>
          </div>
        </section>

        <section className="grid gap-4 border-b border-slate-200 pb-6 lg:grid-cols-[280px_1fr]">
          <div>
            <h2 className="text-base font-semibold text-slate-950">CSV content</h2>
          </div>
          <textarea
            className="min-h-64 rounded-md border border-slate-300 bg-white px-3 py-2 font-mono text-sm text-slate-950 outline-none focus:border-slate-500"
            value={csvText}
            onChange={(event) => {
              setCsvText(event.target.value);
              setPreview(null);
              setSuccessMessage(null);
            }}
          />
        </section>

        <div className="flex flex-wrap gap-3">
          <button
            className="rounded-md bg-slate-950 px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:bg-slate-400"
            disabled={isPreviewing || !projectId || !csvText.trim()}
            type="submit"
          >
            {isPreviewing ? "Previewing..." : "Preview"}
          </button>
          <button
            className="rounded-md border border-slate-300 px-4 py-2 text-sm font-medium text-slate-800 disabled:cursor-not-allowed disabled:text-slate-400"
            disabled={isImporting || !preview || !projectId}
            type="button"
            onClick={handleImport}
          >
            {isImporting ? "Saving..." : "Save experiments"}
          </button>
        </div>
      </form>

      {preview ? (
        <section className="mt-8">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 pb-3">
            <div>
              <h2 className="text-base font-semibold text-slate-950">Preview</h2>
              <p className="mt-1 text-sm text-slate-600">{previewSummary}</p>
            </div>
            <p className="text-xs font-medium uppercase text-slate-500">
              {preview.fields.join(" / ")}
            </p>
          </div>
          <div className="mt-4 overflow-x-auto">
            <table className="min-w-full border-collapse text-left text-sm">
              <thead>
                <tr className="border-b border-slate-200 text-xs uppercase text-slate-500">
                  <th className="px-3 py-2">Row</th>
                  <th className="px-3 py-2">Variant</th>
                  <th className="px-3 py-2">Mutation</th>
                  <th className="px-3 py-2">Property</th>
                  <th className="px-3 py-2">Value</th>
                  <th className="px-3 py-2">Visibility</th>
                </tr>
              </thead>
              <tbody>
                {preview.records.slice(0, 50).map((record, index) => (
                  <tr
                    className="border-b border-slate-100 text-slate-800"
                    key={`${record.row_number}-${record.measured_property}-${index}`}
                  >
                    <td className="px-3 py-2">{record.row_number}</td>
                    <td className="px-3 py-2">{record.variant_name}</td>
                    <td className="px-3 py-2">{record.mutation_string ?? "-"}</td>
                    <td className="px-3 py-2">{record.measured_property}</td>
                    <td className="px-3 py-2">
                      {record.measured_value}
                      {record.unit ? ` ${record.unit}` : ""}
                    </td>
                    <td className="px-3 py-2">{record.visibility}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}
    </main>
  );
}
