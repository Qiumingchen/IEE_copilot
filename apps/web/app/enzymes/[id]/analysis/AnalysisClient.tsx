"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import {
  createAnalysisJob,
  getAnalysisArtifactContent,
  getAnalysisArtifacts,
  listStructures,
  listJobs,
  retryJob
} from "../../../../lib/api";
import type {
  AnalysisArtifactContentRecord,
  AnalysisArtifactRecord,
  AnalysisJobType,
  StructureRecord
} from "../../../../lib/types";
import {
  buildConservationJobParameters,
  buildHomologCsv,
  buildHomologFasta,
  buildMsaJobParameters,
  buildMsaDownloadFasta,
  buildMutationRecommendationJobParameters,
  buildRosettaDdgJobParameters,
  buildLibraryDesignParameters,
  buildMutationLibraryWorkbookBytes,
  buildConservationDownloadJson,
  buildAnalysisArtifactLineageJson,
  buildAnalysisRunManifestJson,
  formatAnalysisArtifactSource,
  filterConservationSites,
  getArtifactRunnerLabel,
  getAnalysisArtifactStructureId,
  getConservationArtifactOptions,
  getConservationSites,
  getHomologArtifactOptions,
  getHomologDiagnostics,
  getHomologSequences,
  getMsaArtifactOptions,
  getMsaRecords,
  getMutationLibrary,
  getMutationRecommendationCandidates,
  getRecommendationArtifactOptions,
  getRosettaDdgResults,
  getRosettaDdgRunViews,
  getStructureContextOptions
} from "./analysis-utils";
import type {
  ConservationCategoryFilter,
  ConservationSiteView,
  ConservationInputMode,
  ArtifactRunnerLabel,
  HomologDiagnosticsView,
  HomologSequenceView,
  MsaInputMode,
  MsaRecordView,
  MutationLibraryInputMode,
  MutationRecommendationInputMode,
  MutationLibraryView,
  MutationRecommendationCandidateView,
  ScoredMutationSuggestionView,
  RosettaDdgRunView,
  AnalysisFocus
} from "./analysis-utils";

const TOKEN_KEY = "iee-copilot-token";
const homologCountOptions = [10, 25, 50, 100];
const homologSearchModeOptions = [
  { value: "metadata_search", label: "Fast UniProt metadata" },
  { value: "sequence_similarity", label: "Sequence similarity" }
];

type AnalysisClientProps = {
  enzymeId: string;
  initialFocus?: AnalysisFocus | null;
  initialStructureId?: string;
};

const analysisModules = [
  {
    title: "Homolog sequences",
    artifactType: "homolog_sequences",
    jobType: "homolog_collection",
    metric: "identity / coverage",
    actionLabel: "Run homologs"
  },
  {
    title: "MSA",
    artifactType: "msa",
    jobType: "msa",
    metric: "aligned FASTA",
    actionLabel: "Run MSA"
  },
  {
    title: "Conservation",
    artifactType: "conservation_profile",
    jobType: "conservation_profile",
    metric: "entropy / WT frequency",
    actionLabel: "Run conservation"
  },
  {
    title: "Hotspot recommendations",
    artifactType: "mutation_recommendations",
    jobType: "mutation_recommendation",
    metric: "priority score / mutations",
    actionLabel: "Run recommendations"
  }
] satisfies Array<{
  title: string;
  artifactType: string;
  jobType: AnalysisJobType;
  metric: string;
  actionLabel: string;
}>;

