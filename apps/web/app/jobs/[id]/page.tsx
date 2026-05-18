type JobDetailPageProps = {
  params: Promise<{
    id: string;
  }>;
};

export default async function JobDetailPage({ params }: JobDetailPageProps) {
  const { id } = await params;

  return (
    <main className="mx-auto max-w-4xl px-6 py-8">
      <header className="border-b border-slate-200 pb-6">
        <p className="text-sm font-medium text-slate-500">Analysis queue</p>
        <h1 className="mt-2 text-2xl font-semibold text-slate-950">Analysis job</h1>
        <p className="mt-2 text-sm text-slate-600">Job id: {id}</p>
      </header>

      <section className="mt-6 rounded-md border border-slate-200 bg-white p-5 shadow-sm">
        <h2 className="text-base font-semibold text-slate-950">Status</h2>
        <p className="mt-2 text-sm leading-6 text-slate-600">
          Queued, running, finished, failed, and artifact list states are shown here.
        </p>
      </section>
    </main>
  );
}
