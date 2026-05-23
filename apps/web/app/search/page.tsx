"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { ChangeEvent, FormEvent, useEffect, useState } from "react";

import { discoverEnzymeFromPdb, searchEnzyme, uploadStructureFile } from "../../lib/api";
import type { PdbDiscoveryHit, PdbDiscoveryResponse, SearchResponse } from "../../lib/types";
import {
  buildStructureAnalysisHref,
  formatPdbDiscoveryHitSubtitle,
  formatSearchMatchSubtitle,
  searchResultMatches
} from "./search-utils";

const TOKEN_KEY = "iee-copilot-token";

export default function SearchPage() {
  const router = useRouter();
  const [query, setQuery] = useState("microbial transglutaminase");
  const [token, setToken] = useState<string | null>(null);
  const [result, setResult] = useState<SearchResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isSearching, setIsSearching] = useState(false);
  const [selectedPdbFile, setSelectedPdbFile] = useState<File | null>(null);
  const [pdbDiscovery, setPdbDiscovery] = useState<PdbDiscoveryResponse | null>(null);
  const [pdbDiscoveryError, setPdbDiscoveryError] = useState<string | null>(null);
  const [isDiscoveringPdb, setIsDiscoveringPdb] = useState(false);
  const [attachingHitId, setAttachingHitId] = useState<string | null>(null);

  useEffect(() => {
    const storedToken = window.localStorage.getItem(TOKEN_KEY);
    if (!storedToken) {
      router.replace("/login");
      return;
    }
    setToken(storedToken);
  }, [router]);

  async function handleSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token) {
      router.replace("/login");
      return;
    }

    setError(null);
    setResult(null);
    setIsSearching(true);

    try {
      const response = await searchEnzyme(query, token);
      setResult(response);
    } catch {
      setError("Search failed. Please confirm the API is running and your login is still valid.");
    } finally {
      setIsSearching(false);
    }
  }

  function handlePdbFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0] ?? null;
    setSelectedPdbFile(file);
    setPdbDiscovery(null);
    setPdbDiscoveryError(null);
  }

  async function handlePdbDiscovery(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token) {
      router.replace("/login");
      return;
    }
    if (!selectedPdbFile) {
      setPdbDiscoveryError("Choose a PDB or mmCIF file before running discovery.");
      return;
    }

    setPdbDiscovery(null);
    setPdbDiscoveryError(null);
    setIsDiscoveringPdb(true);

    try {
      const response = await discoverEnzymeFromPdb(selectedPdbFile, token);
      setPdbDiscovery(response);
    } catch {
      setPdbDiscoveryError(
        "PDB discovery failed. Please confirm the file contains a protein chain and the API is running."
      );
    } finally {
      setIsDiscoveringPdb(false);
    }
  }

  async function handleAttachDiscoveredStructure(hit: PdbDiscoveryHit) {
    if (!token) {
      router.replace("/login");
      return;
    }
    if (!selectedPdbFile || attachingHitId) {
      return;
    }

    setPdbDiscoveryError(null);
    setAttachingHitId(hit.enzyme.id);
    try {
      const structure = await uploadStructureFile(hit.enzyme.id, token, selectedPdbFile);
      router.push(buildStructureAnalysisHref(hit.enzyme.id, structure.id));
    } catch {
      setPdbDiscoveryError(
        "Unable to save the uploaded structure to this enzyme. Please try again from the structure page."
      );
    } finally {
      setAttachingHitId(null);
    }
  }

  return (
    <main className="mx-auto max-w-5xl px-6 py-8">
      <header className="border-b border-slate-200 pb-6">
        <p className="text-sm font-medium text-slate-500">Workbench search</p>
        <h1 className="mt-2 text-2xl font-semibold text-slate-950">Search enzyme</h1>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">
          Search by enzyme name, EC number, organism, UniProt ID, or PDB ID.
        </p>
      </header>

      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <section className="rounded-md border border-slate-200 bg-white p-5">
          <div>
            <p className="text-sm font-medium text-slate-500">Known enzyme</p>
            <h2 className="mt-1 text-lg font-semibold text-slate-950">Search by identifier</h2>
          </div>
          <form className="mt-4 grid gap-3 sm:grid-cols-[1fr_auto]" onSubmit={handleSearch}>
            <label className="grid gap-1 text-sm font-medium text-slate-700">
              Query
              <input
                className="min-w-0 rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-950 outline-none focus:border-slate-500"
                name="query"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
              />
            </label>
            <button
              className="self-end rounded-md bg-slate-950 px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:bg-slate-400"
              disabled={isSearching || !query.trim()}
              type="submit"
            >
              {isSearching ? "Searching..." : "Search"}
            </button>
          </form>
        </section>

        <section className="rounded-md border border-slate-200 bg-white p-5">
          <div>
            <p className="text-sm font-medium text-slate-500">Unknown structure</p>
            <h2 className="mt-1 text-lg font-semibold text-slate-950">Discover from PDB</h2>
          </div>
          <form className="mt-4 grid gap-3 sm:grid-cols-[1fr_auto]" onSubmit={handlePdbDiscovery}>
            <label className="grid gap-1 text-sm font-medium text-slate-700">
              PDB or mmCIF file
              <input
                accept=".pdb,.cif,.mmcif,chemical/x-pdb"
                className="min-w-0 rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-950 file:mr-3 file:rounded file:border-0 file:bg-slate-100 file:px-3 file:py-1 file:text-sm file:font-medium file:text-slate-700"
                name="pdbFile"
                onChange={handlePdbFileChange}
                type="file"
              />
            </label>
            <button
              className="self-end rounded-md bg-slate-950 px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:bg-slate-400"
              disabled={isDiscoveringPdb || !selectedPdbFile}
              type="submit"
            >
              {isDiscoveringPdb ? "Discovering..." : "Upload PDB"}
            </button>
          </form>
        </section>
      </div>

      {error ? (
        <p className="mt-4 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          {error}
        </p>
      ) : null}

      {pdbDiscoveryError ? (
        <p className="mt-4 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          {pdbDiscoveryError}
        </p>
      ) : null}

      {pdbDiscovery ? (
        <section className="mt-8 border-t border-slate-200 pt-6">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="text-sm font-medium text-slate-500">PDB discovery</p>
              <h2 className="mt-1 text-xl font-semibold text-slate-950">
                {pdbDiscovery.hits.length} similar enzyme entries
              </h2>
              <p className="mt-1 text-sm text-slate-600">
                Query chain {pdbDiscovery.query_chain_id} from {pdbDiscovery.file_name}
              </p>
            </div>
            <span className="rounded bg-slate-100 px-2 py-1 text-xs font-medium text-slate-700">
              {pdbDiscovery.complex_state}
            </span>
          </div>

          <dl className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
            <div className="rounded-md border border-slate-200 bg-white p-4">
              <dt className="text-xs font-medium uppercase text-slate-500">Detected name</dt>
              <dd className="mt-1 text-sm text-slate-950">
                {pdbDiscovery.metadata.enzyme_name ?? pdbDiscovery.metadata.title ?? "Not reported"}
              </dd>
            </div>
            <div className="rounded-md border border-slate-200 bg-white p-4">
              <dt className="text-xs font-medium uppercase text-slate-500">Organism</dt>
              <dd className="mt-1 text-sm text-slate-950">
                {pdbDiscovery.metadata.organism ?? "Not reported"}
              </dd>
            </div>
            <div className="rounded-md border border-slate-200 bg-white p-4">
              <dt className="text-xs font-medium uppercase text-slate-500">PDB ID</dt>
              <dd className="mt-1 text-sm text-slate-950">
                {pdbDiscovery.metadata.pdb_id ?? "Uploaded file"}
              </dd>
            </div>
            <div className="rounded-md border border-slate-200 bg-white p-4">
              <dt className="text-xs font-medium uppercase text-slate-500">AlphaFold ID</dt>
              <dd className="mt-1 text-sm text-slate-950">
                {pdbDiscovery.metadata.alphafold_id ?? "Not reported"}
              </dd>
            </div>
            <div className="rounded-md border border-slate-200 bg-white p-4">
              <dt className="text-xs font-medium uppercase text-slate-500">Query sequence</dt>
              <dd className="mt-1 text-sm text-slate-950">
                {pdbDiscovery.query_sequence.length} aa, {pdbDiscovery.chains.length} chain
                {pdbDiscovery.chains.length === 1 ? "" : "s"}
              </dd>
            </div>
          </dl>

          <div className="mt-5 grid gap-3">
            {pdbDiscovery.hits.length > 0 ? (
              pdbDiscovery.hits.map((hit) => (
                <article
                  className="rounded-md border border-slate-200 bg-white p-4 transition hover:border-slate-400 hover:bg-slate-50"
                  key={hit.enzyme.id}
                >
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <Link
                        className="text-base font-semibold text-slate-950 hover:underline"
                        href={`/enzymes/${hit.enzyme.id}`}
                      >
                        {hit.enzyme.name}
                      </Link>
                      <p className="mt-1 text-sm text-slate-600">
                        {formatSearchMatchSubtitle(hit.enzyme)}
                      </p>
                      <p className="mt-2 text-xs font-medium text-slate-500">
                        {formatPdbDiscoveryHitSubtitle(hit)}
                      </p>
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="rounded bg-slate-100 px-2 py-1 text-xs font-medium text-slate-700">
                        {hit.enzyme.source}
                      </span>
                      <button
                        className="rounded-md bg-slate-950 px-3 py-2 text-xs font-medium text-white disabled:cursor-not-allowed disabled:bg-slate-300"
                        disabled={!selectedPdbFile || Boolean(attachingHitId)}
                        onClick={() => void handleAttachDiscoveredStructure(hit)}
                        type="button"
                      >
                        {attachingHitId === hit.enzyme.id ? "Saving..." : "Use uploaded structure"}
                      </button>
                    </div>
                  </div>
                </article>
              ))
            ) : (
              <p className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
                No local homologs passed the current identity and coverage filters.
              </p>
            )}
          </div>
        </section>
      ) : null}

      {result ? (
        <section className="mt-8 border-t border-slate-200 pt-6">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-sm font-medium text-slate-500">Search results</p>
              <h2 className="mt-1 text-xl font-semibold text-slate-950">
                {searchResultMatches(result).length} enzyme entries
              </h2>
            </div>
            <div className="flex gap-2">
              <Link
                className="rounded-md bg-slate-950 px-3 py-2 text-sm font-medium text-white"
                href={`/jobs/${result.job_id}`}
              >
                Analysis job
              </Link>
            </div>
          </div>

          <div className="mt-5 grid gap-3">
            {searchResultMatches(result).map((match) => (
              <Link
                className="rounded-md border border-slate-200 bg-white p-4 transition hover:border-slate-400 hover:bg-slate-50"
                href={`/enzymes/${match.id}`}
                key={match.id}
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <h3 className="text-base font-semibold text-slate-950">{match.name}</h3>
                    <p className="mt-1 text-sm text-slate-600">{formatSearchMatchSubtitle(match)}</p>
                  </div>
                  <span className="rounded bg-slate-100 px-2 py-1 text-xs font-medium text-slate-700">
                    {match.source}
                  </span>
                </div>
              </Link>
            ))}
          </div>

          <dl className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <div className="rounded-md border border-slate-200 bg-white p-4">
              <dt className="text-xs font-medium uppercase text-slate-500">Cache</dt>
              <dd className="mt-1 text-sm text-slate-950">{result.cache_status}</dd>
            </div>
            <div className="rounded-md border border-slate-200 bg-white p-4">
              <dt className="text-xs font-medium uppercase text-slate-500">Query kind</dt>
              <dd className="mt-1 text-sm text-slate-950">{result.query_kind}</dd>
            </div>
            <div className="rounded-md border border-slate-200 bg-white p-4">
              <dt className="text-xs font-medium uppercase text-slate-500">Module</dt>
              <dd className="mt-1 text-sm text-slate-950">{result.module}</dd>
            </div>
          </dl>
        </section>
      ) : null}

    </main>
  );
}
