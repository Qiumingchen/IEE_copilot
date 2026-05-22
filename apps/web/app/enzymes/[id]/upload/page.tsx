import EnzymeDetailClient from "../EnzymeDetailClient";

type EnzymeUploadPageProps = {
  params: Promise<{
    id: string;
  }>;
};

export default async function EnzymeUploadPage({ params }: EnzymeUploadPageProps) {
  const { id } = await params;

  return <EnzymeDetailClient enzymeId={id} mode="upload" />;
}
