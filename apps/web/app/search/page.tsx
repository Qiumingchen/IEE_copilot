"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { ChangeEvent, FormEvent, useEffect, useState } from "react";

import { ApiRequestError, discoverEnzymeFromPdb, searchEnzyme, uploadStructureFile } from "../../lib/api";
import type { PdbDiscoveryHit, PdbDiscoveryResponse, SearchResponse } from "../../lib/types";
import {
  buildStructureAnalysisHref,
  type EnzymeSortMode,
  formatPdbDiscoveryMatchReason,
  formatPdbDiscoveryHitSubtitle,
  formatRecordCoverageBadges,
  formatSearchMatchSubtitle,
  paginateItems,
  pdbDiscoveryErrorMessage,
  sortPdbDiscoveryHits,
  sortSearchMatches,
  searchErrorMessage,
  searchResultMatches
} from "./search-utils";

const TOKEN_KEY = "iee-copilot-token";
const PAGE_SIZE_OPTIONS = [10, 20, 50];

export default function SearchPage() {
  const router = useRouter();
  const [query, setQuery] = useState("microbial transglutaminase");
  const [sourceOrganism, setSourceOrganism] = useState("");
  const [token, setToken] = useState<string | null>(null);
  const [result, setResult] = useState<SearchResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isSearching, setIsSearching] = useState(false);
  const [selectedPdbFile, setSelectedPdbFile] = useState<File | null>(null);
  const [pdbDiscovery, setPdbDiscovery] = useState<PdbDiscoveryResponse | null>(null);
  const [pdbDiscoveryError, setPdbDiscoveryError] = useState<string | null>(null);
  const [isDiscoveringPdb, setIsDiscoveringPdb] = useState(false);
  const [attachingHitId, setAttachingHitId] = useState<string | null>(null);
  const [searchSortMode, setSearchSortMode] = useState<EnzymeSortMode>("default");
  const [pdbSortMode, setPdbSortMode] = useState<EnzymeSortMode>("default");
  const [searchPage, setSearchPage] = useState(1);
  const [searchPageSize, setSearchPageSize] = useState(10);
  const [pdbPage, setPdbPage] = useState(1);
  const [pdbPageSize, setPdbPageSize] = useState(10);

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
    setSearchSortMode("default");
    setSearchPage(1);
    setIsSearching(true);

    try {
      const response = await searchEnzyme(query, token, searchPageSize, sourceOrganism);
      setResult(response);
    } catch (caught) {
      if (caught instanceof ApiRequestError && caught.status === 401) {
        window.localStorage.removeItem(TOKEN_KEY);
        setToken(null);
        setError(searchErrorMessage(caught));
        router.replace("/login");
        return;
      }
      setError(
        searchErrorMessage(
          caught instanceof ApiRequestError
            ? caught
            : { message: "Search failed. Please confirm the API is running." }
        )
      );
    } finally {
      setIsSearching(false);
    }
  }

  function handlePdbFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0] ?? null;
    setSelectedPdbFile(file);
    setPdbDiscovery(null);
    setPdbDiscoveryError(null);
    setPdbSortMode("default");
    setPdbPage(1);
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
    setPdbSortMode("default");
    setPdbPage(1);
    setIsDiscoveringPdb(true);

    try {
      const response = await discoverEnzymeFromPdb(selectedPdbFile, token);
      setPdbDiscovery(response);
    } catch (caught) {
      if (caught instanceof ApiRequestError && caught.status === 401) {
        window.localStorage.removeItem(TOKEN_KEY);
        setToken(null);
        setPdbDiscoveryError(pdbDiscoveryErrorMessage(caught));
        router.replace("/login");
        return;
      }
      setPdbDiscoveryError(
        pdbDiscoveryErrorMessage(
          caught instanceof ApiRequestError
            ? caught
            : { message: "PDB discovery failed. Please confirm the API is running." }
        )
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
    } catch (caught) {
      if (caught instanceof ApiRequestError && caught.status === 401) {
        window.localStorage.removeItem(TOKEN_KEY);
        setToken(null);
        setPdbDiscoveryError("Your login session has expired. Please sign in again before saving this structure.");
        router.replace("/login");
        return;
      }
      setPdbDiscoveryError(
        caught instanceof ApiRequestError && caught.detail
          ? caught.detail
          : "Unable to save the uploaded structure to this enzyme. Please try again from the structure page."
      );
    } finally {
      setAttachingHitId(null);
    }
  }

  const searchMatches = result ? sortSearchMatches(searchResultMatches(result), searchSortMode) : [];
  const pagedSearchMatches = paginateItems(searchMatches, searchPage, searchPageSize);
  const pdbHits = pdbDiscovery ? sortPdbDiscoveryHits(pdbDiscovery.hits, pdbSortMode) : [];
  const pagedPdbHits = paginateItems(pdbHits, pdbPage, pdbPageSize);

  return (
    <main className="mx-auto max-w-5xl px-6 py-8">
      <header className="border-b border-slate-200 pb-6">
        <p className="text-sm font-medium text-slate-500">Workbench search</p>
        <h1 className="mt-2 text-2xl font-semibold text-slate-950">Search enzyme</h1>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">
          Search by enzyme name, EC number, organism, UniProt ID, PDB ID, or AlphaFold ID.
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
            <label className="grid gap-1 text-sm font-medium text-slate-700 sm:col-span-2">
              Source organism
              <input
                className="min-w-0 rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-950 outline-none focus:border-slate-500"
                name="organism"
                placeholder="Optional, e.g. Bacillus subtilis"
                value={sourceOrganism}
                onChange={(event) => setSourceOrganism(event.target.value)}
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
          <div className="mt-3">
            <PageSizeSelect
              label="Requested results"
              pageSize={searchPageSize}
              onChange={(value) => {
                setSearchPageSize(value);
                setSearchPage(1);
              }}
            />
          </div>
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
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <label className="grid gap-1 text-sm font-medium text-slate-700">
              Sort enzymes
              <select
                className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-950 outline-none focus:border-slate-500"
                onChange={(event) => {
                  setPdbSortMode(event.target.value as EnzymeSortMode);
                  setPdbPage(1);
                }}
                value={pdbSortMode}
              >
                <option value="default">Best match</option>
                <option value="reviewed">Reviewed UniProt first</option>
                <option value="temperature">Highest optimal temperature</option>
                <option value="activity">Highest specific activity</option>
              </select>
            </label>
            <PageSizeSelect
              label="Results per page"
              pageSize={pdbPageSize}
              onChange={(value) => {
                setPdbPageSize(value);
                setPdbPage(1);
              }}
            />
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
              pagedPdbHits.items.map((hit) => (
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
                      <MetricBadges enzyme={hit.enzyme} />
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="rounded bg-emerald-50 px-2 py-1 text-xs font-medium text-emerald-700">
                        {formatPdbDiscoveryMatchReason(hit)}
                      </span>
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
          {pdbDiscovery.hits.length > 0 ? (
            <PaginationControls
              page={pagedPdbHits.page}
              pageCount={pagedPdbHits.pageCount}
              totalCount={pdbHits.length}
              onPrevious={() => setPdbPage((page) => Math.max(1, page - 1))}
              onNext={() => setPdbPage((page) => Math.min(pagedPdbHits.pageCount, page + 1))}
            />
          ) : null}
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
              <label className="grid gap-1 text-sm font-medium text-slate-700">
                Sort enzymes
                <select
                  className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-950 outline-none focus:border-slate-500"
                  onChange={(event) => {
                    setSearchSortMode(event.target.value as EnzymeSortMode);
                    setSearchPage(1);
                  }}
                  value={searchSortMode}
                >
                  <option value="default">Recommended</option>
                  <option value="reviewed">Reviewed UniProt first</option>
                  <option value="temperature">Highest optimal temperature</option>
                  <option value="activity">Highest specific activity</option>
                </select>
              </label>
              <PageSizeSelect
                label="Results per page"
                pageSize={searchPageSize}
                onChange={(value) => {
                  setSearchPageSize(value);
                  setSearchPage(1);
                }}
              />
              <Link
                className="self-end rounded-md bg-slate-950 px-3 py-2 text-sm font-medium text-white"
                href={`/jobs/${result.job_id}`}
              >
                Analysis job
              </Link>
            </div>
          </div>

          <div className="mt-5 grid gap-3">
            {pagedSearchMatches.items.map((match) => (
              <SearchMatchCard key={match.id} match={match} />
            ))}
          </div>
          <PaginationControls
            page={pagedSearchMatches.page}
            pageCount={pagedSearchMatches.pageCount}
            totalCount={searchMatches.length}
            onPrevious={() => setSearchPage((page) => Math.max(1, page - 1))}
            onNext={() => setSearchPage((page) => Math.min(pagedSearchMatches.pageCount, page + 1))}
          />
        </section>
      ) : null}

    </main>
  );
}

