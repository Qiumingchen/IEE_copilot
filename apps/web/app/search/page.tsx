export default function SearchPage() {
  return (
    <main className="mx-auto max-w-5xl px-6 py-8">
      <header className="border-b border-slate-200 pb-6">
        <p className="text-sm font-medium text-slate-500">Workbench search</p>
        <h1 className="mt-2 text-2xl font-semibold text-slate-950">Search enzyme</h1>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">
          Search by enzyme name, EC number, organism, UniProt ID, or PDB ID.
        </p>
      </header>

      <form className="mt-6 grid gap-3 sm:grid-cols-[1fr_auto]">
        <label className="grid gap-1 text-sm font-medium text-slate-700">
          Query
          <input
            className="min-w-0 rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-950 outline-none focus:border-slate-500"
            defaultValue="microbial transglutaminase"
            name="query"
          />
        </label>
        <button className="self-end rounded-md bg-slate-950 px-4 py-2 text-sm font-medium text-white" type="submit">
          Search
        </button>
      </form>

      <section className="mt-8 border-t border-slate-200 pt-6">
        <h2 className="text-base font-semibold text-slate-950">PDB upload</h2>
        <p className="mt-2 text-sm leading-6 text-slate-600">
          Apo and enzyme-substrate complex upload enters this workflow after the skeleton is stable.
        </p>
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <div className="rounded-md border border-slate-200 p-4">
            <p className="text-sm font-medium text-slate-950">Apo structure</p>
            <p className="mt-1 text-sm text-slate-600">Upload placeholder</p>
          </div>
          <div className="rounded-md border border-slate-200 p-4">
            <p className="text-sm font-medium text-slate-950">Enzyme-substrate complex</p>
            <p className="mt-1 text-sm text-slate-600">Upload placeholder</p>
          </div>
        </div>
      </section>
    </main>
  );
}
