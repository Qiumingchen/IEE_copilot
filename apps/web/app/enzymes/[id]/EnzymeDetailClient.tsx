"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import {
  createPropertyRecord,
  createSubstrate,
  getEnzymeRecordBundle
} from "../../../lib/api";
import type { EnzymeRecordBundle } from "../../../lib/types";

const TOKEN_KEY = "iee-copilot-token";

type EnzymeDetailClientProps = {
  enzymeId: string;
};

type PropertyFormState = {
  property_type: string;
  value_original: string;
  unit_original: string;
  substrate: string;
  assay_temperature: string;
  assay_pH: string;
};

function emptyPropertyForm(): PropertyFormState {
  return {
    property_type: "optimal_temperature",
    value_original: "",
    unit_original: "degC",
    substrate: "",
    assay_temperature: "",
    assay_pH: ""
  };
}

function textOrDash(value: string | null | undefined): string {
  return value && value.trim() ? value : "-";
}

export default function EnzymeDetailClient({ enzymeId }: EnzymeDetailClientProps) {
  const router = useRouter();
  const [token, setToken] = useState<string | null>(null);
  const [bundle, setBundle] = useState<EnzymeRecordBundle | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSavingSubstrate, setIsSavingSubstrate] = useState(false);
  const [isSavingProperty, setIsSavingProperty] = useState(false);
  const [substrateName, setSubstrateName] = useState("");
  const [substrateClass, setSubstrateClass] = useState("");
  const [substrateSmiles, setSubstrateSmiles] = useState("");
  const [propertyForm, setPropertyForm] = useState<PropertyFormState>(emptyPropertyForm);

  const substrateOptions = useMemo(() => bundle?.substrates.map((item) => item.name) ?? [], [bundle]);

  async function loadBundle(nextToken: string) {
    setError(null);
    setIsLoading(true);
    try {
      setBundle(await getEnzymeRecordBundle(enzymeId, nextToken));
    } catch {
      setError("Unable to load enzyme records. Please check the API service and your login.");
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

  async function handleCreateSubstrate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || !substrateName.trim()) {
      return;
    }

    setIsSavingSubstrate(true);
    setError(null);
    try {
      await createSubstrate(enzymeId, token, {
        name: substrateName.trim(),
        substrate_class: substrateClass.trim() || undefined,
        smiles: substrateSmiles.trim() || undefined
      });
      setSubstrateName("");
      setSubstrateClass("");
      setSubstrateSmiles("");
      await loadBundle(token);
    } catch {
      setError("Unable to save substrate record.");
    } finally {
      setIsSavingSubstrate(false);
    }
  }

  async function handleCreateProperty(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || !propertyForm.property_type.trim() || !propertyForm.value_original.trim()) {
      return;
    }

    setIsSavingProperty(true);
    setError(null);
    try {
      await createPropertyRecord(enzymeId, token, {
        property_type: propertyForm.property_type.trim(),
        value_original: propertyForm.value_original.trim(),
        unit_original: propertyForm.unit_original.trim() || undefined,
        substrate: propertyForm.substrate.trim() || undefined,
        assay_temperature: propertyForm.assay_temperature.trim() || undefined,
        assay_pH: propertyForm.assay_pH.trim() || undefined
      });
      setPropertyForm(emptyPropertyForm());
      await loadBundle(token);
    } catch {
      setError("Unable to save property record.");
    } finally {
      setIsSavingProperty(false);
    }
  }

  return (
    <main className="mx-auto max-w-6xl px-6 py-8">
      <header className="border-b border-slate-200 pb-6">
        <p className="text-sm font-medium text-slate-500">Enzyme record</p>
        <div className="mt-2 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold text-slate-950">
              {bundle?.enzyme.name ?? "Enzyme detail"}
            </h1>
            <p className="mt-2 text-sm text-slate-600">Entry id: {enzymeId}</p>
          </div>
          <button
            className="rounded-md border border-slate-300 px-3 py-2 text-sm font-medium text-slate-800 disabled:cursor-not-allowed disabled:text-slate-400"
            disabled={!token || isLoading}
            onClick={() => token && void loadBundle(token)}
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

      {isLoading ? (
        <p className="mt-6 text-sm text-slate-600">Loading enzyme records...</p>
      ) : null}

      {bundle ? (
        <>
          <section className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <div className="rounded-md border border-slate-200 bg-white p-4">
              <dt className="text-xs font-medium uppercase text-slate-500">Organism</dt>
              <dd className="mt-1 text-sm text-slate-950">{textOrDash(bundle.enzyme.organism)}</dd>
            </div>
            <div className="rounded-md border border-slate-200 bg-white p-4">
              <dt className="text-xs font-medium uppercase text-slate-500">EC number</dt>
              <dd className="mt-1 text-sm text-slate-950">{textOrDash(bundle.enzyme.ec_number)}</dd>
            </div>
            <div className="rounded-md border border-slate-200 bg-white p-4">
              <dt className="text-xs font-medium uppercase text-slate-500">UniProt</dt>
              <dd className="mt-1 text-sm text-slate-950">{textOrDash(bundle.enzyme.uniprot_id)}</dd>
            </div>
            <div className="rounded-md border border-slate-200 bg-white p-4">
              <dt className="text-xs font-medium uppercase text-slate-500">Source</dt>
              <dd className="mt-1 text-sm text-slate-950">{bundle.enzyme.source}</dd>
            </div>
          </section>

          <section className="mt-8 grid gap-6 lg:grid-cols-2">
            <form className="rounded-md border border-slate-200 bg-white p-5" onSubmit={handleCreateSubstrate}>
              <h2 className="text-base font-semibold text-slate-950">Substrate</h2>
              <div className="mt-4 grid gap-3">
                <label className="grid gap-1 text-sm font-medium text-slate-700">
                  Name
                  <input
                    className="rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-950 outline-none focus:border-slate-500"
                    value={substrateName}
                    onChange={(event) => setSubstrateName(event.target.value)}
                  />
                </label>
                <label className="grid gap-1 text-sm font-medium text-slate-700">
                  Class
                  <input
                    className="rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-950 outline-none focus:border-slate-500"
                    value={substrateClass}
                    onChange={(event) => setSubstrateClass(event.target.value)}
                  />
                </label>
                <label className="grid gap-1 text-sm font-medium text-slate-700">
                  SMILES
                  <input
                    className="rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-950 outline-none focus:border-slate-500"
                    value={substrateSmiles}
                    onChange={(event) => setSubstrateSmiles(event.target.value)}
                  />
                </label>
              </div>
              <button
                className="mt-4 rounded-md bg-slate-950 px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:bg-slate-400"
                disabled={isSavingSubstrate || !substrateName.trim()}
                type="submit"
              >
                {isSavingSubstrate ? "Saving..." : "Save substrate"}
              </button>
            </form>

            <form className="rounded-md border border-slate-200 bg-white p-5" onSubmit={handleCreateProperty}>
              <h2 className="text-base font-semibold text-slate-950">Property</h2>
              <div className="mt-4 grid gap-3 sm:grid-cols-2">
                <label className="grid gap-1 text-sm font-medium text-slate-700">
                  Type
                  <select
                    className="rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-950 outline-none focus:border-slate-500"
                    value={propertyForm.property_type}
                    onChange={(event) =>
                      setPropertyForm((current) => ({ ...current, property_type: event.target.value }))
                    }
                  >
                    <option value="optimal_temperature">optimal_temperature</option>
                    <option value="optimal_pH">optimal_pH</option>
                    <option value="specific_activity">specific_activity</option>
                    <option value="thermostability">thermostability</option>
                  </select>
                </label>
                <label className="grid gap-1 text-sm font-medium text-slate-700">
                  Value
                  <input
                    className="rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-950 outline-none focus:border-slate-500"
                    value={propertyForm.value_original}
                    onChange={(event) =>
                      setPropertyForm((current) => ({ ...current, value_original: event.target.value }))
                    }
                  />
                </label>
                <label className="grid gap-1 text-sm font-medium text-slate-700">
                  Unit
                  <input
                    className="rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-950 outline-none focus:border-slate-500"
                    value={propertyForm.unit_original}
                    onChange={(event) =>
                      setPropertyForm((current) => ({ ...current, unit_original: event.target.value }))
                    }
                  />
                </label>
                <label className="grid gap-1 text-sm font-medium text-slate-700">
                  Substrate
                  <input
                    className="rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-950 outline-none focus:border-slate-500"
                    list="substrate-options"
                    value={propertyForm.substrate}
                    onChange={(event) =>
                      setPropertyForm((current) => ({ ...current, substrate: event.target.value }))
                    }
                  />
                  <datalist id="substrate-options">
                    {substrateOptions.map((name) => (
                      <option key={name} value={name} />
                    ))}
                  </datalist>
                </label>
                <label className="grid gap-1 text-sm font-medium text-slate-700">
                  Assay temp
                  <input
                    className="rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-950 outline-none focus:border-slate-500"
                    value={propertyForm.assay_temperature}
                    onChange={(event) =>
                      setPropertyForm((current) => ({ ...current, assay_temperature: event.target.value }))
                    }
                  />
                </label>
                <label className="grid gap-1 text-sm font-medium text-slate-700">
                  Assay pH
                  <input
                    className="rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-950 outline-none focus:border-slate-500"
                    value={propertyForm.assay_pH}
                    onChange={(event) =>
                      setPropertyForm((current) => ({ ...current, assay_pH: event.target.value }))
                    }
                  />
                </label>
              </div>
              <button
                className="mt-4 rounded-md bg-slate-950 px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:bg-slate-400"
                disabled={isSavingProperty || !propertyForm.value_original.trim()}
                type="submit"
              >
                {isSavingProperty ? "Saving..." : "Save property"}
              </button>
            </form>
          </section>

          <section className="mt-8 grid gap-6">
            <RecordTable
              columns={["Name", "Class", "SMILES"]}
              rows={bundle.substrates.map((item) => [
                item.name,
                textOrDash(item.substrate_class),
                textOrDash(item.smiles)
              ])}
              title="Substrates"
            />
            <RecordTable
              columns={["Type", "State", "Source", "Ligands"]}
              rows={bundle.structures.map((item) => [
                item.structure_type,
                item.complex_state,
                item.source,
                item.ligands.map((ligand) => ligand.ligand_code ?? ligand.ligand_name).join(", ") || "-"
              ])}
              title="Structures"
            />
            <RecordTable
              columns={["Type", "Value", "Unit", "Substrate", "Assay"]}
              rows={bundle.properties.map((item) => [
                item.property_type,
                item.value_original,
                textOrDash(item.unit_original),
                textOrDash(item.substrate),
                [item.assay_temperature, item.assay_pH].filter(Boolean).join(" / ") || "-"
              ])}
              title="Properties"
            />
            <RecordTable
              columns={["Substrate", "Km", "kcat", "kcat/Km", "Assay"]}
              rows={bundle.kinetics.map((item) => [
                textOrDash(item.substrate),
                textOrDash(item.km),
                textOrDash(item.kcat),
                textOrDash(item.kcat_km),
                [item.assay_temperature, item.assay_pH].filter(Boolean).join(" / ") || "-"
              ])}
              title="Kinetics"
            />
            <RecordTable
              columns={["Host", "Vector", "Level", "Soluble", "Condition"]}
              rows={bundle.expression.map((item) => [
                textOrDash(item.expression_host),
                textOrDash(item.vector),
                textOrDash(item.expression_level_original),
                textOrDash(item.soluble_expression),
                item.condition
                  ? [item.condition.assay_temperature, item.condition.assay_pH, item.condition.method]
                      .filter(Boolean)
                      .join(" / ")
                  : "-"
              ])}
              title="Expression"
            />
          </section>
        </>
      ) : null}
    </main>
  );
}

function RecordTable({
  columns,
  rows,
  title
}: {
  columns: string[];
  rows: string[][];
  title: string;
}) {
  return (
    <section className="overflow-hidden rounded-md border border-slate-200 bg-white">
      <div className="border-b border-slate-200 px-4 py-3">
        <h2 className="text-base font-semibold text-slate-950">{title}</h2>
      </div>
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-slate-200 text-left text-sm">
          <thead className="bg-slate-50 text-xs uppercase text-slate-500">
            <tr>
              {columns.map((column) => (
                <th className="whitespace-nowrap px-4 py-3 font-medium" key={column} scope="col">
                  {column}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 text-slate-700">
            {rows.length > 0 ? (
              rows.map((row, rowIndex) => (
                <tr key={`${title}-${rowIndex}`}>
                  {row.map((cell, cellIndex) => (
                    <td className="max-w-xs px-4 py-3 align-top" key={`${title}-${rowIndex}-${cellIndex}`}>
                      <span className="break-words">{cell}</span>
                    </td>
                  ))}
                </tr>
              ))
            ) : (
              <tr>
                <td className="px-4 py-4 text-slate-500" colSpan={columns.length}>
                  No records
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
