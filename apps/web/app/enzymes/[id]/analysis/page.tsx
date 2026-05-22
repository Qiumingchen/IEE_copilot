import AnalysisClient from "./AnalysisClient";
import { normalizeAnalysisFocus } from "./analysis-utils";

type EnzymeAnalysisPageProps = {
  params: Promise<{
    id: string;
  }>;
  searchParams?: Promise<{
    focus?: string;
    structure_id?: string;
  }>;
};

export default async function EnzymeAnalysisPage({ params, searchParams }: EnzymeAnalysisPageProps) {
  const { id } = await params;
  const resolvedSearchParams = searchParams ? await searchParams : {};

  return (
    <AnalysisClient
      enzymeId={id}
      initialFocus={normalizeAnalysisFocus(resolvedSearchParams.focus)}
      initialStructureId={resolvedSearchParams.structure_id ?? ""}
    />
  );
}
