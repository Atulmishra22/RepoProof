import Link from "next/link";

export default function Home() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-zinc-950 text-zinc-100 font-sans antialiased selection:bg-blue-600/30 selection:text-blue-200 overflow-hidden relative">
      {/* Background glow effects */}
      <div className="absolute top-1/4 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[500px] h-[500px] bg-gradient-to-tr from-blue-500/10 to-indigo-500/10 rounded-full blur-[120px] pointer-events-none" />
      <div className="absolute bottom-1/4 left-1/3 w-[300px] h-[300px] bg-gradient-to-br from-cyan-500/5 to-purple-500/5 rounded-full blur-[100px] pointer-events-none" />

      <main className="relative z-10 flex w-full max-w-4xl flex-col items-center text-center px-6 md:px-8">
        {/* Badge */}
        <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full border border-blue-500/20 bg-blue-950/20 text-xs font-semibold text-blue-400 mb-8">
          <span className="h-1.5 w-1.5 rounded-full bg-blue-400 animate-pulse" />
          <span>Platform Status: Live</span>
        </div>

        {/* Title */}
        <h1 className="text-4xl md:text-6xl font-extrabold tracking-tight text-white mb-6 leading-tight">
          Welcome to{" "}
          <span className="bg-clip-text text-transparent bg-gradient-to-r from-blue-400 via-indigo-400 to-cyan-400">
            RepoProof
          </span>
        </h1>

        {/* Description */}
        <p className="max-w-xl text-zinc-400 text-sm md:text-base leading-relaxed mb-10">
          Advanced Repository Intelligence Platform. Clone public GitHub repositories, construct flat structural trees, and automatically extract framework-level heuristic facts using high-performance checkpointers.
        </p>

        {/* Enter Button */}
        <div className="flex flex-col sm:flex-row gap-4 items-center justify-center w-full">
          <Link
            className="flex h-12 w-full sm:w-auto items-center justify-center rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 px-8 text-sm font-bold text-white shadow-lg shadow-blue-900/30 hover:from-blue-500 hover:to-indigo-500 transition-all duration-200"
            href="/dashboard"
          >
            Launch Dashboard →
          </Link>
        </div>

        {/* Features preview container */}
        <div className="mt-20 grid grid-cols-1 sm:grid-cols-3 gap-6 w-full text-left">
          <div className="rounded-xl border border-zinc-900 bg-zinc-900/20 p-6 backdrop-blur-sm">
            <h3 className="text-sm font-semibold text-zinc-200 mb-2 flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-cyan-500" />
              File Tree Mapping
            </h3>
            <p className="text-xs text-zinc-500 leading-relaxed">
              Parse directories instantly to map absolute paths, sizes, and extensions into optimized structural metadata.
            </p>
          </div>
          <div className="rounded-xl border border-zinc-900 bg-zinc-900/20 p-6 backdrop-blur-sm">
            <h3 className="text-sm font-semibold text-zinc-200 mb-2 flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-indigo-500" />
              Heuristic Fact Scanner
            </h3>
            <p className="text-xs text-zinc-500 leading-relaxed">
              Scan config rules and package files to discover dependencies and tech stacks without API latency.
            </p>
          </div>
          <div className="rounded-xl border border-zinc-900 bg-zinc-900/20 p-6 backdrop-blur-sm">
            <h3 className="text-sm font-semibold text-zinc-200 mb-2 flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-purple-500" />
              LangGraph State Pools
            </h3>
            <p className="text-xs text-zinc-500 leading-relaxed">
              Track task nodes and resume execution steps gracefully using transactional PostgreSQL checkpointers.
            </p>
          </div>
        </div>
      </main>
    </div>
  );
}