export default function AnalysisClient({ enzymeId, initialFocus = null, initialStructureId = "" }: AnalysisClientProps) {
  const router = useRouter();
  const [token, setToken] = useState<string | null>(null);
  const [artifacts, setArtifacts] = useState<AnalysisArtifactRecord[]>([]);
  const [structures, setStructures] = useState<StructureRecord[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [runningJobType, setRunningJobType] = useState<AnalysisJobType | null>(null);
  const [selectedContent, setSelectedContent] = useState<AnalysisArtifactContentRecord | null>(null);
  const [latestConservationContent, setLatestConservationContent] =
    useState<AnalysisArtifactContentRecord | null>(null);
  const [latestHomologContent, setLatestHomologContent] =
    useState<AnalysisArtifactContentRecord | null>(null);
  const [homologSequences, setHomologSequences] = useState<HomologSequenceView[]>([]);
  const [homologObjectKey, setHomologObjectKey] = useState<string | null>(null);
  const [homologSearchMode, setHomologSearchMode] = useState("metadata_search");
  const [maxHomologSequences, setMaxHomologSequences] = useState(25);
  const [msaInputMode, setMsaInputMode] = useState<MsaInputMode>("latest");
  const [selectedHomologArtifactId, setSelectedHomologArtifactId] = useState("");
  const [customMsaFasta, setCustomMsaFasta] = useState("");
  const [conservationInputMode, setConservationInputMode] = useState<ConservationInputMode>("latest");
  const [selectedMsaArtifactId, setSelectedMsaArtifactId] = useState("");
  const [recommendationInputMode, setRecommendationInputMode] =
    useState<MutationRecommendationInputMode>("latest");
  const [selectedConservationArtifactId, setSelectedConservationArtifactId] = useState("");
  const [conservationSites, setConservationSites] = useState<ConservationSiteView[]>([]);
  const [conservationFilter, setConservationFilter] = useState<ConservationCategoryFilter>("all");
  const [conservationObjectKey, setConservationObjectKey] = useState<string | null>(null);
  const [recommendationCandidates, setRecommendationCandidates] = useState<MutationRecommendationCandidateView[]>([]);
  const [recommendationObjectKey, setRecommendationObjectKey] = useState<string | null>(null);
  const [rosettaRuns, setRosettaRuns] = useState<RosettaDdgRunView[]>([]);
  const [rosettaObjectKey, setRosettaObjectKey] = useState<string | null>(null);
  const [mutationLibrary, setMutationLibrary] = useState<MutationLibraryView | null>(null);
  const [libraryObjectKey, setLibraryObjectKey] = useState<string | null>(null);
  const [librarySize, setLibrarySize] = useState(24);
  const [maxOrder, setMaxOrder] = useState(2);
  const [plateFormat, setPlateFormat] = useState(96);
  const [libraryInputMode, setLibraryInputMode] = useState<MutationLibraryInputMode>("latest");
  const [selectedRecommendationArtifactId, setSelectedRecommendationArtifactId] = useState("");
  const [selectedStructureId, setSelectedStructureId] = useState(initialStructureId);
  const [runningRosettaMutation, setRunningRosettaMutation] = useState<string | null>(null);
  const [isRunningLibraryDesign, setIsRunningLibraryDesign] = useState(false);
  const [retryingJobId, setRetryingJobId] = useState<string | null>(null);
  const [loadingArtifactId, setLoadingArtifactId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function loadArtifacts(nextToken: string) {
    setError(null);
    setIsLoading(true);
    try {
      const nextArtifacts = await getAnalysisArtifacts(enzymeId, nextToken);
      setArtifacts(nextArtifacts);
      await loadLatestHomologSequences(nextArtifacts, nextToken);
      await loadLatestConservationProfile(nextArtifacts, nextToken);
      await loadLatestRecommendations(nextArtifacts, nextToken);
      loadLatestRosettaDdgArtifact(nextArtifacts);
      await loadLatestMutationLibrary(nextArtifacts, nextToken);
      await loadRosettaDdgRuns(nextToken);
    } catch {
      setError("Unable to load analysis artifacts. Please check the API service and your login.");
    } finally {
      setIsLoading(false);
    }
  }

  async function loadStructures(nextToken: string) {
    try {
      const nextStructures = await listStructures(enzymeId, nextToken);
      setStructures(nextStructures);
      const structureContext = getStructureContextOptions(nextStructures, selectedStructureId);
      setSelectedStructureId(structureContext.selectedStructureId);
    } catch {
      setStructures([]);
    }
  }

  async function loadLatestHomologSequences(
    nextArtifacts: AnalysisArtifactRecord[],
    nextToken: string
  ) {
    const homologArtifacts = nextArtifacts.filter(
      (artifact) => artifact.artifact_type === "homolog_sequences"
    );
    const latestHomologArtifact = homologArtifacts[homologArtifacts.length - 1];
    if (!latestHomologArtifact) {
      setLatestHomologContent(null);
      setHomologSequences([]);
      setHomologObjectKey(null);
      return;
    }

    try {
      const content = await getAnalysisArtifactContent(enzymeId, latestHomologArtifact.id, nextToken);
      setLatestHomologContent(content);
      setHomologSequences(getHomologSequences(content));
      setHomologObjectKey(content.object_key);
    } catch {
      setLatestHomologContent(null);
      setHomologSequences([]);
      setHomologObjectKey(latestHomologArtifact.object_key);
    }
  }

  async function loadLatestConservationProfile(
    nextArtifacts: AnalysisArtifactRecord[],
    nextToken: string
  ) {
    const conservationArtifacts = nextArtifacts.filter(
      (artifact) => artifact.artifact_type === "conservation_profile"
    );
    const latestConservationArtifact = conservationArtifacts[conservationArtifacts.length - 1];
    if (!latestConservationArtifact) {
      setConservationSites([]);
      setLatestConservationContent(null);
      setConservationObjectKey(null);
      return;
    }

    try {
      const content = await getAnalysisArtifactContent(enzymeId, latestConservationArtifact.id, nextToken);
      setLatestConservationContent(content);
      setConservationSites(getConservationSites(content));
      setConservationObjectKey(content.object_key);
    } catch {
      setConservationSites([]);
      setLatestConservationContent(null);
      setConservationObjectKey(latestConservationArtifact.object_key);
    }
  }

  async function loadLatestRecommendations(
    nextArtifacts: AnalysisArtifactRecord[],
    nextToken: string
  ) {
    const recommendationArtifacts = nextArtifacts.filter(
      (artifact) => artifact.artifact_type === "mutation_recommendations"
    );
    const latestRecommendationArtifact = recommendationArtifacts[recommendationArtifacts.length - 1];
    if (!latestRecommendationArtifact) {
      setRecommendationCandidates([]);
      setRecommendationObjectKey(null);
      return;
    }

    try {
      const content = await getAnalysisArtifactContent(enzymeId, latestRecommendationArtifact.id, nextToken);
      setRecommendationCandidates(getMutationRecommendationCandidates(content));
      setRecommendationObjectKey(content.object_key);
    } catch {
      setRecommendationCandidates([]);
      setRecommendationObjectKey(latestRecommendationArtifact.object_key);
    }
  }

  async function loadRosettaDdgRuns(nextToken: string) {
    try {
      const jobs = await listJobs(nextToken);
      setRosettaRuns(getRosettaDdgRunViews(jobs, enzymeId));
    } catch {
      setRosettaRuns([]);
    }
  }

  function loadLatestRosettaDdgArtifact(nextArtifacts: AnalysisArtifactRecord[]) {
    const rosettaArtifacts = nextArtifacts.filter((artifact) => artifact.artifact_type === "rosetta_ddg");
    const latestRosettaArtifact = rosettaArtifacts[rosettaArtifacts.length - 1];
    if (!latestRosettaArtifact) {
      setRosettaObjectKey(null);
      return;
    }
    setRosettaObjectKey(latestRosettaArtifact.object_key);
  }

  async function loadLatestMutationLibrary(
    nextArtifacts: AnalysisArtifactRecord[],
    nextToken: string
  ) {
    const libraryArtifacts = nextArtifacts.filter((artifact) => artifact.artifact_type === "mutation_library");
    const latestLibraryArtifact = libraryArtifacts[libraryArtifacts.length - 1];
    if (!latestLibraryArtifact) {
      setMutationLibrary(null);
      setLibraryObjectKey(null);
      return;
    }

    try {
      const content = await getAnalysisArtifactContent(enzymeId, latestLibraryArtifact.id, nextToken);
      setMutationLibrary(getMutationLibrary(content));
      setLibraryObjectKey(content.object_key);
    } catch {
      setMutationLibrary(null);
      setLibraryObjectKey(latestLibraryArtifact.object_key);
    }
  }

  async function runAnalysis(jobType: AnalysisJobType) {
    if (!token) {
      return;
    }
    setError(null);
    setNotice(null);
    setRunningJobType(jobType);
    try {
      const parameters = buildAnalysisJobParameters(jobType);
      const job = await createAnalysisJob(enzymeId, token, jobType, parameters);
      setNotice(`${job.job_type} job queued: ${job.id}`);
      await loadArtifacts(token);
    } catch {
      setError("Unable to queue analysis job. Please check that this enzyme has a protein sequence.");
    } finally {
      setRunningJobType(null);
    }
  }

  async function runRosettaDdg(mutationString: string) {
    if (!token) {
      return;
    }
    setError(null);
    setNotice(null);
    setRunningRosettaMutation(mutationString);
    try {
      const job = await createAnalysisJob(
        enzymeId,
        token,
        "rosetta_ddg",
        buildRosettaDdgJobParameters(mutationString, selectedStructureId)
      );
      setNotice(`${job.job_type} job queued for ${mutationString}: ${job.id}`);
      await loadArtifacts(token);
    } catch {
      setError("Unable to queue Rosetta ddG job. Please check that this enzyme has a structure and mutation string.");
    } finally {
      setRunningRosettaMutation(null);
    }
  }

  async function retryRosettaDdgJob(jobId: string) {
    if (!token) {
      return;
    }
    setError(null);
    setNotice(null);
    setRetryingJobId(jobId);
    try {
      const job = await retryJob(jobId, token);
      setNotice(`${job.job_type} job requeued: ${job.id}`);
      await loadArtifacts(token);
    } catch {
      setError("Unable to retry Rosetta ddG job. Only failed Rosetta jobs can be retried.");
    } finally {
      setRetryingJobId(null);
    }
  }

  async function runLibraryDesign() {
    if (!token) {
      return;
    }
    setError(null);
    setNotice(null);
    setIsRunningLibraryDesign(true);
    try {
      const job = await createAnalysisJob(enzymeId, token, "library_design", {
        ...buildLibraryDesignParameters(
          librarySize,
          maxOrder,
          plateFormat,
          libraryInputMode,
          selectedRecommendationArtifactId ||
            recommendationArtifactOptions[recommendationArtifactOptions.length - 1]?.id ||
            ""
        )
      });
      setNotice(`${job.job_type} job queued: ${job.id}`);
      await loadArtifacts(token);
    } catch {
      setError("Unable to queue mutation library design. Please run hotspot recommendations first.");
    } finally {
      setIsRunningLibraryDesign(false);
    }
  }

  async function viewArtifactContent(artifact: AnalysisArtifactRecord) {
    if (!token) {
      return;
    }
    setError(null);
    setLoadingArtifactId(artifact.id);
    try {
      setSelectedContent(await getAnalysisArtifactContent(enzymeId, artifact.id, token));
    } catch {
      setError("Unable to load artifact content. This artifact may have been created before preview payloads were enabled.");
    } finally {
      setLoadingArtifactId(null);
    }
  }

  function downloadLatestConservationProfile() {
    if (!latestConservationContent) {
      return;
    }
    const payload = buildConservationDownloadJson(latestConservationContent, conservationSites);
    const blob = new Blob([payload], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `conservation-profile-${enzymeId}.json`;
    link.click();
    URL.revokeObjectURL(url);
  }

  function downloadArtifactLineage(artifact: AnalysisArtifactRecord) {
    const blob = new Blob([buildAnalysisArtifactLineageJson(artifact)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `analysis-lineage-${artifact.id}.json`;
    link.click();
    URL.revokeObjectURL(url);
  }

  function downloadAnalysisManifest() {
    const blob = new Blob([buildAnalysisRunManifestJson(enzymeId, artifacts)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `analysis-manifest-${enzymeId}.json`;
    link.click();
    URL.revokeObjectURL(url);
  }

  function buildAnalysisJobParameters(jobType: AnalysisJobType) {
    if (jobType === "homolog_collection") {
      return {
        search_mode: homologSearchMode,
        max_sequences: maxHomologSequences
      };
    }
    if (jobType === "msa") {
      const fallbackArtifactId = homologArtifactOptions[homologArtifactOptions.length - 1]?.id ?? "";
      return buildMsaJobParameters(
        msaInputMode,
        selectedHomologArtifactId || fallbackArtifactId,
        customMsaFasta
      );
    }
    if (jobType === "conservation_profile") {
      const fallbackArtifactId = msaArtifactOptions[msaArtifactOptions.length - 1]?.id ?? "";
      return buildConservationJobParameters(
        conservationInputMode,
        selectedMsaArtifactId || fallbackArtifactId
      );
    }
    if (jobType === "mutation_recommendation") {
      const fallbackArtifactId =
        conservationArtifactOptions[conservationArtifactOptions.length - 1]?.id ?? "";
      return buildMutationRecommendationJobParameters(
        recommendationInputMode,
        selectedConservationArtifactId || fallbackArtifactId,
        selectedStructureId
      );
    }
    return undefined;
  }

  function downloadHomologFasta() {
    if (!latestHomologContent) {
      return;
    }
    const blob = new Blob([buildHomologFasta(latestHomologContent)], { type: "text/x-fasta" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `homolog-sequences-${enzymeId}.fasta`;
    link.click();
    URL.revokeObjectURL(url);
  }

  function downloadHomologCsv() {
    if (!latestHomologContent) {
      return;
    }
    const blob = new Blob([buildHomologCsv(latestHomologContent)], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `homolog-sequences-${enzymeId}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  }

  function downloadMutationLibraryCsv() {
    if (!mutationLibrary?.csv_text) {
      return;
    }
    const blob = new Blob([mutationLibrary.csv_text], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `mutation-library-${enzymeId}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  }

  function downloadMutationLibraryXlsx() {
    if (!mutationLibrary) {
      return;
    }
    const workbookBytes = buildMutationLibraryWorkbookBytes(mutationLibrary);
    const workbookBuffer = new ArrayBuffer(workbookBytes.byteLength);
    new Uint8Array(workbookBuffer).set(workbookBytes);
    const blob = new Blob([workbookBuffer], {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `mutation-library-${enzymeId}.xlsx`;
    link.click();
    URL.revokeObjectURL(url);
  }

  useEffect(() => {
    const storedToken = window.localStorage.getItem(TOKEN_KEY);
    if (!storedToken) {
      router.replace("/login");
      return;
    }
    setToken(storedToken);
    void loadArtifacts(storedToken);
    void loadStructures(storedToken);
  }, [enzymeId, router]);

  const filteredConservationSites = filterConservationSites(conservationSites, conservationFilter);
  const homologDiagnostics = latestHomologContent ? getHomologDiagnostics(latestHomologContent) : null;
  const homologArtifactOptions = getHomologArtifactOptions(artifacts);
  const msaArtifactOptions = getMsaArtifactOptions(artifacts);
  const conservationArtifactOptions = getConservationArtifactOptions(artifacts);
  const recommendationArtifactOptions = getRecommendationArtifactOptions(artifacts);
  const structureContext = getStructureContextOptions(structures, selectedStructureId);
  const hasStructureWorkflowFocus = Boolean(initialFocus && structureContext.selectedStructureId);

  return (
    <main className="mx-auto max-w-6xl px-6 py-8">
      <header className="border-b border-slate-200 pb-6">
        <p className="text-sm font-medium text-slate-500">MSA / Conservation</p>
        <div className="mt-2 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold text-slate-950">Evolutionary analysis</h1>
            <p className="mt-2 text-sm text-slate-600">Entry id: {enzymeId}</p>
          </div>
          <button
            className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-800 disabled:cursor-not-allowed disabled:text-slate-400"
            disabled={!token || isLoading}
            onClick={() => token && void loadArtifacts(token)}
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
      {notice ? (
        <p className="mt-4 rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-700">
          {notice}
        </p>
      ) : null}
      {hasStructureWorkflowFocus ? (
        <p className="mt-4 rounded-md border border-sky-200 bg-sky-50 px-3 py-2 text-sm text-sky-800">
          Structure workflow selected {structureContext.selectedStructureId}. Use the highlighted module below to run {
            initialFocus === "rosetta_ddg" ? "Rosetta ddG from scored mutations" : "structure-aware hotspot recommendations"
          }.
        </p>
      ) : null}

      {isLoading ? <p className="mt-6 text-sm text-slate-600">Loading analysis artifacts...</p> : null}

      <section className="mt-6 grid gap-3 md:grid-cols-2 lg:grid-cols-4">
        {analysisModules.map((item) => {
          const moduleArtifacts = artifacts.filter((artifact) => artifact.artifact_type === item.artifactType);
          const latestArtifact = moduleArtifacts[moduleArtifacts.length - 1];
          const isRunning = runningJobType === item.jobType;
          const isMsaBlocked =
            item.jobType === "msa" &&
            (
              (msaInputMode === "artifact" && homologArtifactOptions.length === 0) ||
              (msaInputMode === "custom_fasta" && customMsaFasta.trim().length === 0)
            );
          const isConservationBlocked =
            item.jobType === "conservation_profile" &&
            conservationInputMode === "artifact" &&
            msaArtifactOptions.length === 0;
          const isRecommendationBlocked =
            item.jobType === "mutation_recommendation" &&
            recommendationInputMode === "artifact" &&
            conservationArtifactOptions.length === 0;
          const isFocusedModule =
            initialFocus === "mutation_recommendation" && item.jobType === "mutation_recommendation";
          const cardClassName = isFocusedModule
            ? "rounded-md border border-sky-300 bg-sky-50 p-4"
            : "rounded-md border border-slate-200 bg-white p-4";
          return (
            <article className={cardClassName} key={item.artifactType}>
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h2 className="text-base font-semibold text-slate-950">{item.title}</h2>
                  <p className="mt-1 text-sm text-slate-600">{item.metric}</p>
                </div>
                <StatusPill value={latestArtifact?.job_status ?? "not_run"} />
              </div>
              <dl className="mt-4 grid gap-3">
                <div>
                  <dt className="text-xs font-medium uppercase text-slate-500">Artifact</dt>
                  <dd className="mt-1 break-words font-mono text-sm text-slate-950">{item.artifactType}</dd>
                </div>
                <div>
                  <dt className="text-xs font-medium uppercase text-slate-500">Latest object</dt>
                  <dd className="mt-1 break-words font-mono text-xs text-slate-700">
                    {latestArtifact?.object_key ?? "-"}
                  </dd>
                </div>
              </dl>
              {item.jobType === "homolog_collection" ? (
                <div className="mt-4 grid gap-3 border-t border-slate-200 pt-4">
                  <label className="grid gap-1 text-xs font-medium uppercase text-slate-500">
                    Search mode
                    <select
                      className="rounded-md border border-slate-300 bg-white px-2 py-2 text-sm font-normal normal-case text-slate-800"
                      onChange={(event) => setHomologSearchMode(event.target.value)}
                      value={homologSearchMode}
                    >
                      {homologSearchModeOptions.map((option) => (
                        <option key={option.value} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="grid gap-1 text-xs font-medium uppercase text-slate-500">
                    Max homologs
                    <select
                      className="rounded-md border border-slate-300 bg-white px-2 py-2 text-sm font-normal normal-case text-slate-800"
                      onChange={(event) => setMaxHomologSequences(Number(event.target.value))}
                      value={maxHomologSequences}
                    >
                      {homologCountOptions.map((count) => (
                        <option key={count} value={count}>
                          {count}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
              ) : null}
              {item.jobType === "msa" ? (
                <div className="mt-4 grid gap-3 border-t border-slate-200 pt-4">
                  <label className="grid gap-1 text-xs font-medium uppercase text-slate-500">
                    Input source
                    <select
                      className="rounded-md border border-slate-300 bg-white px-2 py-2 text-sm font-normal normal-case text-slate-800"
                      onChange={(event) => setMsaInputMode(event.target.value as MsaInputMode)}
                      value={msaInputMode}
                    >
                      <option value="latest">Latest homologs</option>
                      <option value="artifact">Previous homolog run</option>
                      <option value="custom_fasta">Custom FASTA</option>
                    </select>
                  </label>
                  {msaInputMode === "artifact" ? (
                    <label className="grid gap-1 text-xs font-medium uppercase text-slate-500">
                      Homolog run
                      <select
                        className="rounded-md border border-slate-300 bg-white px-2 py-2 text-sm font-normal normal-case text-slate-800 disabled:cursor-not-allowed disabled:bg-slate-50 disabled:text-slate-400"
                        disabled={homologArtifactOptions.length === 0}
                        onChange={(event) => setSelectedHomologArtifactId(event.target.value)}
                        value={selectedHomologArtifactId || homologArtifactOptions[homologArtifactOptions.length - 1]?.id || ""}
                      >
                        {homologArtifactOptions.length === 0 ? (
                          <option value="">No homolog runs</option>
                        ) : (
                          homologArtifactOptions.map((option) => (
                            <option key={option.id} value={option.id}>
                              {option.label}
                            </option>
                          ))
                        )}
                      </select>
                    </label>
                  ) : null}
                  {msaInputMode === "custom_fasta" ? (
                    <label className="grid gap-1 text-xs font-medium uppercase text-slate-500">
                      FASTA
                      <textarea
                        className="min-h-32 rounded-md border border-slate-300 bg-white px-2 py-2 font-mono text-xs font-normal normal-case text-slate-800"
                        onChange={(event) => setCustomMsaFasta(event.target.value)}
                        placeholder={">seq1\nMTA...\n>seq2\nMTA..."}
                        value={customMsaFasta}
                      />
                    </label>
                  ) : null}
                </div>
              ) : null}
              {item.jobType === "conservation_profile" ? (
                <div className="mt-4 grid gap-3 border-t border-slate-200 pt-4">
                  <label className="grid gap-1 text-xs font-medium uppercase text-slate-500">
                    Input source
                    <select
                      className="rounded-md border border-slate-300 bg-white px-2 py-2 text-sm font-normal normal-case text-slate-800"
                      onChange={(event) => setConservationInputMode(event.target.value as ConservationInputMode)}
                      value={conservationInputMode}
                    >
                      <option value="latest">Latest MSA</option>
                      <option value="artifact">Previous MSA run</option>
                    </select>
                  </label>
                  {conservationInputMode === "artifact" ? (
                    <label className="grid gap-1 text-xs font-medium uppercase text-slate-500">
                      MSA run
                      <select
                        className="rounded-md border border-slate-300 bg-white px-2 py-2 text-sm font-normal normal-case text-slate-800 disabled:cursor-not-allowed disabled:bg-slate-50 disabled:text-slate-400"
                        disabled={msaArtifactOptions.length === 0}
                        onChange={(event) => setSelectedMsaArtifactId(event.target.value)}
                        value={selectedMsaArtifactId || msaArtifactOptions[msaArtifactOptions.length - 1]?.id || ""}
                      >
                        {msaArtifactOptions.length === 0 ? (
                          <option value="">No MSA runs</option>
                        ) : (
                          msaArtifactOptions.map((option) => (
                            <option key={option.id} value={option.id}>
                              {option.label}
                            </option>
                          ))
                        )}
                      </select>
                    </label>
                  ) : null}
                </div>
              ) : null}
              {item.jobType === "mutation_recommendation" ? (
                <div className="mt-4 grid gap-3 border-t border-slate-200 pt-4">
                  <label className="grid gap-1 text-xs font-medium uppercase text-slate-500">
                    Input source
                    <select
                      className="rounded-md border border-slate-300 bg-white px-2 py-2 text-sm font-normal normal-case text-slate-800"
                      onChange={(event) => (
                        setRecommendationInputMode(event.target.value as MutationRecommendationInputMode)
                      )}
                      value={recommendationInputMode}
                    >
                      <option value="latest">Latest conservation</option>
                      <option value="artifact">Previous conservation run</option>
                    </select>
                  </label>
                  {recommendationInputMode === "artifact" ? (
                    <label className="grid gap-1 text-xs font-medium uppercase text-slate-500">
                      Conservation run
                      <select
                        className="rounded-md border border-slate-300 bg-white px-2 py-2 text-sm font-normal normal-case text-slate-800 disabled:cursor-not-allowed disabled:bg-slate-50 disabled:text-slate-400"
                        disabled={conservationArtifactOptions.length === 0}
                        onChange={(event) => setSelectedConservationArtifactId(event.target.value)}
                        value={
                          selectedConservationArtifactId ||
                          conservationArtifactOptions[conservationArtifactOptions.length - 1]?.id ||
                          ""
                        }
                      >
                        {conservationArtifactOptions.length === 0 ? (
                          <option value="">No conservation runs</option>
                        ) : (
                          conservationArtifactOptions.map((option) => (
                            <option key={option.id} value={option.id}>
                              {option.label}
                            </option>
                          ))
                        )}
                      </select>
                    </label>
                  ) : null}
                </div>
              ) : null}
              <button
                className="mt-4 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-800 disabled:cursor-not-allowed disabled:text-slate-400"
                disabled={
                  !token ||
                  Boolean(runningJobType) ||
                  isMsaBlocked ||
                  isConservationBlocked ||
                  isRecommendationBlocked
                }
                onClick={() => void runAnalysis(item.jobType)}
                type="button"
              >
                {isRunning ? "Queueing..." : item.actionLabel}
              </button>
            </article>
          );
        })}
      </section>

      <section className="mt-8 overflow-hidden rounded-md border border-slate-200 bg-white">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-4 py-3">
          <h2 className="text-base font-semibold text-slate-950">Analysis artifacts</h2>
          <button
            className="rounded-md border border-slate-300 bg-white px-2 py-1 text-xs font-medium text-slate-800 disabled:cursor-not-allowed disabled:text-slate-400"
            disabled={artifacts.length === 0}
            onClick={downloadAnalysisManifest}
            type="button"
          >
            Manifest
          </button>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-200 text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase text-slate-500">
              <tr>
                <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">
                  Type
                </th>
                <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">
                  Status
                </th>
                <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">
                  Object key
                </th>
                <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">
                  Input source
                </th>
                <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">
                  Size
                </th>
                <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">
                  Content
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-slate-700">
              {artifacts.length > 0 ? (
                artifacts.map((artifact) => (
                  <tr key={artifact.id}>
                    <td className="px-4 py-3 font-mono text-slate-950">{artifact.artifact_type}</td>
                    <td className="px-4 py-3">
                      <StatusPill value={artifact.job_status ?? "-"} />
                    </td>
                    <td className="max-w-md px-4 py-3">
                      <span className="break-words font-mono text-xs">{artifact.object_key}</span>
                    </td>
                    <td className="max-w-sm px-4 py-3">
                      <span className="break-words font-mono text-xs text-slate-600">
                        {formatAnalysisArtifactSource(artifact)}
                      </span>
                    </td>
                    <td className="px-4 py-3">{artifact.size_bytes ?? "-"}</td>
                    <td className="px-4 py-3">
                      <div className="flex flex-wrap gap-2">
                      <button
                        className="rounded-md border border-slate-300 bg-white px-2 py-1 text-xs font-medium text-slate-800 disabled:cursor-not-allowed disabled:text-slate-400"
                        disabled={!token || loadingArtifactId === artifact.id}
                        onClick={() => void viewArtifactContent(artifact)}
                        type="button"
                      >
                        {loadingArtifactId === artifact.id ? "Loading..." : "View"}
                      </button>
                      <button
                        className="rounded-md border border-slate-300 bg-white px-2 py-1 text-xs font-medium text-slate-800"
                        onClick={() => downloadArtifactLineage(artifact)}
                        type="button"
                      >
                        Lineage
                      </button>
                      </div>
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td className="px-4 py-4 text-slate-500" colSpan={6}>
                    No analysis artifacts
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      {selectedContent ? <ArtifactContentPanel content={selectedContent} /> : null}

      <section
        className={`mt-8 overflow-hidden rounded-md border bg-white ${
          initialFocus === "rosetta_ddg" ? "border-sky-300 ring-1 ring-sky-200" : "border-slate-200"
        }`}
      >
        <div className="border-b border-slate-200 px-4 py-3">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h2 className="text-base font-semibold text-slate-950">Homolog sequence hits</h2>
              {homologObjectKey ? (
                <p className="mt-1 break-words font-mono text-xs text-slate-500">{homologObjectKey}</p>
              ) : null}
              <p className="mt-1 text-xs text-slate-500">{homologSequences.length} filtered homologs</p>
              {homologDiagnostics ? <HomologDiagnosticsStrip diagnostics={homologDiagnostics} /> : null}
            </div>
            {latestHomologContent ? (
              <div className="flex flex-wrap items-center justify-end gap-2">
                <button
                  className="rounded-md border border-slate-300 bg-white px-2 py-1 text-xs font-medium text-slate-800"
                  onClick={downloadHomologFasta}
                  type="button"
                >
                  FASTA
                </button>
                <button
                  className="rounded-md border border-slate-300 bg-white px-2 py-1 text-xs font-medium text-slate-800"
                  onClick={downloadHomologCsv}
                  type="button"
                >
                  CSV
                </button>
                <RunnerBadge label={getArtifactRunnerLabel(latestHomologContent)} />
              </div>
            ) : null}
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-200 text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase text-slate-500">
              <tr>
                <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">
                  Accession
                </th>
                <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">
                  Protein
                </th>
                <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">
                  Organism
                </th>
                <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">
                  Identity
                </th>
                <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">
                  Coverage
                </th>
                <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">
                  Length
                </th>
                <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">
                  Source
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-slate-700">
              {homologSequences.length > 0 ? (
                homologSequences.map((homolog) => (
                  <tr key={homolog.accession}>
                    <td className="px-4 py-3 font-mono text-xs text-slate-950">{homolog.accession}</td>
                    <td className="max-w-sm px-4 py-3 text-slate-950">{homolog.name}</td>
                    <td className="px-4 py-3">{homolog.organism}</td>
                    <td className="px-4 py-3 font-mono text-xs">{homolog.identity}</td>
                    <td className="px-4 py-3 font-mono text-xs">{homolog.coverage}</td>
                    <td className="px-4 py-3 font-mono text-xs">{homolog.sequence_length}</td>
                    <td className="px-4 py-3 font-mono text-xs">{homolog.source}</td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td className="px-4 py-4 text-slate-500" colSpan={7}>
                    {homologObjectKey ? "No homologs passed identity and coverage filters" : "No homolog sequence artifact"}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="mt-8 overflow-hidden rounded-md border border-slate-200 bg-white">
        <div className="border-b border-slate-200 px-4 py-3">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h2 className="text-base font-semibold text-slate-950">Conservation profile</h2>
              {conservationObjectKey ? (
                <p className="mt-1 break-words font-mono text-xs text-slate-500">{conservationObjectKey}</p>
              ) : null}
              <p className="mt-1 text-xs text-slate-500">
                Showing {filteredConservationSites.length} of {conservationSites.length} sites
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <label className="text-xs font-medium uppercase text-slate-500" htmlFor="conservation-filter">
                Category
              </label>
              <select
                className="rounded-md border border-slate-300 bg-white px-2 py-1 text-sm text-slate-800"
                id="conservation-filter"
                onChange={(event) => setConservationFilter(event.target.value as ConservationCategoryFilter)}
                value={conservationFilter}
              >
                <option value="all">All</option>
                <option value="highly_conserved">Highly conserved</option>
                <option value="moderately_conserved">Moderately conserved</option>
                <option value="variable">Variable</option>
              </select>
              <button
                className="rounded-md border border-slate-300 bg-white px-3 py-1 text-sm font-medium text-slate-800 disabled:cursor-not-allowed disabled:text-slate-400"
                disabled={!latestConservationContent}
                onClick={downloadLatestConservationProfile}
                type="button"
              >
                Download JSON
              </button>
            </div>
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-200 text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase text-slate-500">
              <tr>
                <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">
                  Position
                </th>
                <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">
                  WT
                </th>
                <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">
                  Entropy
                </th>
                <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">
                  WT frequency
                </th>
                <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">
                  Category
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-slate-700">
              {filteredConservationSites.length > 0 ? (
                filteredConservationSites.map((site) => (
                  <tr key={`${site.query_position}-${site.wildtype_residue}`}>
                    <td className="px-4 py-3 font-medium text-slate-950">{site.query_position}</td>
                    <td className="px-4 py-3 font-mono">{site.wildtype_residue}</td>
                    <td className="px-4 py-3">{site.shannon_entropy}</td>
                    <td className="px-4 py-3">{site.wildtype_frequency}</td>
                    <td className="px-4 py-3">
                      <span className="rounded bg-slate-100 px-2 py-1 text-xs font-medium text-slate-700">
                        {site.conservation_category}
                      </span>
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td className="px-4 py-4 text-slate-500" colSpan={5}>
                    {conservationSites.length > 0 ? "No sites match this filter" : "No conservation profile artifact"}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="mt-8 overflow-hidden rounded-md border border-slate-200 bg-white">
        <div className="border-b border-slate-200 px-4 py-3">
          <h2 className="text-base font-semibold text-slate-950">Hotspot recommendations</h2>
          {recommendationObjectKey ? (
            <p className="mt-1 break-words font-mono text-xs text-slate-500">{recommendationObjectKey}</p>
          ) : null}
          <p className="mt-1 text-xs text-slate-500">{recommendationCandidates.length} candidate sites</p>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-200 text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase text-slate-500">
              <tr>
                <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">Position</th>
                <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">WT</th>
                <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">Category</th>
                <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">Score</th>
                <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">Scored suggestions</th>
                <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">Rationale</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-slate-700">
              {recommendationCandidates.length > 0 ? (
                recommendationCandidates.map((candidate) => (
                  <tr key={`${candidate.query_position}-${candidate.wildtype_residue}`}>
                    <td className="px-4 py-3 font-medium text-slate-950">{candidate.query_position}</td>
                    <td className="px-4 py-3 font-mono">{candidate.wildtype_residue}</td>
                    <td className="px-4 py-3">
                      <span className="rounded bg-slate-100 px-2 py-1 text-xs font-medium text-slate-700">
                        {candidate.conservation_category}
                      </span>
                    </td>
                    <td className="px-4 py-3">{candidate.priority_score}</td>
                    <td className="min-w-96 px-4 py-3">
                      <ScoredSuggestionList
                        disabled={!token || Boolean(runningRosettaMutation)}
                        fallbackMutations={candidate.suggested_mutations}
                        onRunRosettaDdg={(mutation) => void runRosettaDdg(mutation)}
                        runningMutation={runningRosettaMutation}
                        suggestions={candidate.scored_suggestions}
                      />
                    </td>
                    <td className="min-w-80 px-4 py-3 text-xs text-slate-600">{candidate.rationale}</td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td className="px-4 py-4 text-slate-500" colSpan={6}>
                    No hotspot recommendation artifact
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="mt-8 overflow-hidden rounded-md border border-slate-200 bg-white">
        <div className="border-b border-slate-200 px-4 py-3">
          <h2 className="text-base font-semibold text-slate-950">Rosetta ddG jobs</h2>
          {rosettaObjectKey ? (
            <p className="mt-1 break-words font-mono text-xs text-slate-500">{rosettaObjectKey}</p>
          ) : null}
          <p className="mt-1 text-xs text-slate-500">{rosettaRuns.length} submitted jobs</p>
          <label className="mt-3 grid max-w-xl gap-1 text-xs font-medium text-slate-600">
            Structure context for recommendations and ddG jobs
            <select
              className="rounded-md border border-slate-300 bg-white px-3 py-2 font-mono text-xs text-slate-950"
              onChange={(event) => setSelectedStructureId(event.target.value)}
              value={structureContext.selectedStructureId}
            >
              {structureContext.options.length > 0 ? (
                structureContext.options.map((option) => (
                  <option key={option.id} value={option.id}>
                    {option.label}
                  </option>
                ))
              ) : (
                <option value="">No structure available</option>
              )}
            </select>
          </label>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-200 text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase text-slate-500">
              <tr>
                <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">Job</th>
                <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">Status</th>
                <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">Mutation</th>
                <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">Structure</th>
                <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">Mutation file</th>
                <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">ddG kcal/mol</th>
                <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">Interpretation</th>
                <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">Runner</th>
                <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">Error</th>
                <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-slate-700">
              {rosettaRuns.length > 0 ? (
                rosettaRuns.map((run) => (
                  <tr key={run.job_id}>
                    <td className="px-4 py-3 font-mono text-xs text-slate-950">{run.job_id}</td>
                    <td className="px-4 py-3"><StatusPill value={run.status} /></td>
                    <td className="px-4 py-3 font-mono text-slate-950">{run.mutation_string}</td>
                    <td className="px-4 py-3 font-mono text-xs">{run.structure_id}</td>
                    <td className="px-4 py-3 font-mono text-xs">{run.mutation_file}</td>
                    <td className="px-4 py-3">{run.ddg_kcal_per_mol}</td>
                    <td className="px-4 py-3">
                      <span className="rounded bg-slate-100 px-2 py-1 text-xs font-medium text-slate-700">
                        {run.interpretation}
                      </span>
                    </td>
                    <td className="px-4 py-3 font-mono text-xs">{run.runner}</td>
                    <td className="min-w-72 px-4 py-3 text-xs text-slate-600">{run.error_message}</td>
                    <td className="px-4 py-3">
                      {run.can_retry ? (
                        <button
                          className="rounded-md border border-slate-300 bg-white px-2 py-1 text-xs font-medium text-slate-800 disabled:cursor-not-allowed disabled:text-slate-400"
                          disabled={!token || retryingJobId === run.job_id}
                          onClick={() => void retryRosettaDdgJob(run.job_id)}
                          type="button"
                        >
                          {retryingJobId === run.job_id ? "Retrying..." : "Retry"}
                        </button>
                      ) : (
                        "-"
                      )}
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td className="px-4 py-4 text-slate-500" colSpan={10}>
                    No Rosetta ddG job
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="mt-8 overflow-hidden rounded-md border border-slate-200 bg-white">
        <div className="border-b border-slate-200 px-4 py-3">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h2 className="text-base font-semibold text-slate-950">Mutation library</h2>
              {libraryObjectKey ? (
                <p className="mt-1 break-words font-mono text-xs text-slate-500">{libraryObjectKey}</p>
              ) : null}
              <p className="mt-1 text-xs text-slate-500">
                {mutationLibrary ? `${mutationLibrary.variant_count} variants` : "No mutation library artifact"}
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <label className="text-xs font-medium uppercase text-slate-500" htmlFor="library-source">
                Source
              </label>
              <select
                className="rounded-md border border-slate-300 bg-white px-2 py-1 text-sm text-slate-800"
                id="library-source"
                onChange={(event) => setLibraryInputMode(event.target.value as MutationLibraryInputMode)}
                value={libraryInputMode}
              >
                <option value="latest">Latest recommendations</option>
                <option value="artifact">Previous recommendation run</option>
              </select>
              {libraryInputMode === "artifact" ? (
                <select
                  className="rounded-md border border-slate-300 bg-white px-2 py-1 text-sm text-slate-800 disabled:cursor-not-allowed disabled:bg-slate-50 disabled:text-slate-400"
                  disabled={recommendationArtifactOptions.length === 0}
                  onChange={(event) => setSelectedRecommendationArtifactId(event.target.value)}
                  value={
                    selectedRecommendationArtifactId ||
                    recommendationArtifactOptions[recommendationArtifactOptions.length - 1]?.id ||
                    ""
                  }
                >
                  {recommendationArtifactOptions.length === 0 ? (
                    <option value="">No recommendation runs</option>
                  ) : (
                    recommendationArtifactOptions.map((option) => (
                      <option key={option.id} value={option.id}>
                        {option.label}
                      </option>
                    ))
                  )}
                </select>
              ) : null}
              <label className="text-xs font-medium uppercase text-slate-500" htmlFor="library-size">
                Size
              </label>
              <select
                className="rounded-md border border-slate-300 bg-white px-2 py-1 text-sm text-slate-800"
                id="library-size"
                onChange={(event) => setLibrarySize(Number(event.target.value))}
                value={librarySize}
              >
                <option value={24}>24</option>
                <option value={48}>48</option>
                <option value={96}>96</option>
                <option value={384}>384</option>
              </select>
              <label className="text-xs font-medium uppercase text-slate-500" htmlFor="max-order">
                Max sites
              </label>
              <select
                className="rounded-md border border-slate-300 bg-white px-2 py-1 text-sm text-slate-800"
                id="max-order"
                onChange={(event) => setMaxOrder(Number(event.target.value))}
                value={maxOrder}
              >
                <option value={2}>2</option>
                <option value={3}>3</option>
              </select>
              <label className="text-xs font-medium uppercase text-slate-500" htmlFor="plate-format">
                Plate
              </label>
              <select
                className="rounded-md border border-slate-300 bg-white px-2 py-1 text-sm text-slate-800"
                id="plate-format"
                onChange={(event) => setPlateFormat(Number(event.target.value))}
                value={plateFormat}
              >
                <option value={96}>96</option>
                <option value={384}>384</option>
              </select>
              <button
                className="rounded-md border border-slate-300 bg-white px-3 py-1 text-sm font-medium text-slate-800 disabled:cursor-not-allowed disabled:text-slate-400"
                disabled={
                  !token ||
                  isRunningLibraryDesign ||
                  (libraryInputMode === "artifact" && recommendationArtifactOptions.length === 0)
                }
                onClick={() => void runLibraryDesign()}
                type="button"
              >
                {isRunningLibraryDesign ? "Queueing..." : "Run library"}
              </button>
              <button
                className="rounded-md border border-slate-300 bg-white px-3 py-1 text-sm font-medium text-slate-800 disabled:cursor-not-allowed disabled:text-slate-400"
                disabled={!mutationLibrary?.csv_text}
                onClick={downloadMutationLibraryCsv}
                type="button"
              >
                Download CSV
              </button>
              <button
                className="rounded-md border border-slate-300 bg-white px-3 py-1 text-sm font-medium text-slate-800 disabled:cursor-not-allowed disabled:text-slate-400"
                disabled={!mutationLibrary}
                onClick={downloadMutationLibraryXlsx}
                type="button"
              >
                Download XLSX
              </button>
            </div>
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-200 text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase text-slate-500">
              <tr>
                <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">Variant</th>
                <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">Mutation</th>
                <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">Order</th>
                <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">Score</th>
                <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">Member scores</th>
                <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">Risk</th>
                <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">Reason</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-slate-700">
              {mutationLibrary?.variants.length ? (
                mutationLibrary.variants.map((variant) => (
                  <tr key={variant.variant_id}>
                    <td className="px-4 py-3 font-mono text-xs text-slate-950">{variant.variant_id}</td>
                    <td className="px-4 py-3 font-mono text-slate-950">{variant.mutation_string}</td>
                    <td className="px-4 py-3">{variant.order}</td>
                    <td className="px-4 py-3">{variant.score}</td>
                    <td className="px-4 py-3">
                      <MemberScoreList memberScores={variant.member_scores} />
                    </td>
                    <td className="px-4 py-3 text-xs">{variant.risk_flags.join(", ") || "-"}</td>
                    <td className="min-w-80 px-4 py-3 text-xs text-slate-600">
                      {variant.reasons.join("; ")}
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td className="px-4 py-4 text-slate-500" colSpan={7}>
                    No mutation library artifact
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        {mutationLibrary?.plate_layout.length ? (
          <div className="border-t border-slate-200">
            <div className="grid grid-cols-6 gap-2 p-4 sm:grid-cols-8 md:grid-cols-12">
              {mutationLibrary.plate_layout.slice(0, 96).map((well) => (
                <div
                  className="min-h-20 rounded-md border border-slate-200 bg-slate-50 p-2"
                  key={`${well.well}-${well.variant_id}`}
                  title={well.mutation_string}
                >
                  <p className="font-mono text-xs font-semibold text-slate-950">{well.well}</p>
                  <p className="mt-1 truncate font-mono text-xs text-slate-700">{well.variant_id}</p>
                  <p className="mt-1 truncate font-mono text-xs text-slate-500">{well.mutation_string || "-"}</p>
                </div>
              ))}
            </div>
          </div>
        ) : null}
      </section>
    </main>
  );
}

function ArtifactContentPanel({ content }: { content: AnalysisArtifactContentRecord }) {
  const homologs = getHomologSequences(content);
  const msaRecords = getMsaRecords(content);
  const sites = getConservationSites(content);
  const candidates = getMutationRecommendationCandidates(content);
  const rosettaResults = getRosettaDdgResults(content);
  const mutationLibrary = getMutationLibrary(content);
  const runnerLabel = getArtifactRunnerLabel(content);
  const structureId = getAnalysisArtifactStructureId(content);

  function downloadMsaFasta() {
    const fasta = buildMsaDownloadFasta(content);
    if (!fasta) {
      return;
    }
    const blob = new Blob([fasta], { type: "text/x-fasta" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "msa.fasta";
    link.click();
    URL.revokeObjectURL(url);
  }

  return (
    <section className="mt-8 overflow-hidden rounded-md border border-slate-200 bg-white">
      <div className="border-b border-slate-200 px-4 py-3">
        <h2 className="text-base font-semibold text-slate-950">Artifact content</h2>
        <p className="mt-1 break-words font-mono text-xs text-slate-500">{content.object_key}</p>
        <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
          <span className="rounded border border-slate-200 bg-slate-50 px-2 py-1 font-mono text-slate-700">
            {runnerLabel.text}
          </span>
          {runnerLabel.warning ? <span className="text-amber-700">{runnerLabel.warning}</span> : null}
          {structureId ? (
            <span className="rounded border border-slate-200 bg-slate-50 px-2 py-1 font-mono text-slate-700">
              structure {structureId}
            </span>
          ) : null}
          {msaRecords.length > 0 ? (
            <button
              className="rounded border border-slate-300 bg-white px-2 py-1 font-medium text-slate-800"
              onClick={downloadMsaFasta}
              type="button"
            >
              FASTA
            </button>
          ) : null}
        </div>
      </div>
      {homologs.length > 0 ? (
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-200 text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase text-slate-500">
              <tr>
                <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">Accession</th>
                <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">Protein</th>
                <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">Organism</th>
                <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">Identity</th>
                <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">Coverage</th>
                <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">Length</th>
                <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">Source</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-slate-700">
              {homologs.map((homolog) => (
                <tr key={homolog.accession}>
                  <td className="px-4 py-3 font-mono text-xs text-slate-950">{homolog.accession}</td>
                  <td className="max-w-sm px-4 py-3 text-slate-950">{homolog.name}</td>
                  <td className="px-4 py-3">{homolog.organism}</td>
                  <td className="px-4 py-3 font-mono text-xs">{homolog.identity}</td>
                  <td className="px-4 py-3 font-mono text-xs">{homolog.coverage}</td>
                  <td className="px-4 py-3 font-mono text-xs">{homolog.sequence_length}</td>
                  <td className="px-4 py-3 font-mono text-xs">{homolog.source}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : msaRecords.length > 0 ? (
        <MsaRecordTable records={msaRecords} />
      ) : rosettaResults.length > 0 ? (
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-200 text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase text-slate-500">
              <tr>
                <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">Mutation</th>
                <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">Mutation file</th>
                <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">ddG kcal/mol</th>
                <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">Interpretation</th>
                <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">Structure</th>
                <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">Runner</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-slate-700">
              {rosettaResults.map((result) => (
                <tr key={result.mutation_string}>
                  <td className="px-4 py-3 font-mono text-slate-950">{result.mutation_string}</td>
                  <td className="px-4 py-3 font-mono text-xs">{result.mutation_file}</td>
                  <td className="px-4 py-3">{result.ddg_kcal_per_mol}</td>
                  <td className="px-4 py-3">{result.interpretation}</td>
                  <td className="px-4 py-3 font-mono text-xs">{result.structure_id}</td>
                  <td className="px-4 py-3 font-mono text-xs">{result.runner}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : mutationLibrary ? (
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-200 text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase text-slate-500">
              <tr>
                <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">Variant</th>
                <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">Mutation</th>
                <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">Score</th>
                <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">Member scores</th>
                <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">Risk</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-slate-700">
              {mutationLibrary.variants.map((variant) => (
                <tr key={variant.variant_id}>
                  <td className="px-4 py-3 font-mono text-xs text-slate-950">{variant.variant_id}</td>
                  <td className="px-4 py-3 font-mono text-slate-950">{variant.mutation_string}</td>
                  <td className="px-4 py-3">{variant.score}</td>
                  <td className="px-4 py-3">
                    <MemberScoreList memberScores={variant.member_scores} />
                  </td>
                  <td className="px-4 py-3 text-xs">{variant.risk_flags.join(", ") || "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : candidates.length > 0 ? (
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-200 text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase text-slate-500">
              <tr>
                <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">Position</th>
                <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">WT</th>
                <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">Category</th>
                <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">Score</th>
                <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">Scored suggestions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-slate-700">
              {candidates.map((candidate) => (
                <tr key={`${candidate.query_position}-${candidate.wildtype_residue}`}>
                  <td className="px-4 py-3 font-medium text-slate-950">{candidate.query_position}</td>
                  <td className="px-4 py-3 font-mono">{candidate.wildtype_residue}</td>
                  <td className="px-4 py-3">{candidate.conservation_category}</td>
                  <td className="px-4 py-3">{candidate.priority_score}</td>
                  <td className="min-w-96 px-4 py-3">
                    <ScoredSuggestionList
                      disabled
                      fallbackMutations={candidate.suggested_mutations}
                      onRunRosettaDdg={() => undefined}
                      runningMutation={null}
                      suggestions={candidate.scored_suggestions}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : sites.length > 0 ? (
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-200 text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase text-slate-500">
              <tr>
                <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">Position</th>
                <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">WT</th>
                <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">Entropy</th>
                <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">WT frequency</th>
                <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">Category</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-slate-700">
              {sites.map((site) => (
                <tr key={`${site.query_position}-${site.wildtype_residue}`}>
                  <td className="px-4 py-3 font-medium text-slate-950">{site.query_position}</td>
                  <td className="px-4 py-3 font-mono">{site.wildtype_residue}</td>
                  <td className="px-4 py-3">{site.shannon_entropy}</td>
                  <td className="px-4 py-3">{site.wildtype_frequency}</td>
                  <td className="px-4 py-3">
                    <span className="rounded bg-slate-100 px-2 py-1 text-xs font-medium text-slate-700">
                      {site.conservation_category}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <pre className="max-h-96 overflow-auto whitespace-pre-wrap p-4 font-mono text-xs text-slate-800">
          {content.content_text ?? JSON.stringify(content.content_json, null, 2)}
        </pre>
      )}
    </section>
  );
}

function StatusPill({ value }: { value: string }) {
  return (
    <span className="rounded bg-slate-100 px-2 py-1 text-xs font-medium text-slate-700">
      {value}
    </span>
  );
}

function RunnerBadge({ label }: { label: ArtifactRunnerLabel }) {
  const modeClassName = label.mode === "real"
    ? "border-emerald-200 bg-emerald-50 text-emerald-700"
    : label.mode === "fallback"
      ? "border-amber-200 bg-amber-50 text-amber-700"
      : "border-slate-200 bg-slate-50 text-slate-700";
  return (
    <div className="flex flex-wrap items-center gap-2 text-xs">
      <span className={`rounded border px-2 py-1 font-mono ${modeClassName}`}>
        {label.text}
      </span>
      {label.warning ? <span className="text-amber-700">{label.warning}</span> : null}
    </div>
  );
}

function HomologDiagnosticsStrip({ diagnostics }: { diagnostics: HomologDiagnosticsView }) {
  const stages = [
    { label: "Fetched", value: diagnostics.candidate_count },
    { label: "Scored", value: diagnostics.scored_count },
    { label: "Identity pass", value: diagnostics.passed_identity_count },
    { label: "Coverage pass", value: diagnostics.passed_coverage_count },
    { label: "Returned", value: diagnostics.returned_count }
  ];

  return (
    <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-slate-600">
      {stages.map((stage) => (
        <span
          className="rounded border border-slate-200 bg-slate-50 px-2 py-1"
          key={stage.label}
          title={diagnostics.summary}
        >
          {stage.label}: <span className="font-mono text-slate-950">{stage.value}</span>
        </span>
      ))}
      <span className="rounded border border-slate-200 bg-white px-2 py-1">
        Identity filtered: <span className="font-mono text-slate-950">{diagnostics.filtered_identity_count}</span>
      </span>
      <span className="rounded border border-slate-200 bg-white px-2 py-1">
        Coverage filtered: <span className="font-mono text-slate-950">{diagnostics.filtered_coverage_count}</span>
      </span>
      <span className="rounded border border-slate-200 bg-white px-2 py-1">
        Duplicates: <span className="font-mono text-slate-950">{diagnostics.duplicate_count}</span>
      </span>
    </div>
  );
}

function MsaRecordTable({ records }: { records: MsaRecordView[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full divide-y divide-slate-200 text-left text-sm">
        <thead className="bg-slate-50 text-xs uppercase text-slate-500">
          <tr>
            <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">Identifier</th>
            <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">Length</th>
            <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">Gaps</th>
            <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">Aligned sequence</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100 text-slate-700">
          {records.map((record) => (
            <tr key={record.identifier}>
              <td className="px-4 py-3 font-mono text-xs text-slate-950">{record.identifier}</td>
              <td className="px-4 py-3 font-mono text-xs">{record.sequence_length}</td>
              <td className="px-4 py-3 font-mono text-xs">{record.gap_count}</td>
              <td className="max-w-xl truncate px-4 py-3 font-mono text-xs" title={record.aligned_sequence}>
                {record.aligned_sequence}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ScoredSuggestionList({
  disabled,
  fallbackMutations,
  onRunRosettaDdg,
  runningMutation,
  suggestions
}: {
  disabled: boolean;
  fallbackMutations: string[];
  onRunRosettaDdg: (mutation: string) => void;
  runningMutation: string | null;
  suggestions: ScoredMutationSuggestionView[];
}) {
  if (suggestions.length > 0) {
    return (
      <div className="grid gap-2">
        {suggestions.map((suggestion) => (
          <div className="rounded-md border border-slate-200 bg-slate-50 p-3" key={suggestion.mutation_string}>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <p className="font-mono text-sm font-semibold text-slate-950">{suggestion.mutation_string}</p>
                <p className="mt-1 text-xs text-slate-500">Score {suggestion.total_score}</p>
              </div>
              <button
                className="rounded-md border border-slate-300 bg-white px-2 py-1 font-mono text-xs font-medium text-slate-800 disabled:cursor-not-allowed disabled:text-slate-400"
                disabled={disabled}
                onClick={() => onRunRosettaDdg(suggestion.mutation_string)}
                type="button"
              >
                {runningMutation === suggestion.mutation_string ? "Queueing..." : "Run ddG"}
              </button>
            </div>
            <RiskTags risks={suggestion.risk_summary} />
            <ScoreComponents components={suggestion.components} />
          </div>
        ))}
      </div>
    );
  }

  if (fallbackMutations.length === 0) {
    return <span>-</span>;
  }

  return (
    <div className="flex flex-wrap gap-2">
      {fallbackMutations.map((mutation) => (
        <button
          className="rounded-md border border-slate-300 bg-white px-2 py-1 font-mono text-xs font-medium text-slate-800 disabled:cursor-not-allowed disabled:text-slate-400"
          disabled={disabled}
          key={mutation}
          onClick={() => onRunRosettaDdg(mutation)}
          type="button"
        >
          {runningMutation === mutation ? "Queueing..." : `Run ddG ${mutation}`}
        </button>
      ))}
    </div>
  );
}

function RiskTags({ risks }: { risks: string[] }) {
  if (risks.length === 0) {
    return <p className="mt-2 text-xs text-slate-500">No scoring risks flagged</p>;
  }
  return (
    <div className="mt-2 flex flex-wrap gap-1">
      {risks.map((risk) => (
        <span className="rounded bg-amber-50 px-2 py-1 text-xs font-medium text-amber-700" key={risk}>
          {risk}
        </span>
      ))}
    </div>
  );
}

function ScoreComponents({ components }: { components: ScoredMutationSuggestionView["components"] }) {
  if (components.length === 0) {
    return null;
  }
  return (
    <dl className="mt-3 grid gap-2 sm:grid-cols-2">
      {components.map((component) => (
        <div className="rounded border border-slate-200 bg-white px-2 py-2" key={component.name}>
          <dt className="text-xs font-medium text-slate-500">{component.name}</dt>
          <dd className="mt-1 text-xs text-slate-700">
            value {component.value} x weight {component.weight} = {component.contribution}
          </dd>
        </div>
      ))}
    </dl>
  );
}

function MemberScoreList({
  memberScores
}: {
  memberScores: Array<{ mutation_string: string; total_score: number | string }>;
}) {
  if (memberScores.length === 0) {
    return <span className="text-xs text-slate-500">-</span>;
  }
  return (
    <div className="flex flex-wrap gap-1">
      {memberScores.map((memberScore) => (
        <span
          className="rounded bg-emerald-50 px-2 py-1 font-mono text-xs font-medium text-emerald-700"
          key={`${memberScore.mutation_string}-${memberScore.total_score}`}
        >
          {memberScore.mutation_string}: {memberScore.total_score}
        </span>
      ))}
    </div>
  );
}