function PageSizeSelect({
  label,
  pageSize,
  onChange
}: {
  label: string;
  pageSize: number;
  onChange: (pageSize: number) => void;
}) {
  return (
    <label className="grid gap-1 text-sm font-medium text-slate-700">
      {label}
      <select
        className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-950 outline-none focus:border-slate-500"
        onChange={(event) => onChange(Number(event.target.value))}
        value={pageSize}
      >
        {PAGE_SIZE_OPTIONS.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
    </label>
  );
}

function PaginationControls({
  page,
  pageCount,
  totalCount,
  onPrevious,
  onNext
}: {
  page: number;
  pageCount: number;
  totalCount: number;
  onPrevious: () => void;
  onNext: () => void;
}) {
  return (
    <div className="mt-4 flex flex-wrap items-center justify-between gap-3 text-sm text-slate-600">
      <span>
        Page {page} of {pageCount}, {totalCount} total
      </span>
      <div className="flex gap-2">
        <button
          className="rounded-md border border-slate-300 bg-white px-3 py-2 font-medium text-slate-700 disabled:cursor-not-allowed disabled:text-slate-300"
          disabled={page <= 1}
          onClick={onPrevious}
          type="button"
        >
          Previous
        </button>
        <button
          className="rounded-md border border-slate-300 bg-white px-3 py-2 font-medium text-slate-700 disabled:cursor-not-allowed disabled:text-slate-300"
          disabled={page >= pageCount}
          onClick={onNext}
          type="button"
        >
          Next
        </button>
      </div>
    </div>
  );
}

function MetricBadges({ enzyme }: { enzyme: SearchResponse["enzyme"] }) {
  const badges = [
    enzyme.uniprot_reviewed ? "Reviewed UniProt" : null,
    enzyme.optimal_temperature !== null ? `Topt ${enzyme.optimal_temperature} degC` : null,
    enzyme.specific_activity !== null ? `Activity ${enzyme.specific_activity}` : null,
    ...formatRecordCoverageBadges(enzyme)
  ].filter(Boolean);

  if (badges.length === 0) {
    return null;
  }

  return (
    <div className="mt-3 flex flex-wrap gap-2">
      {badges.map((badge) => (
        <span className="rounded bg-sky-50 px-2 py-1 text-xs font-medium text-sky-700" key={badge}>
          {badge}
        </span>
      ))}
    </div>
  );
}

function SearchMatchCard({ match }: { match: SearchResponse["matches"][number] }) {
  const subtitle = formatSearchMatchSubtitle(match);

  return (
    <Link
      className="rounded-md border border-slate-200 bg-white p-4 transition hover:border-slate-400 hover:bg-slate-50"
      href={`/enzymes/${match.id}`}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold text-slate-950">{match.name}</h3>
          {subtitle ? <p className="mt-1 text-sm text-slate-600">{subtitle}</p> : null}
          <MetricBadges enzyme={match} />
        </div>
        <span className="rounded bg-slate-100 px-2 py-1 text-xs font-medium text-slate-700">
          {match.source}
        </span>
      </div>
    </Link>
  );
}
