type EnzymeDetailPageProps = {
  params: Promise<{
    id: string;
  }>;
};

export default async function EnzymeDetailPage({ params }: EnzymeDetailPageProps) {
  const { id } = await params;

  return (
    <main className="mx-auto max-w-5xl px-6 py-8">
      <header className="border-b border-slate-200 pb-6">
        <p className="text-sm font-medium text-slate-500">Enzyme record</p>
        <h1 className="mt-2 text-2xl font-semibold text-slate-950">Enzyme detail</h1>
        <p className="mt-2 text-sm text-slate-600">Entry id: {id}</p>
      </header>

      <section className="mt-6 rounded-md border border-slate-200 bg-white p-5 shadow-sm">
        <h2 className="text-base font-semibold text-slate-950">Summary</h2>
        <p className="mt-2 text-sm leading-6 text-slate-600">
          Sequence, structure source, cache timestamp, reported properties, and analysis job status render here.
        </p>
      </section>
    </main>
  );
}
