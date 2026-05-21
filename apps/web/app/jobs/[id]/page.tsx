import JobDetailClient from "./JobDetailClient";

type JobDetailPageProps = {
  params: Promise<{
    id: string;
  }>;
};

export default async function JobDetailPage({ params }: JobDetailPageProps) {
  const { id } = await params;

  return <JobDetailClient jobId={id} />;
}
