import EnzymeDetailClient from "./EnzymeDetailClient";

type EnzymeDetailPageProps = {
  params: Promise<{
    id: string;
  }>;
};

export default async function EnzymeDetailPage({ params }: EnzymeDetailPageProps) {
  const { id } = await params;

  return <EnzymeDetailClient enzymeId={id} />;
}
