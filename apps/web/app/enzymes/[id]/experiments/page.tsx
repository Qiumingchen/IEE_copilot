import ExperimentImportClient from "./ExperimentImportClient";

type ExperimentImportPageProps = {
  params: Promise<{
    id: string;
  }>;
};

export default async function ExperimentImportPage({ params }: ExperimentImportPageProps) {
  const { id } = await params;

  return <ExperimentImportClient enzymeId={id} />;
}
