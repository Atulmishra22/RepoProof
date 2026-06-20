import Image from "next/image";
import Link from "next/link";

export default function Home() {
  return (
    <div className="flex flex-col flex-1 items-center justify-center bg-zinc-50 font-sans dark:bg-black">
      <main className="flex flex-1 w-full max-w-3xl flex-col items-center justify-between py-32 px-16 bg-white dark:bg-black sm:items-start">
        <Image
          className="dark:invert"
          src="/next.svg"
          alt="Next.js logo"
          width={100}
          height={20}
          priority
        />
        <div className="flex flex-col items-center gap-6 text-center sm:items-start sm:text-left mt-8">
          <h1 className="max-w-md text-4xl font-bold leading-tight tracking-tight text-black dark:text-zinc-50">
            Welcome to RepoProof
          </h1>
          <p className="max-w-md text-lg leading-8 text-zinc-600 dark:text-zinc-400">
            GitHub Repository Intelligence Platform. Analyze repositories, parse code architectures, and generate technical summaries.
          </p>
        </div>
        <div className="flex flex-col gap-4 text-base font-medium sm:flex-row mt-8 w-full">
          <Link
            className="flex h-12 w-full items-center justify-center rounded-full bg-blue-600 px-6 text-white font-semibold shadow transition-colors hover:bg-blue-700 md:w-[200px]"
            href="/dashboard"
          >
            Go to Dashboard →
          </Link>
        </div>
      </main>
    </div>
  );
}

