"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";

import { searchEnzyme } from "../../lib/api";
import type { SearchResponse } from "../../lib/types";
import { formatSearchMatchSubtitle, searchResultMatches } from "./search-utils";

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
