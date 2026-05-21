"use client";

import type { ReactNode } from "react";
import { ChangeEvent, FormEvent, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import {
  createExpressionRecord,
  createKineticRecord,
  createPropertyRecord,
  createStructureRecord,
  createSubstrate,
  getEnzymeRecordBundle,
  listEnzymeReferences,
  uploadStructureFile
} from "../../../lib/api";
import { formatProvenanceLabel, provenanceFromRecord, provenanceWarning } from "../../../lib/provenance";
import type { EnzymeRecordBundle, LiteratureReferenceRecord, StructureRecord } from "../../../lib/types";
import { formatReferenceForTable, formatVisibilityStatus } from "./enzyme-detail-utils";
import { ReferenceCitation } from "./ReferenceCitation";

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

type StructureFormState = {
  structure_type: string;
  complex_state: string;
  pdb_id: string;
  ligand_name: string;
  ligand_code: string;
  ligand_type: string;
};

type KineticFormState = {
  substrate: string;
  km: string;
  kcat: string;
  kcat_km: string;
  unit_original: string;
  assay_temperature: string;
  assay_pH: string;
};

type ExpressionFormState = {
  expression_host: string;
  vector: string;
  expression_level_original: string;
  soluble_expression: string;
  unit_original: string;
  substrate_entry_id: string;
  assay_temperature: string;
  assay_pH: string;
  method: string;
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

function emptyStructureForm(): StructureFormState {
  return {
    structure_type: "uploaded_pdb",
    complex_state: "apo",
    pdb_id: "",
    ligand_name: "",
    ligand_code: "",
    ligand_type: "substrate"
  };
}

function emptyKineticForm(): KineticFormState {
  return {
    substrate: "",
    km: "",
    kcat: "",
    kcat_km: "",
    unit_original: "",
    assay_temperature: "",
    assay_pH: ""
  };
}

function emptyExpressionForm(): ExpressionFormState {
  return {
    expression_host: "",
    vector: "",
    expression_level_original: "",
    soluble_expression: "",
    unit_original: "",
    substrate_entry_id: "",
    assay_temperature: "",
    assay_pH: "",
    method: ""
  };
}

function textOrDash(value: string | null | undefined): string {
  return value && value.trim() ? value : "-";
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function summarizeStructureChains(structure: StructureRecord): string {
  const chains = structure.chain_summary?.chains;
  if (!Array.isArray(chains) || chains.length === 0) {
    return "-";
  }
  return chains
    .map((chain) => {
      if (!isRecord(chain)) {
        return null;
      }
      const chainId = "chain_id" in chain ? String(chain.chain_id) : "-";
      const residueCount = "residue_count" in chain ? String(chain.residue_count) : "?";
      const sequence = "sequence" in chain ? String(chain.sequence) : "";
      return `${chainId}: ${residueCount} aa${sequence ? ` (${sequence})` : ""}`;
    })
    .filter(Boolean)
    .join(" / ");
}

function summarizeStructureLigands(structure: StructureRecord): string {
  const summaryLigands = structure.ligand_summary?.ligands;
  if (Array.isArray(summaryLigands) && summaryLigands.length > 0) {
    return summaryLigands
      .map((ligand) => {
        if (!isRecord(ligand)) {
          return null;
        }
        const ligandCode = "ligand_code" in ligand ? String(ligand.ligand_code) : "ligand";
        const nearestSummary = summarizeNearestResidues(ligand);
        return nearestSummary ? `${ligandCode} (${nearestSummary})` : ligandCode;
      })
      .filter(Boolean)
      .join(", ");
  }
  const ligands = structure.ligands
    .map((ligand) => ligand.ligand_code ?? ligand.ligand_name)
    .filter(Boolean);
  if (ligands.length === 0) {
    return "-";
  }
  return ligands.join(", ");
}

function summarizeStructureProvenance(structure: StructureRecord): string {
  const provenance = provenanceFromRecord(structure as unknown as Record<string, unknown>, "chain_summary");
  const warning = provenanceWarning(provenance);
  return warning ? `${formatProvenanceLabel(provenance)} / ${warning}` : formatProvenanceLabel(provenance);
}

function summarizeNearestResidues(ligand: Record<string, unknown>): string {
  const nearestResidues = ligand.nearest_residues;
  if (!isRecord(nearestResidues)) {
    return "";
  }

  return ["4A", "6A", "8A"]
    .map((cutoff) => {
      const residues = nearestResidues[cutoff];
      if (!Array.isArray(residues) || residues.length === 0) {
        return null;
      }
      const residueText = residues.slice(0, 3).map(formatNearestResidue).filter(Boolean).join(", ");
      const suffix = residues.length > 3 ? ` +${residues.length - 3}` : "";
      return residueText ? `${cutoff}: ${residueText}${suffix}` : null;
    })
    .filter(Boolean)
    .join("; ");
}

function formatNearestResidue(residue: unknown): string | null {
  if (!isRecord(residue)) {
    return null;
  }
  const chainId = "chain_id" in residue ? String(residue.chain_id) : "-";
  const residueNumber = "residue_number" in residue ? String(residue.residue_number) : "?";
  const oneLetter = "one_letter" in residue ? String(residue.one_letter) : "";
  const distance = "min_distance_angstrom" in residue ? Number(residue.min_distance_angstrom) : NaN;
  const distanceText = Number.isFinite(distance) ? ` ${distance.toFixed(1)}A` : "";
  return `${chainId}${residueNumber}${oneLetter ? ` ${oneLetter}` : ""}${distanceText}`;
}

export default function EnzymeDetailClient({ enzymeId }: EnzymeDetailClientProps) {
  const router = useRouter();
  const [token, setToken] = useState<string | null>(null);
  const [bundle, setBundle] = useState<EnzymeRecordBundle | null>(null);
  const [referencesById, setReferencesById] = useState<Record<string, LiteratureReferenceRecord>>({});
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSavingSubstrate, setIsSavingSubstrate] = useState(false);
  const [isSavingProperty, setIsSavingProperty] = useState(false);
  const [isSavingStructure, setIsSavingStructure] = useState(false);
  const [isUploadingStructure, setIsUploadingStructure] = useState(false);
  const [isSavingKinetic, setIsSavingKinetic] = useState(false);
  const [isSavingExpression, setIsSavingExpression] = useState(false);
  const [substrateName, setSubstrateName] = useState("");
  const [substrateClass, setSubstrateClass] = useState("");
  const [substrateSmiles, setSubstrateSmiles] = useState("");
  const [propertyForm, setPropertyForm] = useState<PropertyFormState>(emptyPropertyForm);
  const [structureForm, setStructureForm] = useState<StructureFormState>(emptyStructureForm);
  const [structureFile, setStructureFile] = useState<File | null>(null);
  const [kineticForm, setKineticForm] = useState<KineticFormState>(emptyKineticForm);
  const [expressionForm, setExpressionForm] = useState<ExpressionFormState>(emptyExpressionForm);

  const substrateOptions = useMemo(() => bundle?.substrates.map((item) => item.name) ?? [], [bundle]);
  const substrateIdOptions = useMemo(
    () => bundle?.substrates.map((item) => ({ id: item.id, name: item.name })) ?? [],
    [bundle]
  );

  async function loadBundle(nextToken: string) {
    setError(null);
    setIsLoading(true);
    try {
      const [nextBundle, references] = await Promise.all([
        getEnzymeRecordBundle(enzymeId, nextToken),
        listEnzymeReferences(enzymeId, nextToken)
      ]);
      setBundle(nextBundle);
      setReferencesById(Object.fromEntries(references.map((reference) => [reference.id, reference])));
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

  async function handleCreateStructure(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || !structureForm.structure_type.trim()) {
      return;
    }

    setIsSavingStructure(true);
    setError(null);
    try {
      await createStructureRecord(enzymeId, token, {
        structure_type: structureForm.structure_type.trim(),
        complex_state: structureForm.complex_state.trim() || undefined,
        pdb_id: structureForm.pdb_id.trim() || undefined,
        source: "user_upload",
        ligands: structureForm.ligand_name.trim()
          ? [
              {
                ligand_name: structureForm.ligand_name.trim(),
                ligand_code: structureForm.ligand_code.trim() || undefined,
                ligand_type: structureForm.ligand_type.trim() || undefined
              }
            ]
          : []
      });
      setStructureForm(emptyStructureForm());
      await loadBundle(token);
    } catch {
      setError("Unable to save structure record.");
    } finally {
      setIsSavingStructure(false);
    }
  }

  function handleStructureFileChange(event: ChangeEvent<HTMLInputElement>) {
    setStructureFile(event.target.files?.[0] ?? null);
    setError(null);
  }

  async function handleUploadStructureFile() {
    if (!token || !structureFile) {
      return;
    }

    setIsUploadingStructure(true);
    setError(null);
    try {
      await uploadStructureFile(enzymeId, token, structureFile);
      setStructureFile(null);
      await loadBundle(token);
    } catch {
      setError("Unable to upload or parse structure file.");
    } finally {
      setIsUploadingStructure(false);
    }
  }

  async function handleCreateKinetic(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || (!kineticForm.km.trim() && !kineticForm.kcat.trim() && !kineticForm.kcat_km.trim())) {
      return;
    }

    setIsSavingKinetic(true);
    setError(null);
    try {
      await createKineticRecord(enzymeId, token, {
        substrate: kineticForm.substrate.trim() || undefined,
        km: kineticForm.km.trim() || undefined,
        kcat: kineticForm.kcat.trim() || undefined,
        kcat_km: kineticForm.kcat_km.trim() || undefined,
        unit_original: kineticForm.unit_original.trim() || undefined,
        assay_temperature: kineticForm.assay_temperature.trim() || undefined,
        assay_pH: kineticForm.assay_pH.trim() || undefined
      });
      setKineticForm(emptyKineticForm());
      await loadBundle(token);
    } catch {
      setError("Unable to save kinetic record.");
    } finally {
      setIsSavingKinetic(false);
    }
  }

  async function handleCreateExpression(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || !expressionForm.expression_host.trim()) {
      return;
    }

    setIsSavingExpression(true);
    setError(null);
    try {
      await createExpressionRecord(enzymeId, token, {
        expression_host: expressionForm.expression_host.trim(),
        vector: expressionForm.vector.trim() || undefined,
        expression_level_original: expressionForm.expression_level_original.trim() || undefined,
        soluble_expression: expressionForm.soluble_expression.trim() || undefined,
        unit_original: expressionForm.unit_original.trim() || undefined,
        unit_standardized: expressionForm.unit_original.trim() || undefined,
        condition:
          expressionForm.substrate_entry_id ||
          expressionForm.assay_temperature ||
          expressionForm.assay_pH ||
          expressionForm.method
            ? {
                substrate_entry_id: expressionForm.substrate_entry_id || undefined,
                assay_temperature: expressionForm.assay_temperature.trim() || undefined,
                assay_pH: expressionForm.assay_pH.trim() || undefined,
                method: expressionForm.method.trim() || undefined
              }
            : undefined
      });
      setExpressionForm(emptyExpressionForm());
      await loadBundle(token);
    } catch {
      setError("Unable to save expression record.");
    } finally {
      setIsSavingExpression(false);
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
          <div className="flex flex-wrap gap-2">
            <Link
              className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-800"
              href={`/enzymes/${enzymeId}/structures`}
            >
              Structure analysis
            </Link>
            <button
              className="rounded-md border border-slate-300 px-3 py-2 text-sm font-medium text-slate-800 disabled:cursor-not-allowed disabled:text-slate-400"
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

          <section className="mt-6 grid gap-6 xl:grid-cols-3">
            <form className="rounded-md border border-slate-200 bg-white p-5" onSubmit={handleCreateStructure}>
              <h2 className="text-base font-semibold text-slate-950">Structure</h2>
              <div className="mt-4 grid gap-3">
                <label className="grid gap-1 text-sm font-medium text-slate-700">
                  PDB or CIF file
                  <input
                    accept=".pdb,.cif,chemical/x-pdb,chemical/x-mmcif"
                    className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-950 file:mr-3 file:rounded-md file:border-0 file:bg-slate-100 file:px-3 file:py-1 file:text-sm file:font-medium file:text-slate-800"
                    type="file"
                    onChange={handleStructureFileChange}
                  />
                </label>
                <button
                  className="rounded-md border border-slate-300 px-4 py-2 text-sm font-medium text-slate-800 disabled:cursor-not-allowed disabled:text-slate-400"
                  disabled={isUploadingStructure || !structureFile}
                  onClick={() => void handleUploadStructureFile()}
                  type="button"
                >
                  {isUploadingStructure ? "Uploading..." : "Upload and parse"}
                </button>
                <label className="grid gap-1 text-sm font-medium text-slate-700">
                  Type
                  <select
                    className="rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-950 outline-none focus:border-slate-500"
                    value={structureForm.structure_type}
                    onChange={(event) =>
                      setStructureForm((current) => ({ ...current, structure_type: event.target.value }))
                    }
                  >
                    <option value="uploaded_pdb">uploaded_pdb</option>
                    <option value="pdb">pdb</option>
                    <option value="alphafold">alphafold</option>
                    <option value="predicted">predicted</option>
                  </select>
                </label>
                <label className="grid gap-1 text-sm font-medium text-slate-700">
                  State
                  <select
                    className="rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-950 outline-none focus:border-slate-500"
                    value={structureForm.complex_state}
                    onChange={(event) =>
                      setStructureForm((current) => ({ ...current, complex_state: event.target.value }))
                    }
                  >
                    <option value="apo">apo</option>
                    <option value="enzyme_substrate_complex">enzyme_substrate_complex</option>
                    <option value="unknown">unknown</option>
                  </select>
                </label>
                <label className="grid gap-1 text-sm font-medium text-slate-700">
                  PDB ID
                  <input
                    className="rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-950 outline-none focus:border-slate-500"
                    value={structureForm.pdb_id}
                    onChange={(event) =>
                      setStructureForm((current) => ({ ...current, pdb_id: event.target.value }))
                    }
                  />
                </label>
                <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-1">
                  <label className="grid gap-1 text-sm font-medium text-slate-700">
                    Ligand name
                    <input
                      className="rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-950 outline-none focus:border-slate-500"
                      value={structureForm.ligand_name}
                      onChange={(event) =>
                        setStructureForm((current) => ({ ...current, ligand_name: event.target.value }))
                      }
                    />
                  </label>
                  <label className="grid gap-1 text-sm font-medium text-slate-700">
                    Ligand code
                    <input
                      className="rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-950 outline-none focus:border-slate-500"
                      value={structureForm.ligand_code}
                      onChange={(event) =>
                        setStructureForm((current) => ({ ...current, ligand_code: event.target.value }))
                      }
                    />
                  </label>
                </div>
              </div>
              <button
                className="mt-4 rounded-md bg-slate-950 px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:bg-slate-400"
                disabled={isSavingStructure || !structureForm.structure_type.trim()}
                type="submit"
              >
                {isSavingStructure ? "Saving..." : "Save structure"}
              </button>
            </form>

            <form className="rounded-md border border-slate-200 bg-white p-5" onSubmit={handleCreateKinetic}>
              <h2 className="text-base font-semibold text-slate-950">Kinetic</h2>
              <div className="mt-4 grid gap-3">
                <label className="grid gap-1 text-sm font-medium text-slate-700">
                  Substrate
                  <input
                    className="rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-950 outline-none focus:border-slate-500"
                    list="substrate-options"
                    value={kineticForm.substrate}
                    onChange={(event) =>
                      setKineticForm((current) => ({ ...current, substrate: event.target.value }))
                    }
                  />
                </label>
                <div className="grid gap-3 sm:grid-cols-3 xl:grid-cols-1">
                  <label className="grid gap-1 text-sm font-medium text-slate-700">
                    Km
                    <input
                      className="rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-950 outline-none focus:border-slate-500"
                      value={kineticForm.km}
                      onChange={(event) =>
                        setKineticForm((current) => ({ ...current, km: event.target.value }))
                      }
                    />
                  </label>
                  <label className="grid gap-1 text-sm font-medium text-slate-700">
                    kcat
                    <input
                      className="rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-950 outline-none focus:border-slate-500"
                      value={kineticForm.kcat}
                      onChange={(event) =>
                        setKineticForm((current) => ({ ...current, kcat: event.target.value }))
                      }
                    />
                  </label>
                  <label className="grid gap-1 text-sm font-medium text-slate-700">
                    kcat/Km
                    <input
                      className="rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-950 outline-none focus:border-slate-500"
                      value={kineticForm.kcat_km}
                      onChange={(event) =>
                        setKineticForm((current) => ({ ...current, kcat_km: event.target.value }))
                      }
                    />
                  </label>
                </div>
                <div className="grid gap-3 sm:grid-cols-3 xl:grid-cols-1">
                  <label className="grid gap-1 text-sm font-medium text-slate-700">
                    Unit
                    <input
                      className="rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-950 outline-none focus:border-slate-500"
                      value={kineticForm.unit_original}
                      onChange={(event) =>
                        setKineticForm((current) => ({ ...current, unit_original: event.target.value }))
                      }
                    />
                  </label>
                  <label className="grid gap-1 text-sm font-medium text-slate-700">
                    Temp
                    <input
                      className="rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-950 outline-none focus:border-slate-500"
                      value={kineticForm.assay_temperature}
                      onChange={(event) =>
                        setKineticForm((current) => ({ ...current, assay_temperature: event.target.value }))
                      }
                    />
                  </label>
                  <label className="grid gap-1 text-sm font-medium text-slate-700">
                    pH
                    <input
                      className="rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-950 outline-none focus:border-slate-500"
                      value={kineticForm.assay_pH}
                      onChange={(event) =>
                        setKineticForm((current) => ({ ...current, assay_pH: event.target.value }))
                      }
                    />
                  </label>
                </div>
              </div>
              <button
                className="mt-4 rounded-md bg-slate-950 px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:bg-slate-400"
                disabled={
                  isSavingKinetic ||
                  (!kineticForm.km.trim() && !kineticForm.kcat.trim() && !kineticForm.kcat_km.trim())
                }
                type="submit"
              >
                {isSavingKinetic ? "Saving..." : "Save kinetic"}
              </button>
            </form>

            <form className="rounded-md border border-slate-200 bg-white p-5" onSubmit={handleCreateExpression}>
              <h2 className="text-base font-semibold text-slate-950">Expression</h2>
              <div className="mt-4 grid gap-3">
                <label className="grid gap-1 text-sm font-medium text-slate-700">
                  Host
                  <input
                    className="rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-950 outline-none focus:border-slate-500"
                    value={expressionForm.expression_host}
                    onChange={(event) =>
                      setExpressionForm((current) => ({ ...current, expression_host: event.target.value }))
                    }
                  />
                </label>
                <label className="grid gap-1 text-sm font-medium text-slate-700">
                  Vector
                  <input
                    className="rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-950 outline-none focus:border-slate-500"
                    value={expressionForm.vector}
                    onChange={(event) =>
                      setExpressionForm((current) => ({ ...current, vector: event.target.value }))
                    }
                  />
                </label>
                <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-1">
                  <label className="grid gap-1 text-sm font-medium text-slate-700">
                    Level
                    <input
                      className="rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-950 outline-none focus:border-slate-500"
                      value={expressionForm.expression_level_original}
                      onChange={(event) =>
                        setExpressionForm((current) => ({
                          ...current,
                          expression_level_original: event.target.value
                        }))
                      }
                    />
                  </label>
                  <label className="grid gap-1 text-sm font-medium text-slate-700">
                    Unit
                    <input
                      className="rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-950 outline-none focus:border-slate-500"
                      value={expressionForm.unit_original}
                      onChange={(event) =>
                        setExpressionForm((current) => ({ ...current, unit_original: event.target.value }))
                      }
                    />
                  </label>
                </div>
                <label className="grid gap-1 text-sm font-medium text-slate-700">
                  Soluble
                  <select
                    className="rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-950 outline-none focus:border-slate-500"
                    value={expressionForm.soluble_expression}
                    onChange={(event) =>
                      setExpressionForm((current) => ({ ...current, soluble_expression: event.target.value }))
                    }
                  >
                    <option value="">-</option>
                    <option value="high">high</option>
                    <option value="medium">medium</option>
                    <option value="low">low</option>
                    <option value="insoluble">insoluble</option>
                  </select>
                </label>
                <label className="grid gap-1 text-sm font-medium text-slate-700">
                  Condition substrate
                  <select
                    className="rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-950 outline-none focus:border-slate-500"
                    value={expressionForm.substrate_entry_id}
                    onChange={(event) =>
                      setExpressionForm((current) => ({ ...current, substrate_entry_id: event.target.value }))
                    }
                  >
                    <option value="">-</option>
                    {substrateIdOptions.map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.name}
                      </option>
                    ))}
                  </select>
                </label>
                <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-1">
                  <label className="grid gap-1 text-sm font-medium text-slate-700">
                    Temp
                    <input
                      className="rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-950 outline-none focus:border-slate-500"
                      value={expressionForm.assay_temperature}
                      onChange={(event) =>
                        setExpressionForm((current) => ({ ...current, assay_temperature: event.target.value }))
                      }
                    />
                  </label>
                  <label className="grid gap-1 text-sm font-medium text-slate-700">
                    pH
                    <input
                      className="rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-950 outline-none focus:border-slate-500"
                      value={expressionForm.assay_pH}
                      onChange={(event) =>
                        setExpressionForm((current) => ({ ...current, assay_pH: event.target.value }))
                      }
                    />
                  </label>
                </div>
                <label className="grid gap-1 text-sm font-medium text-slate-700">
                  Method
                  <input
                    className="rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-950 outline-none focus:border-slate-500"
                    value={expressionForm.method}
                    onChange={(event) =>
                      setExpressionForm((current) => ({ ...current, method: event.target.value }))
                    }
                  />
                </label>
              </div>
              <button
                className="mt-4 rounded-md bg-slate-950 px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:bg-slate-400"
                disabled={isSavingExpression || !expressionForm.expression_host.trim()}
                type="submit"
              >
                {isSavingExpression ? "Saving..." : "Save expression"}
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
              columns={["Type", "State", "Chains", "Ligands", "Provenance", "Artifact"]}
              rows={bundle.structures.map((item) => [
                item.structure_type,
                item.complex_state,
                summarizeStructureChains(item),
                summarizeStructureLigands(item),
                summarizeStructureProvenance(item),
                item.artifact?.object_key ?? "-"
              ])}
              title="Structures"
            />
            <RecordTable
              columns={["Type", "Value", "Unit", "Substrate", "Assay", "Reference", "Evidence", "Status"]}
              rows={bundle.properties.map((item) => [
                item.property_type,
                item.value_original,
                textOrDash(item.unit_original),
                textOrDash(item.substrate),
                [item.assay_temperature, item.assay_pH].filter(Boolean).join(" / ") || "-",
                <ReferenceCitation
                  fallback={formatReferenceForTable(item.reference_id, referencesById)}
                  reference={item.reference ?? referencesById[item.reference_id ?? ""]}
                />,
                textOrDash(item.evidence_text),
                formatVisibilityStatus(item.visibility, item.curation_status)
              ])}
              title="Properties"
            />
            <RecordTable
              columns={["Substrate", "Km", "kcat", "kcat/Km", "Assay", "Reference", "Status"]}
              rows={bundle.kinetics.map((item) => [
                textOrDash(item.substrate),
                textOrDash(item.km),
                textOrDash(item.kcat),
                textOrDash(item.kcat_km),
                [item.assay_temperature, item.assay_pH].filter(Boolean).join(" / ") || "-",
                <ReferenceCitation
                  fallback={formatReferenceForTable(item.reference_id, referencesById)}
                  reference={item.reference ?? referencesById[item.reference_id ?? ""]}
                />,
                formatVisibilityStatus(item.visibility, item.curation_status)
              ])}
              title="Kinetics"
            />
            <RecordTable
              columns={["Host", "Vector", "Level", "Soluble", "Condition", "Reference", "Status"]}
              rows={bundle.expression.map((item) => [
                textOrDash(item.expression_host),
                textOrDash(item.vector),
                textOrDash(item.expression_level_original),
                textOrDash(item.soluble_expression),
                item.condition
                  ? [item.condition.assay_temperature, item.condition.assay_pH, item.condition.method]
                      .filter(Boolean)
                      .join(" / ")
                  : "-",
                formatReferenceForTable(item.reference_id ?? item.condition?.reference_id, referencesById),
                formatVisibilityStatus(item.visibility, item.curation_status)
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
  rows: ReactNode[][];
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
