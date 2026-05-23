"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import type { ChangeEvent } from "react";
import { useEffect, useMemo, useRef, useState } from "react";

import { downloadStructureFile, getEnzymeRecordBundle, uploadStructureFile } from "../../../../lib/api";
import type { EnzymeRecordBundle, StructureRecord } from "../../../../lib/types";
import {
  buildDistanceMatrixCsv,
  buildResidueMappingCsv,
  buildStructureReportJson,
  buildStructureWarnings,
  buildStructureDownloadFileName,
  getChainOptions,
  getDefaultStructureId,
  getDistanceMatrixRows,
  getLigandViews,
  getMetalIonViews,
  getResidueRows,
  getStructurePreviewAtoms,
  getStructureQualityChecks,
  getStructureReadiness,
  getStructureProvenanceView,
  getStructureStats,
  getStructureWorkflowActions,
  isStructureUploadFileName,
  structureUploadAccept,
  summarizeStructureUploadResult
} from "./structure-utils";

const TOKEN_KEY = "iee-copilot-token";

type StructureAnalysisClientProps = {
  enzymeId: string;
  initialStructureId?: string;
};

export default function StructureAnalysisClient({ enzymeId, initialStructureId = "" }: StructureAnalysisClientProps) {
  const router = useRouter();
  const [token, setToken] = useState<string | null>(null);
  const [bundle, setBundle] = useState<EnzymeRecordBundle | null>(null);
  const [selectedStructureId, setSelectedStructureId] = useState<string | null>(initialStructureId || null);
  const [selectedChainId, setSelectedChainId] = useState<string | null>(null);
  const [selectedUploadFile, setSelectedUploadFile] = useState<File | null>(null);
  const [isUploadingStructure, setIsUploadingStructure] = useState(false);
  const [downloadingStructureId, setDownloadingStructureId] = useState<string | null>(null);
  const [uploadNotice, setUploadNotice] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const uploadInputRef = useRef<HTMLInputElement | null>(null);

  async function loadBundle(nextToken: string, preferredStructureId?: string) {
    setError(null);
    setIsLoading(true);
    try {
      const nextBundle = await getEnzymeRecordBundle(enzymeId, nextToken);
      setBundle(nextBundle);
      setSelectedStructureId((current) => {
        const requestedStructureId = preferredStructureId ?? current ?? initialStructureId;
        const hasRequestedStructure = nextBundle.structures.some(
          (structure) => structure.id === requestedStructureId
        );
        return hasRequestedStructure ? requestedStructureId : getDefaultStructureId(nextBundle.structures);
      });
    } catch {
      setError("Unable to load structure analysis data. Please check the API service and your login.");
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
    void loadBundle(storedToken);
  }, [enzymeId, router]);

  const structures = bundle?.structures ?? [];
  const selectedStructure = useMemo(
    () => structures.find((structure) => structure.id === selectedStructureId) ?? structures[0] ?? null,
    [selectedStructureId, structures]
  );
  const chainOptions = useMemo(() => getChainOptions(selectedStructure ? [selectedStructure] : []), [selectedStructure]);
  const selectedChain = chainOptions.find((chain) => chain.chain_id === selectedChainId) ?? chainOptions[0] ?? null;
  const ligandViews = selectedStructure ? getLigandViews(selectedStructure) : [];
  const metalIonViews = selectedStructure ? getMetalIonViews(selectedStructure) : [];
  const stats = selectedStructure ? getStructureStats(selectedStructure) : null;
  const provenance = selectedStructure ? getStructureProvenanceView(selectedStructure) : null;
  const warnings = selectedStructure ? buildStructureWarnings(selectedStructure) : [];
  const residueRows = selectedStructure ? getResidueRows(selectedStructure, selectedChain?.chain_id ?? null) : [];
  const readiness = selectedStructure ? getStructureReadiness(selectedStructure) : null;
  const qualityChecks = selectedStructure ? getStructureQualityChecks(selectedStructure) : [];
  const workflowActions = selectedStructure ? getStructureWorkflowActions(selectedStructure, enzymeId) : [];
  const distanceMatrixRows = selectedStructure ? getDistanceMatrixRows(selectedStructure) : [];
  const previewAtoms = selectedStructure ? getStructurePreviewAtoms(selectedStructure) : [];

  useEffect(() => {
    setSelectedChainId(chainOptions[0]?.chain_id ?? null);
  }, [selectedStructureId, chainOptions]);

  function selectStructure(structure: StructureRecord) {
    setSelectedStructureId(structure.id);
    setSelectedChainId(null);
  }

  function handleUploadFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0] ?? null;
    setUploadNotice(null);
    if (file && !isStructureUploadFileName(file.name)) {
      setSelectedUploadFile(null);
      setError("Only .pdb and .cif structure files are supported.");
      if (uploadInputRef.current) {
        uploadInputRef.current.value = "";
      }
      return;
    }
    setError(null);
    setSelectedUploadFile(file);
  }

  async function handleStructureUpload() {
    if (!token || !selectedUploadFile || isUploadingStructure) {
      return;
    }
    setError(null);
    setUploadNotice(null);
    setIsUploadingStructure(true);
    try {
      const uploadedStructure = await uploadStructureFile(enzymeId, token, selectedUploadFile);
      setUploadNotice(summarizeStructureUploadResult(uploadedStructure));
      setSelectedUploadFile(null);
      if (uploadInputRef.current) {
        uploadInputRef.current.value = "";
      }
      await loadBundle(token, uploadedStructure.id);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to upload structure file.");
    } finally {
      setIsUploadingStructure(false);
    }
  }

  async function handleStructureDownload(structure: StructureRecord) {
    if (!token || !structure.artifact_id || downloadingStructureId) {
      return;
    }
    setError(null);
    setDownloadingStructureId(structure.id);
    try {
      const blob = await downloadStructureFile(enzymeId, structure.id, token);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = buildStructureDownloadFileName(structure);
      link.click();
      URL.revokeObjectURL(url);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to download structure file.");
    } finally {
      setDownloadingStructureId(null);
    }
  }

  function downloadDistanceMatrixCsv() {
    if (!selectedStructure || distanceMatrixRows.length === 0) {
      return;
    }
    const blob = new Blob([buildDistanceMatrixCsv(distanceMatrixRows)], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `ligand-distance-matrix-${selectedStructure.id}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  }

  function downloadResidueMappingCsv() {
    if (!selectedStructure || residueRows.length === 0) {
      return;
    }
    const blob = new Blob([buildResidueMappingCsv(residueRows)], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `residue-mapping-${selectedStructure.id}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  }

  function downloadStructureReportJson() {
    if (!selectedStructure) {
      return;
    }
    const blob = new Blob([
      buildStructureReportJson(selectedStructure, enzymeId, {
        selectedChainId: selectedChain?.chain_id ?? null
      })
    ], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `structure-report-${selectedStructure.id}.json`;
    link.click();
    URL.revokeObjectURL(url);
  }

  return (
    <main className="mx-auto max-w-7xl px-6 py-8">
      <header className="border-b border-slate-200 pb-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-sm font-medium text-slate-500">Structure analysis</p>
            <h1 className="mt-2 text-2xl font-semibold text-slate-950">
              {bundle?.enzyme.name ?? "Uploaded structures"}
            </h1>
            <p className="mt-2 text-sm text-slate-600">Entry id: {enzymeId}</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Link
              className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-800"
              href={`/enzymes/${enzymeId}`}
            >
              Back to record
            </Link>
            <button
              className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-800 disabled:cursor-not-allowed disabled:text-slate-400"
              disabled={!token || isLoading}
              onClick={() => token && void loadBundle(token)}
              type="button"
            >
              Refresh
            </button>
          </div>
        </div>
      </header>

      {error ? (
        <p className="mt-4 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          {error}
        </p>
      ) : null}
      {isLoading ? <p className="mt-6 text-sm text-slate-600">Loading structures...</p> : null}

      <section className="mt-6 rounded-md border border-slate-200 bg-white p-4">
        <div className="flex flex-wrap items-end gap-3">
          <label className="grid min-w-64 flex-1 gap-1 text-sm font-medium text-slate-700">
            Structure file
            <input
              accept={structureUploadAccept}
              className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-950 file:mr-3 file:rounded-md file:border-0 file:bg-slate-100 file:px-3 file:py-1.5 file:text-sm file:font-medium file:text-slate-700"
              onChange={handleUploadFileChange}
              ref={uploadInputRef}
              type="file"
            />
          </label>
          <button
            className="rounded-md bg-slate-950 px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:bg-slate-300"
            disabled={!selectedUploadFile || !token || isUploadingStructure}
            onClick={handleStructureUpload}
            type="button"
          >
            {isUploadingStructure ? "Uploading..." : "Upload structure"}
          </button>
        </div>
        {selectedUploadFile ? (
          <p className="mt-2 break-words text-xs text-slate-500">{selectedUploadFile.name}</p>
        ) : null}
        {uploadNotice ? (
          <p className="mt-3 rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800">
            {uploadNotice}
          </p>
        ) : null}
      </section>

      <section className="mt-6 grid gap-6 lg:grid-cols-[22rem_minmax(0,1fr)]">
        <aside className="rounded-md border border-slate-200 bg-white">
          <div className="border-b border-slate-200 px-4 py-3">
            <h2 className="text-base font-semibold text-slate-950">Structures</h2>
            <p className="mt-1 text-xs text-slate-500">{structures.length} records</p>
          </div>
          <div className="divide-y divide-slate-100">
            {structures.length > 0 ? (
              structures.map((structure) => (
                <button
                  className={`block w-full px-4 py-3 text-left text-sm ${
                    selectedStructure?.id === structure.id ? "bg-slate-100" : "bg-white hover:bg-slate-50"
                  }`}
                  key={structure.id}
                  onClick={() => selectStructure(structure)}
                  type="button"
                >
                  <span className="block font-medium text-slate-950">{structure.structure_type}</span>
                  <span className="mt-1 block text-xs text-slate-500">{structure.complex_state}</span>
                  <span className="mt-1 block break-words font-mono text-xs text-slate-500">
                    {structure.artifact?.object_key ?? structure.pdb_id ?? structure.id}
                  </span>
                </button>
              ))
            ) : (
              <p className="px-4 py-4 text-sm text-slate-500">No uploaded structures yet</p>
            )}
          </div>
        </aside>

        {selectedStructure && stats ? (
          <div className="grid gap-6">
            <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
              <MetricCard label="Chains" value={stats.chain_count} />
              <MetricCard label="Residues" value={stats.residue_count} />
              <MetricCard label="Ligands" value={stats.ligand_count} />
              <MetricCard label="Metals" value={stats.metal_count} />
              <MetricCard label="State" value={stats.complex_state} />
            </section>
            <section className="rounded-md border border-slate-200 bg-white p-4">
              <p className="text-xs font-medium uppercase text-slate-500">Database identifiers</p>
              <p className="mt-1 break-words font-mono text-sm text-slate-950">
                {stats.database_identifiers}
              </p>
            </section>

            <div className="flex flex-wrap justify-end gap-2">
              <button
                className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-800"
                onClick={downloadStructureReportJson}
                type="button"
              >
                Structure report
              </button>
            </div>

            {provenance ? <ProvenancePanel provenance={provenance} /> : null}
            {readiness ? <ReadinessPanel readiness={readiness} /> : null}
            <QualityChecksPanel checks={qualityChecks} />
            <WorkflowActions actions={workflowActions} />

            <section className="rounded-md border border-slate-200 bg-white">
              <div className="border-b border-slate-200 px-4 py-3">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <h2 className="text-base font-semibold text-slate-950">Structure preview</h2>
                    <p className="mt-1 break-words font-mono text-xs text-slate-500">
                      {stats.artifact_object_key}
                    </p>
                  </div>
                  <button
                    className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-800 disabled:cursor-not-allowed disabled:text-slate-400"
                    disabled={!token || !selectedStructure.artifact_id || downloadingStructureId === selectedStructure.id}
                    onClick={() => void handleStructureDownload(selectedStructure)}
                    type="button"
                  >
                    {downloadingStructureId === selectedStructure.id ? "Downloading..." : "Download file"}
                  </button>
                </div>
              </div>
              <div className="grid gap-4 p-4 lg:grid-cols-[minmax(0,1fr)_18rem]">
                <CoordinatePreview atoms={previewAtoms} />
                <div className="grid content-start gap-3">
                  <label className="grid gap-1 text-sm font-medium text-slate-700">
                    Chain
                    <select
                      className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-950"
                      onChange={(event) => setSelectedChainId(event.target.value)}
                      value={selectedChain?.chain_id ?? ""}
                    >
                      {chainOptions.map((chain) => (
                        <option key={`${chain.structure_id}-${chain.chain_id}`} value={chain.chain_id}>
                          Chain {chain.chain_id}
                        </option>
                      ))}
                    </select>
                  </label>
                  {selectedChain ? (
                    <dl className="grid gap-3 rounded-md border border-slate-200 p-3">
                      <Definition label="Residues" value={selectedChain.residue_count} />
                      <Definition label="Mapping" value={selectedChain.mapping_quality} />
                      <Definition label="Sequence" value={selectedChain.sequence} mono />
                    </dl>
                  ) : (
                    <p className="rounded-md border border-slate-200 p-3 text-sm text-slate-500">
                      No chain mapping available
                    </p>
                  )}
                </div>
              </div>
            </section>

            {warnings.length > 0 ? (
              <section className="rounded-md border border-amber-200 bg-amber-50 px-4 py-3">
                <h2 className="text-sm font-semibold text-amber-950">Structure warnings</h2>
                <ul className="mt-2 grid gap-1 text-sm text-amber-800">
                  {warnings.map((warning) => (
                    <li key={warning}>{warning}</li>
                  ))}
                </ul>
              </section>
            ) : null}

            <LigandTable ligands={ligandViews} />
            <MetalIonTable metalIons={metalIonViews} />
            <DistanceMatrixTable onDownloadCsv={downloadDistanceMatrixCsv} rows={distanceMatrixRows} />
            <ResidueMappingTable onDownloadCsv={downloadResidueMappingCsv} rows={residueRows} />
          </div>
        ) : (
          <section className="rounded-md border border-slate-200 bg-white p-6 text-sm text-slate-500">
            No structure record is available yet.
          </section>
        )}
      </section>
    </main>
  );
}

function QualityChecksPanel({ checks }: { checks: ReturnType<typeof getStructureQualityChecks> }) {
  return (
    <section className="rounded-md border border-slate-200 bg-white">
      <div className="border-b border-slate-200 px-4 py-3">
        <h2 className="text-base font-semibold text-slate-950">Structure quality checks</h2>
      </div>
      <div className="grid gap-3 p-4 md:grid-cols-2">
        {checks.map((check) => (
          <div className="flex items-start gap-3 rounded-md border border-slate-200 p-3" key={check.label}>
            <QualityDot status={check.status} />
            <div>
              <h3 className="text-sm font-semibold text-slate-950">{check.label}</h3>
              <p className="mt-1 text-sm text-slate-600">{check.detail}</p>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function QualityDot({ status }: { status: "pass" | "warn" | "fail" }) {
  const toneClass =
    status === "pass" ? "bg-emerald-500" : status === "warn" ? "bg-amber-500" : "bg-red-500";
  return <span aria-label={status} className={`mt-1 h-2.5 w-2.5 shrink-0 rounded-full ${toneClass}`} />;
}

function ReadinessPanel({ readiness }: { readiness: ReturnType<typeof getStructureReadiness> }) {
  const toneClass =
    readiness.status === "ready"
      ? "border-emerald-200 bg-emerald-50 text-emerald-900"
      : readiness.status === "limited"
        ? "border-sky-200 bg-sky-50 text-sky-900"
        : "border-amber-200 bg-amber-50 text-amber-900";

  return (
    <section className={`rounded-md border px-4 py-3 ${toneClass}`}>
      <h2 className="text-sm font-semibold">{readiness.title}</h2>
      <p className="mt-1 text-sm">{readiness.description}</p>
    </section>
  );
}

function WorkflowActions({ actions }: { actions: ReturnType<typeof getStructureWorkflowActions> }) {
  return (
    <section className="rounded-md border border-slate-200 bg-white">
      <div className="border-b border-slate-200 px-4 py-3">
        <h2 className="text-base font-semibold text-slate-950">Next analysis actions</h2>
      </div>
      <div className="grid gap-3 p-4 md:grid-cols-2">
        {actions.map((action) => (
          <div className="rounded-md border border-slate-200 p-3" key={action.label}>
            <div className="flex items-start justify-between gap-3">
              <h3 className="text-sm font-semibold text-slate-950">{action.label}</h3>
              <StatusBadge status={action.status} />
            </div>
            <p className="mt-2 text-sm text-slate-600">{action.description}</p>
            {action.href ? (
              <Link className="mt-3 inline-flex text-sm font-medium text-slate-950 underline underline-offset-2" href={action.href}>
                {action.cta_label ?? "Open analysis"}
              </Link>
            ) : null}
          </div>
        ))}
      </div>
    </section>
  );
}

function CoordinatePreview({ atoms }: { atoms: ReturnType<typeof getStructurePreviewAtoms> }) {
  const width = 640;
  const height = 360;
  if (atoms.length === 0) {
    return (
      <div className="grid min-h-72 place-items-center rounded-md border border-slate-200 bg-slate-950 px-4 text-center text-sm text-slate-300">
        No coordinate preview is available for this structure.
      </div>
    );
  }

  const minX = Math.min(...atoms.map((atom) => atom.x));
  const maxX = Math.max(...atoms.map((atom) => atom.x));
  const minY = Math.min(...atoms.map((atom) => atom.y));
  const maxY = Math.max(...atoms.map((atom) => atom.y));
  const minZ = Math.min(...atoms.map((atom) => atom.z));
  const maxZ = Math.max(...atoms.map((atom) => atom.z));
  const spanX = Math.max(maxX - minX, 1);
  const spanY = Math.max(maxY - minY, 1);
  const spanZ = Math.max(maxZ - minZ, 1);
  const projectedAtoms = atoms.map((atom) => {
    const normalizedX = (atom.x - minX) / spanX;
    const normalizedY = (atom.y - minY) / spanY;
    const normalizedZ = (atom.z - minZ) / spanZ;
    return {
      ...atom,
      px: 48 + normalizedX * (width - 96) + (normalizedZ - 0.5) * 42,
      py: 44 + (1 - normalizedY) * (height - 88) - (normalizedZ - 0.5) * 26,
      radius: atom.kind === "ligand" ? 7 : 4 + normalizedZ * 2
    };
  });
  const proteinLine = projectedAtoms
    .filter((atom) => atom.kind === "protein")
    .map((atom) => `${atom.px},${atom.py}`)
    .join(" ");

  return (
    <div className="relative min-h-72 overflow-hidden rounded-md border border-slate-200 bg-slate-950">
      <svg
        aria-label="Coordinate preview"
        className="h-full min-h-72 w-full"
        preserveAspectRatio="xMidYMid meet"
        role="img"
        viewBox={`0 0 ${width} ${height}`}
      >
        <rect fill="#020617" height={height} width={width} />
        <g opacity="0.22">
          <path d="M48 312H592M48 48V312M48 312L88 286M592 312L552 286" stroke="#94a3b8" strokeWidth="1" />
        </g>
        {proteinLine ? (
          <polyline fill="none" points={proteinLine} stroke="#67e8f9" strokeLinecap="round" strokeWidth="2" />
        ) : null}
        {projectedAtoms.map((atom) => (
          <g key={`${atom.kind}-${atom.chain_id}-${atom.residue_number}-${atom.label}`}>
            <circle
              cx={atom.px}
              cy={atom.py}
              fill={atom.kind === "ligand" ? "#fbbf24" : "#5eead4"}
              opacity={atom.kind === "ligand" ? "0.95" : "0.78"}
              r={atom.radius}
            />
            {atom.kind === "ligand" ? (
              <text fill="#fde68a" fontSize="12" x={atom.px + 10} y={atom.py - 8}>
                {atom.label}
              </text>
            ) : null}
          </g>
        ))}
      </svg>
      <div className="absolute bottom-3 left-3 right-3 rounded bg-slate-900/80 px-3 py-2 text-xs text-slate-200">
        Coordinate projection from parsed PDB/CIF atoms. Ligands are highlighted in amber.
      </div>
    </div>
  );
}

function StatusBadge({ status }: { status: "ready" | "reserved" | "blocked" }) {
  const toneClass =
    status === "ready"
      ? "border-emerald-200 bg-emerald-50 text-emerald-800"
      : status === "reserved"
        ? "border-slate-200 bg-slate-50 text-slate-600"
        : "border-amber-200 bg-amber-50 text-amber-800";

  return (
    <span className={`rounded-full border px-2 py-0.5 text-xs font-medium capitalize ${toneClass}`}>
      {status}
    </span>
  );
}

function ProvenancePanel({
  provenance
}: {
  provenance: ReturnType<typeof getStructureProvenanceView>;
}) {
  const toneClass =
    provenance.mode === "real"
      ? "border-emerald-200 bg-emerald-50 text-emerald-900"
      : provenance.mode === "fallback"
        ? "border-amber-200 bg-amber-50 text-amber-900"
        : "border-slate-200 bg-white text-slate-700";

  return (
    <section className={`rounded-md border px-4 py-3 ${toneClass}`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold">Source provenance</h2>
          <p className="mt-1 break-words font-mono text-xs">{provenance.label}</p>
        </div>
        {provenance.source_url ? (
          <a
            className="text-xs font-medium underline underline-offset-2"
            href={provenance.source_url}
            rel="noreferrer"
            target="_blank"
          >
            Source
          </a>
        ) : null}
      </div>
      {provenance.warning ? <p className="mt-2 text-sm">{provenance.warning}</p> : null}
    </section>
  );
}

function MetricCard({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="rounded-md border border-slate-200 bg-white p-4">
      <dt className="text-xs font-medium uppercase text-slate-500">{label}</dt>
      <dd className="mt-1 text-sm font-semibold text-slate-950">{value}</dd>
    </div>
  );
}

function Definition({ label, value, mono = false }: { label: string; value: number | string; mono?: boolean }) {
  return (
    <div>
      <dt className="text-xs font-medium uppercase text-slate-500">{label}</dt>
      <dd className={`mt-1 break-words text-sm text-slate-950 ${mono ? "font-mono" : ""}`}>{value}</dd>
    </div>
  );
}

function LigandTable({ ligands }: { ligands: ReturnType<typeof getLigandViews> }) {
  return (
    <section className="overflow-hidden rounded-md border border-slate-200 bg-white">
      <div className="border-b border-slate-200 px-4 py-3">
        <h2 className="text-base font-semibold text-slate-950">Ligands and neighboring residues</h2>
      </div>
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-slate-200 text-left text-sm">
          <thead className="bg-slate-50 text-xs uppercase text-slate-500">
            <tr>
              <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">Ligand</th>
              <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">Location</th>
              <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">Atoms</th>
              <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">4A</th>
              <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">6A</th>
              <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">8A</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 text-slate-700">
            {ligands.length > 0 ? (
              ligands.map((ligand) => (
                <tr key={`${ligand.ligand_code}-${ligand.location}`}>
                  <td className="px-4 py-3 font-mono text-slate-950">{ligand.ligand_code}</td>
                  <td className="px-4 py-3 font-mono text-xs">{ligand.location}</td>
                  <td className="px-4 py-3">{ligand.atom_count}</td>
                  <td className="min-w-56 px-4 py-3 text-xs">{ligand.nearest_residues["4A"].join(", ") || "-"}</td>
                  <td className="min-w-56 px-4 py-3 text-xs">{ligand.nearest_residues["6A"].join(", ") || "-"}</td>
                  <td className="min-w-56 px-4 py-3 text-xs">{ligand.nearest_residues["8A"].join(", ") || "-"}</td>
                </tr>
              ))
            ) : (
              <tr>
                <td className="px-4 py-4 text-slate-500" colSpan={6}>
                  No non-metal ligand detected
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function MetalIonTable({ metalIons }: { metalIons: ReturnType<typeof getMetalIonViews> }) {
  return (
    <section className="overflow-hidden rounded-md border border-slate-200 bg-white">
      <div className="border-b border-slate-200 px-4 py-3">
        <h2 className="text-base font-semibold text-slate-950">Metal ions</h2>
      </div>
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-slate-200 text-left text-sm">
          <thead className="bg-slate-50 text-xs uppercase text-slate-500">
            <tr>
              <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">Ion</th>
              <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">Location</th>
              <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">Atoms</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 text-slate-700">
            {metalIons.length > 0 ? (
              metalIons.map((metalIon) => (
                <tr key={`${metalIon.ligand_code}-${metalIon.location}`}>
                  <td className="px-4 py-3 font-mono text-slate-950">{metalIon.ligand_code}</td>
                  <td className="px-4 py-3 font-mono text-xs">{metalIon.location}</td>
                  <td className="px-4 py-3">{metalIon.atom_count}</td>
                </tr>
              ))
            ) : (
              <tr>
                <td className="px-4 py-4 text-slate-500" colSpan={3}>
                  No metal ions detected
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function DistanceMatrixTable({
  onDownloadCsv,
  rows
}: {
  onDownloadCsv: () => void;
  rows: ReturnType<typeof getDistanceMatrixRows>;
}) {
  return (
    <section className="overflow-hidden rounded-md border border-slate-200 bg-white">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-200 px-4 py-3">
        <div>
          <h2 className="text-base font-semibold text-slate-950">Ligand distance matrix</h2>
          <p className="mt-1 text-xs text-slate-500">
            Minimum atom distance between each detected ligand and mapped protein residues.
          </p>
        </div>
        <button
          className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-800 disabled:cursor-not-allowed disabled:text-slate-400"
          disabled={rows.length === 0}
          onClick={onDownloadCsv}
          type="button"
        >
          CSV
        </button>
      </div>
      <div className="max-h-80 overflow-auto">
        <table className="min-w-full divide-y divide-slate-200 text-left text-sm">
          <thead className="sticky top-0 bg-slate-50 text-xs uppercase text-slate-500">
            <tr>
              <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">Ligand</th>
              <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">Residue</th>
              <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">Sequence position</th>
              <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">Distance A</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 text-slate-700">
            {rows.length > 0 ? (
              rows.map((row) => (
                <tr key={`${row.ligand}-${row.residue}-${row.sequence_position}`}>
                  <td className="px-4 py-3 font-mono text-xs text-slate-950">{row.ligand}</td>
                  <td className="px-4 py-3 font-mono text-xs">{row.residue}</td>
                  <td className="px-4 py-3">{row.sequence_position}</td>
                  <td className="px-4 py-3">{row.distance_angstrom}</td>
                </tr>
              ))
            ) : (
              <tr>
                <td className="px-4 py-4 text-slate-500" colSpan={4}>
                  No ligand distance matrix available
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function ResidueMappingTable({
  onDownloadCsv,
  rows
}: {
  onDownloadCsv: () => void;
  rows: ReturnType<typeof getResidueRows>;
}) {
  return (
    <section className="overflow-hidden rounded-md border border-slate-200 bg-white">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-200 px-4 py-3">
        <h2 className="text-base font-semibold text-slate-950">Residue mapping</h2>
        <button
          className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-800 disabled:cursor-not-allowed disabled:text-slate-400"
          disabled={rows.length === 0}
          onClick={onDownloadCsv}
          type="button"
        >
          CSV
        </button>
      </div>
      <div className="max-h-96 overflow-auto">
        <table className="min-w-full divide-y divide-slate-200 text-left text-sm">
          <thead className="sticky top-0 bg-slate-50 text-xs uppercase text-slate-500">
            <tr>
              <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">Sequence position</th>
              <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">PDB residue</th>
              <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">Residue</th>
              <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">AA</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 text-slate-700">
            {rows.length > 0 ? (
              rows.map((row) => (
                <tr key={`${row.sequence_position}-${row.pdb_residue}`}>
                  <td className="px-4 py-3">{row.sequence_position}</td>
                  <td className="px-4 py-3 font-mono text-xs">{row.pdb_residue}</td>
                  <td className="px-4 py-3">{row.residue_name}</td>
                  <td className="px-4 py-3 font-mono">{row.one_letter}</td>
                </tr>
              ))
            ) : (
              <tr>
                <td className="px-4 py-4 text-slate-500" colSpan={4}>
                  No residue mapping available
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
