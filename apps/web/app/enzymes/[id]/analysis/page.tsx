import AnalysisClient from "./AnalysisClient";

type EnzymeAnalysisPageProps = {
  params: Promise<{
    id: string;
  }>;
};

export default async function EnzymeAnalysisPage({ params }: EnzymeAnalysisPageProps) {
  const { id } = await params;

  return <AnalysisClient enzymeId={id} />;
}
