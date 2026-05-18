"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";

import { searchEnzyme } from "../../lib/api";
import type { SearchResponse } from "../../lib/types";

const TOKEN_KEY = "iee-copilot-token";

export default function SearchPage() {
  const router = useRouter();
  const [query, setQuery] = useState("microbial transglutaminase");
  const [token, setToken] = useState<string | null>(null);
  const [result, setResult] = useState<SearchResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isSearching, setIsSearching] = useState(false);

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

  return (
    <main className="mx-auto max-w-5xl px-6 py-8">
      <header className="border-b border-slate-200 pb-6">
        <p className="text-sm font-medium text-slate-500">Workbench search</p>
        <h1 className="mt-2 text-2xl font-semibold text-slate-950">Search enzyme</h1>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">
          Search by enzyme name, EC number, organism, UniProt ID, or PDB ID.
        </p>
      </header>

      <form className="mt-6 grid gap-3 sm:grid-cols-[1fr_auto]" onSubmit={handleSearch}>
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

      {error ? (
        <p className="mt-4 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          {error}
        </p>
      ) : null}

      {result ? (
        <section className="mt-8 border-t border-slate-200 pt-6">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-sm font-medium text-slate-500">Search result</p>
              <h2 className="mt-1 text-xl font-semibold text-slate-950">{result.enzyme.name}</h2>
            </div>
            <div className="flex gap-2">
              <Link
                className="rounded-md border border-slate-300 px-3 py-2 text-sm font-medium text-slate-800"
                href={`/enzymes/${result.enzyme.id}`}
              >
                Enzyme detail
              </Link>
              <Link
                className="rounded-md bg-slate-950 px-3 py-2 text-sm font-medium text-white"
                href={`/jobs/${result.job_id}`}
              >
                Analysis job
              </Link>
            </div>
          </div>

          <dl className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <div className="rounded-md border border-slate-200 bg-white p-4">
              <dt className="text-xs font-medium uppercase text-slate-500">Organism</dt>
              <dd className="mt-1 text-sm text-slate-950">{result.enzyme.organism ?? "Not reported"}</dd>
            </div>
            <div className="rounded-md border border-slate-200 bg-white p-4">
              <dt className="text-xs font-medium uppercase text-slate-500">EC number</dt>
              <dd className="mt-1 text-sm text-slate-950">{result.enzyme.ec_number ?? "Not reported"}</dd>
            </div>
            <div className="rounded-md border border-slate-200 bg-white p-4">
              <dt className="text-xs font-medium uppercase text-slate-500">UniProt</dt>
              <dd className="mt-1 text-sm text-slate-950">{result.enzyme.uniprot_id ?? "Not linked"}</dd>
            </div>
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

      <section className="mt-8 border-t border-slate-200 pt-6">
        <h2 className="text-base font-semibold text-slate-950">PDB upload</h2>
        <p className="mt-2 text-sm leading-6 text-slate-600">
          Apo and enzyme-substrate complex upload enters this workflow after the skeleton is stable.
        </p>
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <div className="rounded-md border border-slate-200 p-4">
            <p className="text-sm font-medium text-slate-950">Apo structure</p>
            <p className="mt-1 text-sm text-slate-600">Upload placeholder</p>
          </div>
          <div className="rounded-md border border-slate-200 p-4">
            <p className="text-sm font-medium text-slate-950">Enzyme-substrate complex</p>
            <p className="mt-1 text-sm text-slate-600">Upload placeholder</p>
          </div>
        </div>
      </section>
    </main>
  );
}
