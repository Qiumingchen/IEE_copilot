import AnalysisClient from "./AnalysisClient";

type EnzymeAnalysisPageProps = {
  params: Promise<{
    id: string;
  }>;
  searchParams?: Promise<{
    structure_id?: string;
  }>;
};

export default async function EnzymeAnalysisPage({ params, searchParams }: EnzymeAnalysisPageProps) {
  const { id } = await params;
  const resolvedSearchParams = searchParams ? await searchParams : {};

  return <AnalysisClient enzymeId={id} initialStructureId={resolvedSearchParams.structure_id ?? ""} />;
}
