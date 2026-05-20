"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import {
  getEnzymeRecordBundle,
  getPropertyRanking
} from "../../../../lib/api";
import type {
  EnzymeRecordBundle,
  PropertyRankingMode,
  PropertyRankingResponse
} from "../../../../lib/types";
import {
  buildPropertyOptions,
  formatAssayContext,
  formatRankingValue,
  summarizeRankingGroup
} from "./property-dashboard-utils";

const TOKEN_KEY = "iee-copilot-token";

type PropertyDashboardClientProps = {
  enzymeId: string;
};

const rankingModes: Array<{
  value: PropertyRankingMode;
  label: string;
}> = [
  { value: "reported_value", label: "Reported values" },
  { value: "condition_grouped", label: "Same-condition groups" }
];

export default function PropertyDashboardClient({ enzymeId }: PropertyDashboardClientProps) {
  const router = useRouter();
  const [token, setToken] = useState<string | null>(null);
  const [bundle, setBundle] = useState<EnzymeRecordBundle | null>(null);
  const [selectedPropertyType, setSelectedPropertyType] = useState("optimal_temperature");
  const [rankingMode, setRankingMode] = useState<PropertyRankingMode>("reported_value");
  const [ranking, setRanking] = useState<PropertyRankingResponse | null>(null);
  const [isLoadingBundle, setIsLoadingBundle] = useState(true);
  const [isLoadingRanking, setIsLoadingRanking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const propertyOptions = useMemo(
    () => buildPropertyOptions(bundle?.properties ?? []),
    [bundle?.properties]
  );

  useEffect(() => {
    const storedToken = window.localStorage.getItem(TOKEN_KEY);
    if (!storedToken) {
      router.replace("/login");
      return;
    }
    setToken(storedToken);
    void loadBundle(storedToken);
  }, [enzymeId, router]);

  useEffect(() => {
    if (!token) {
      return;
    }
    void loadRanking(token, selectedPropertyType, rankingMode);
  }, [token, selectedPropertyType, rankingMode]);

  async function loadBundle(nextToken: string) {
    setError(null);
    setIsLoadingBundle(true);
    try {
      const nextBundle = await getEnzymeRecordBundle(enzymeId, nextToken);
      setBundle(nextBundle);
      if (nextBundle.properties.length > 0) {
        setSelectedPropertyType(nextBundle.properties[0].property_type);
      }
    } catch {
      setError("Unable to load property dashboard. Please check the API service and your login.");
    } finally {
      setIsLoadingBundle(false);
    }
  }

  async function loadRanking(
    nextToken: string,
    propertyType: string,
    nextRankingMode: PropertyRankingMode
  ) {
    setError(null);
    setIsLoadingRanking(true);
    try {
      setRanking(await getPropertyRanking(enzymeId, nextToken, propertyType, nextRankingMode));
    } catch {
      setRanking(null);
      setError("Unable to load property ranking.");
    } finally {
      setIsLoadingRanking(false);
    }
  }

  const currentPropertyRecords =
    bundle?.properties.filter((record) => record.property_type === selectedPropertyType) ?? [];

  return (
    <main className="min-h-screen px-4 py-6 sm:px-6 lg:px-8">
      <section className="border-b border-slate-200 pb-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-sm font-medium text-slate-500">Property dashboard</p>
            <h1 className="mt-2 text-2xl font-semibold text-slate-950">
              {bundle?.enzyme.name ?? "Enzyme properties"}
            </h1>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
              Compare reported enzyme properties with source conditions kept visible.
            </p>
          </div>
          <Link
            className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700"
            href={`/enzymes/${enzymeId}`}
          >
            Detail
          </Link>
        </div>
      </section>

      {error ? (
        <div className="mt-5 rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      ) : null}

      <section className="mt-6 grid gap-4 lg:grid-cols-[minmax(0,280px)_1fr]">
        <aside className="rounded-md border border-slate-200 bg-white p-4">
          <label className="text-sm font-medium text-slate-700" htmlFor="property-type">
            Property type
          </label>
          <select
            className="mt-2 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900"
            id="property-type"
            onChange={(event) => setSelectedPropertyType(event.target.value)}
            value={selectedPropertyType}
          >
            {propertyOptions.map((propertyType) => (
              <option key={propertyType} value={propertyType}>
                {propertyType}
              </option>
            ))}
          </select>

          <div className="mt-5">
            <p className="text-sm font-medium text-slate-700">Ranking mode</p>
            <div className="mt-2 grid gap-2">
              {rankingModes.map((mode) => (
                <button
                  className={`rounded-md border px-3 py-2 text-left text-sm font-medium ${
                    rankingMode === mode.value
                      ? "border-slate-950 bg-slate-950 text-white"
                      : "border-slate-300 bg-white text-slate-700"
                  }`}
                  key={mode.value}
                  onClick={() => setRankingMode(mode.value)}
                  type="button"
                >
                  {mode.label}
                </button>
              ))}
            </div>
          </div>

          <div className="mt-5 rounded-md bg-slate-50 p-3 text-sm text-slate-600">
            <p className="font-medium text-slate-900">{currentPropertyRecords.length} local records</p>
            <p className="mt-1">Source, unit, substrate, pH and temperature remain attached to each row.</p>
          </div>
        </aside>

        <section className="min-w-0 rounded-md border border-slate-200 bg-white">
          <div className="border-b border-slate-200 px-4 py-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="text-base font-semibold text-slate-950">
                  {selectedPropertyType} ranking
                </h2>
                <p className="mt-1 text-sm text-slate-500">
                  {isLoadingRanking ? "Loading ranking..." : `${ranking?.items.length ?? 0} ranked records`}
                </p>
              </div>
              <button
                className="rounded-md border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 disabled:text-slate-400"
                disabled={!token || isLoadingRanking}
                onClick={() => token && void loadRanking(token, selectedPropertyType, rankingMode)}
                type="button"
              >
                Refresh
              </button>
            </div>
            {ranking?.comparison_warnings.length ? (
              <div className="mt-3 grid gap-2">
                {ranking.comparison_warnings.map((warning) => (
                  <p
                    className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800"
                    key={warning}
                  >
                    {warning}
                  </p>
                ))}
              </div>
            ) : null}
          </div>

          {isLoadingBundle || isLoadingRanking ? (
            <div className="px-4 py-10 text-sm text-slate-500">Loading property data...</div>
          ) : rankingMode === "condition_grouped" ? (
            <GroupedRanking ranking={ranking} />
          ) : (
            <ReportedRanking ranking={ranking} />
          )}
        </section>
      </section>
    </main>
  );
}

function ReportedRanking({ ranking }: { ranking: PropertyRankingResponse | null }) {
  if (!ranking || ranking.items.length === 0) {
    return <EmptyState />;
  }

  return (
    <div className="overflow-x-auto">
      <table className="min-w-full divide-y divide-slate-200 text-sm">
        <thead className="bg-slate-50 text-left text-xs font-medium uppercase text-slate-500">
          <tr>
            <th className="px-4 py-3">Rank</th>
            <th className="px-4 py-3">Enzyme</th>
            <th className="px-4 py-3">Value</th>
            <th className="px-4 py-3">Assay context</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {ranking.items.map((item) => (
            <tr key={item.property_record_id}>
              <td className="whitespace-nowrap px-4 py-3 font-medium text-slate-900">#{item.rank}</td>
              <td className="px-4 py-3">
                <p className="font-medium text-slate-950">{item.enzyme_name}</p>
                <p className="text-xs text-slate-500">{item.organism ?? "-"}</p>
              </td>
              <td className="whitespace-nowrap px-4 py-3 text-slate-700">{formatRankingValue(item)}</td>
              <td className="px-4 py-3 text-slate-600">{formatAssayContext(item)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function GroupedRanking({ ranking }: { ranking: PropertyRankingResponse | null }) {
  if (!ranking || ranking.groups.length === 0) {
    return <EmptyState />;
  }

  return (
    <div className="divide-y divide-slate-200">
      {ranking.groups.map((group) => (
        <section className="px-4 py-4" key={JSON.stringify(group.condition_key)}>
          <h3 className="text-sm font-semibold text-slate-950">{summarizeRankingGroup(group)}</h3>
          <div className="mt-3 overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-200 text-sm">
              <thead className="bg-slate-50 text-left text-xs font-medium uppercase text-slate-500">
                <tr>
                  <th className="px-3 py-2">Rank</th>
                  <th className="px-3 py-2">Enzyme</th>
                  <th className="px-3 py-2">Value</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {group.items.map((item) => (
                  <tr key={item.property_record_id}>
                    <td className="whitespace-nowrap px-3 py-2 font-medium">#{item.rank}</td>
                    <td className="px-3 py-2">
                      <p className="font-medium text-slate-950">{item.enzyme_name}</p>
                      <p className="text-xs text-slate-500">{item.organism ?? "-"}</p>
                    </td>
                    <td className="whitespace-nowrap px-3 py-2 text-slate-700">
                      {formatRankingValue(item)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ))}
    </div>
  );
}

function EmptyState() {
  return (
    <div className="px-4 py-10 text-sm text-slate-500">
      No public ranking data is available for this property yet.
    </div>
  );
}
