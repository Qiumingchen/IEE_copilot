import StructureAnalysisClient from "./StructureAnalysisClient";

type StructureAnalysisPageProps = {
  params: Promise<{
    id: string;
  }>;
  searchParams: Promise<{
    structure_id?: string;
  }>;
};

export default async function StructureAnalysisPage({ params, searchParams }: StructureAnalysisPageProps) {
  const { id } = await params;
  const resolvedSearchParams = await searchParams;

  return <StructureAnalysisClient enzymeId={id} initialStructureId={resolvedSearchParams.structure_id ?? ""} />;
}
