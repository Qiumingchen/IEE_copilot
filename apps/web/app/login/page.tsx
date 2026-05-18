export default function LoginPage() {
  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center px-6 py-10">
      <div className="border-b border-slate-200 pb-5">
        <p className="text-sm font-medium text-slate-500">IEE-Copilot</p>
        <h1 className="mt-2 text-2xl font-semibold text-slate-950">Sign in</h1>
        <p className="mt-2 text-sm text-slate-600">Development seed account: demo@iee.local</p>
      </div>

      <form className="mt-6 grid gap-4">
        <label className="grid gap-1 text-sm font-medium text-slate-700">
          Email
          <input
            className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-950 outline-none focus:border-slate-500"
            name="email"
            placeholder="demo@iee.local"
            type="email"
          />
        </label>
        <label className="grid gap-1 text-sm font-medium text-slate-700">
          Password
          <input
            className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-950 outline-none focus:border-slate-500"
            name="password"
            placeholder="Seed account password"
            type="password"
          />
        </label>
        <button className="rounded-md bg-slate-950 px-4 py-2 text-sm font-medium text-white" type="button">
          Sign in
        </button>
      </form>
    </main>
  );
}
