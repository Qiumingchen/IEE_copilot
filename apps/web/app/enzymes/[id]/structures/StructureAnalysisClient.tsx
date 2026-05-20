"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { getEnzymeRecordBundle } from "../../../../lib/api";
import type { EnzymeRecordBundle, StructureRecord } from "../../../../lib/types";
import {
  buildStructureWarnings,
  getChainOptions,
  getDefaultStructureId,
  getLigandViews,
  getResidueRows,
  getStructureStats
} from "./structure-utils";

const TOKEN_KEY = "iee-copilot-token";

type StructureAnalysisClientProps = {
  enzymeId: string;
};

export default function StructureAnalysisClient({ enzymeId }: StructureAnalysisClientProps) {
  const router = useRouter();
  const [token, setToken] = useState<string | null>(null);
  const [bundle, setBundle] = useState<EnzymeRecordBundle | null>(null);
  const [selectedStructureId, setSelectedStructureId] = useState<string | null>(null);
  const [selectedChainId, setSelectedChainId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function loadBundle(nextToken: string) {
    setError(null);
    setIsLoading(true);
    try {
      const nextBundle = await getEnzymeRecordBundle(enzymeId, nextToken);
      setBundle(nextBundle);
      setSelectedStructureId((current) => current ?? getDefaultStructureId(nextBundle.structures));
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
  const stats = selectedStructure ? getStructureStats(selectedStructure) : null;
  const warnings = selectedStructure ? buildStructureWarnings(selectedStructure) : [];
  const residueRows = selectedStructure ? getResidueRows(selectedStructure, selectedChain?.chain_id ?? null) : [];

  useEffect(() => {
    setSelectedChainId(chainOptions[0]?.chain_id ?? null);
  }, [selectedStructureId, chainOptions]);

  function selectStructure(structure: StructureRecord) {
    setSelectedStructureId(structure.id);
    setSelectedChainId(null);
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

            <section className="rounded-md border border-slate-200 bg-white">
              <div className="border-b border-slate-200 px-4 py-3">
                <h2 className="text-base font-semibold text-slate-950">Structure preview</h2>
                <p className="mt-1 break-words font-mono text-xs text-slate-500">
                  {stats.artifact_object_key}
                </p>
              </div>
              <div className="grid gap-4 p-4 lg:grid-cols-[minmax(0,1fr)_18rem]">
                <div className="relative min-h-72 overflow-hidden rounded-md border border-slate-200 bg-slate-950">
                  <div className="absolute inset-0 grid place-items-center">
                    <div className="h-36 w-36 rotate-45 rounded-md border border-cyan-300/70 bg-cyan-300/10 shadow-[0_0_60px_rgba(103,232,249,0.28)]" />
                    <div className="absolute h-20 w-20 rounded-full border border-emerald-300/80 bg-emerald-300/10 shadow-[0_0_40px_rgba(110,231,183,0.22)]" />
                    <div className="absolute h-2 w-2 rounded-full bg-amber-300 shadow-[0_0_24px_rgba(252,211,77,0.9)]" />
                  </div>
                  <div className="absolute bottom-3 left-3 right-3 rounded bg-slate-900/80 px-3 py-2 text-xs text-slate-200">
                    Coordinate-aware 3D viewer slot. Parsed chains and ligand contacts are shown below.
                  </div>
                </div>
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
            <ResidueMappingTable rows={residueRows} />
          </div>
        ) : (
          <section className="rounded-md border border-slate-200 bg-white p-6 text-sm text-slate-500">
            Upload a PDB or CIF file from the enzyme record page to start structure analysis.
          </section>
        )}
      </section>
    </main>
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

function ResidueMappingTable({
  rows
}: {
  rows: Array<{ sequence_position: string | number; pdb_residue: string; residue_name: string; one_letter: string }>;
}) {
  return (
    <section className="overflow-hidden rounded-md border border-slate-200 bg-white">
      <div className="border-b border-slate-200 px-4 py-3">
        <h2 className="text-base font-semibold text-slate-950">Residue mapping</h2>
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
