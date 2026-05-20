import StructureAnalysisClient from "./StructureAnalysisClient";

type StructureAnalysisPageProps = {
  params: Promise<{
    id: string;
  }>;
};

export default async function StructureAnalysisPage({ params }: StructureAnalysisPageProps) {
  const { id } = await params;

  return <StructureAnalysisClient enzymeId={id} />;
}
