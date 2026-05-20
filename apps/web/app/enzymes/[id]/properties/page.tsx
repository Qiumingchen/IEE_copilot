import PropertyDashboardClient from "./PropertyDashboardClient";

type PropertyDashboardPageProps = {
  params: Promise<{
    id: string;
  }>;
};

export default async function PropertyDashboardPage({ params }: PropertyDashboardPageProps) {
  const { id } = await params;

  return <PropertyDashboardClient enzymeId={id} />;
}
