const dashboardCards = [
  {
    title: "Projects",
    value: "2 modules",
    detail: "Anthraquinone glycosyltransferases and mature microbial transglutaminases."
  },
  {
    title: "Recent searches",
    value: "Ready",
    detail: "Search by name, EC number, organism, UniProt ID, or PDB ID."
  },
  {
    title: "Analysis jobs",
    value: "Queue",
    detail: "Family profiling, conservation, and structure-aware jobs will surface here."
  }
];

export default function DashboardPage() {
  return (
    <main className="mx-auto max-w-6xl px-6 py-8">
      <header className="mb-8 border-b border-slate-200 pb-6">
        <div>
          <h1 className="text-2xl font-semibold tracking-normal text-slate-950">IEE-Copilot</h1>
          <p className="mt-1 text-sm text-slate-600">Industrial enzyme engineering workbench</p>
        </div>
      </header>

      <section className="grid gap-4 md:grid-cols-3">
        {dashboardCards.map((card) => (
          <article key={card.title} className="rounded-md border border-slate-200 bg-white p-5 shadow-sm">
            <p className="text-xs font-medium uppercase text-slate-500">{card.title}</p>
            <h2 className="mt-3 text-lg font-semibold text-slate-950">{card.value}</h2>
            <p className="mt-2 text-sm leading-6 text-slate-600">{card.detail}</p>
          </article>
        ))}
      </section>

      <section className="mt-6 rounded-md border border-slate-200 bg-white p-5 shadow-sm">
        <h2 className="text-base font-semibold text-slate-950">Workbench status</h2>
        <div className="mt-4 grid gap-3 text-sm text-slate-700 md:grid-cols-3">
          <div>
            <p className="font-medium text-slate-950">Search</p>
            <p className="mt-1 text-slate-600">API boundary prepared for enzyme lookup.</p>
          </div>
          <div>
            <p className="font-medium text-slate-950">Structure input</p>
            <p className="mt-1 text-slate-600">PDB and CIF upload is available from enzyme detail records.</p>
          </div>
          <div>
            <p className="font-medium text-slate-950">Jobs</p>
            <p className="mt-1 text-slate-600">Queued analysis status has a detail route.</p>
          </div>
        </div>
      </section>
    </main>
  );
}
