import Link from "next/link";

type EnzymeAnalysisPageProps = {
  params: Promise<{
    id: string;
  }>;
};

const analysisModules = [
  {
    title: "Homolog sequences",
    artifactType: "homolog_sequences",
    status: "Worker artifact",
    metric: "identity / coverage"
  },
  {
    title: "MSA",
    artifactType: "msa",
    status: "Worker artifact",
    metric: "aligned FASTA"
  },
  {
    title: "Conservation",
    artifactType: "conservation_profile",
    status: "Worker artifact",
    metric: "entropy / WT frequency"
  }
];

const conservationPreview = [
  {
    position: "1",
    residue: "A",
    entropy: "0.000",
    frequency: "1.00",
    category: "highly_conserved"
  },
  {
    position: "2",
    residue: "C",
    entropy: "0.811",
    frequency: "0.75",
    category: "moderately_conserved"
  },
  {
    position: "3",
    residue: "D",
    entropy: "0.811",
    frequency: "0.75",
    category: "moderately_conserved"
  }
];

export default async function EnzymeAnalysisPage({ params }: EnzymeAnalysisPageProps) {
  const { id } = await params;

  return (
    <main className="mx-auto max-w-6xl px-6 py-8">
      <header className="border-b border-slate-200 pb-6">
        <p className="text-sm font-medium text-slate-500">MSA / Conservation</p>
        <div className="mt-2 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold text-slate-950">Evolutionary analysis</h1>
            <p className="mt-2 text-sm text-slate-600">Entry id: {id}</p>
          </div>
          <Link
            className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-800"
            href={`/enzymes/${id}`}
          >
            Back to enzyme
          </Link>
        </div>
      </header>

      <section className="mt-6 grid gap-3 md:grid-cols-3">
        {analysisModules.map((item) => (
          <article className="rounded-md border border-slate-200 bg-white p-4" key={item.artifactType}>
            <div className="flex items-start justify-between gap-3">
              <div>
                <h2 className="text-base font-semibold text-slate-950">{item.title}</h2>
                <p className="mt-1 text-sm text-slate-600">{item.metric}</p>
              </div>
              <span className="rounded bg-slate-100 px-2 py-1 text-xs font-medium text-slate-700">
                {item.status}
              </span>
            </div>
            <dl className="mt-4">
              <dt className="text-xs font-medium uppercase text-slate-500">Artifact</dt>
              <dd className="mt-1 break-words font-mono text-sm text-slate-950">{item.artifactType}</dd>
            </dl>
          </article>
        ))}
      </section>

      <section className="mt-8 overflow-hidden rounded-md border border-slate-200 bg-white">
        <div className="border-b border-slate-200 px-4 py-3">
          <h2 className="text-base font-semibold text-slate-950">Conservation profile</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-200 text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase text-slate-500">
              <tr>
                <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">
                  Position
                </th>
                <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">
                  WT
                </th>
                <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">
                  Entropy
                </th>
                <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">
                  WT frequency
                </th>
                <th className="whitespace-nowrap px-4 py-3 font-medium" scope="col">
                  Category
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-slate-700">
              {conservationPreview.map((site) => (
                <tr key={site.position}>
                  <td className="px-4 py-3 font-medium text-slate-950">{site.position}</td>
                  <td className="px-4 py-3 font-mono">{site.residue}</td>
                  <td className="px-4 py-3">{site.entropy}</td>
                  <td className="px-4 py-3">{site.frequency}</td>
                  <td className="px-4 py-3">
                    <span className="rounded bg-slate-100 px-2 py-1 text-xs font-medium text-slate-700">
                      {site.category}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  );
}
