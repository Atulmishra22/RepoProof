"use client";

import React, { useState, useEffect } from "react";

interface Repository {
  id: string;
  github_url: string;
  github_repo_id: number;
  owner: string;
  name: string;
  default_branch: string;
  primary_language: string | null;
  languages: Record<string, number>;
  star_count: number;
  analysis_status: string;
  last_analyzed_at: string | null;
  created_at: string;
  updated_at: string;
}

interface Profile {
  username: string;
  name: string;
  email: string;
  bio: string;
  avatar_url: string;
  github_id: number | null;
  readme: string | null;
}

export default function DashboardPage() {
  const [usernameInput, setUsernameInput] = useState("");
  const [currentUsername, setCurrentUsername] = useState("Atulmishra22");
  const [profile, setProfile] = useState<Profile | null>(null);
  const [repositories, setRepositories] = useState<Repository[]>([]);
  const [loading, setLoading] = useState(false);
  const [ingesting, setIngesting] = useState(false);
  const [statusMessage, setStatusMessage] = useState("");
  const [connectionError, setConnectionError] = useState<string | null>(null);
  const [activeJobs, setActiveJobs] = useState<Record<string, { jobId: string; currentNode: string | null }>>({});

  const fetchUserData = async (username: string) => {
    setLoading(true);
    setConnectionError(null);
    try {
      const response = await fetch(`http://127.0.0.1:8000/api/v1/repositories?username=${username}`);
      if (response.ok) {
        const data = await response.json();
        setRepositories(data.repositories || []);
        setProfile(data.profile || null);
      } else {
        setConnectionError(`Backend responded with status ${response.status}. Please check backend logs.`);
      }
    } catch (error) {
      console.error("Error fetching data:", error);
      setConnectionError("Failed to fetch data from backend. Make sure the FastAPI container is running inside WSL.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchUserData(currentUsername);
  }, [currentUsername]);

  const handleAnalyze = async (repoId: string) => {
    try {
      const response = await fetch(`http://127.0.0.1:8000/api/v1/repositories/${repoId}/analyze`, {
        method: "POST",
      });
      if (response.ok) {
        const data = await response.json();
        const jobId = data.job_id;
        
        // Add to active jobs
        setActiveJobs(prev => ({
          ...prev,
          [repoId]: { jobId, currentNode: "queued" }
        }));
        
        // Optimistically update repo status in local state
        setRepositories(prev => 
          prev.map(r => r.id === repoId ? { ...r, analysis_status: "analyzing" } : r)
        );
      } else {
        const errData = await response.json();
        alert(`Failed to start analysis: ${errData.detail || "Unknown error"}`);
      }
    } catch (err) {
      console.error("Error triggering analysis:", err);
      alert("Failed to connect to backend to start analysis.");
    }
  };

  // Auto-recover jobs on mount/refresh if database repos are already analyzing
  useEffect(() => {
    const fetchActiveJobs = async () => {
      const analyzingRepos = repositories.filter(
        r => r.analysis_status === "analyzing" && !activeJobs[r.id]
      );
      if (analyzingRepos.length === 0) return;

      for (const repo of analyzingRepos) {
        try {
          const response = await fetch(`http://127.0.0.1:8000/api/v1/repositories/${repo.id}/analyze`, {
            method: "POST",
          });
          if (response.ok) {
            const data = await response.json();
            if (data.job_id) {
              setActiveJobs(prev => ({
                ...prev,
                [repo.id]: { jobId: data.job_id, currentNode: null }
              }));
            }
          }
        } catch (err) {
          console.error(`Error auto-recovering job for repo ${repo.name}:`, err);
        }
      }
    };
    fetchActiveJobs();
  }, [repositories, activeJobs]);

  // Poll active jobs status from the backend
  useEffect(() => {
    const activeRepoIds = Object.keys(activeJobs);
    if (activeRepoIds.length === 0) return;

    const interval = setInterval(async () => {
      const updatedJobs = { ...activeJobs };
      let changed = false;
      let finishedAny = false;

      await Promise.all(
        activeRepoIds.map(async (repoId) => {
          const { jobId } = activeJobs[repoId];
          try {
            const res = await fetch(`http://127.0.0.1:8000/api/v1/repositories/${repoId}/analysis/${jobId}`);
            if (res.ok) {
              const data = await res.json();
              const status = data.status; // e.g. queued, running, complete, failed
              const currentNode = data.current_node;

              if (status === "complete" || status === "failed" || status === "timed_out") {
                delete updatedJobs[repoId];
                changed = true;
                finishedAny = true;
              } else {
                if (updatedJobs[repoId].currentNode !== currentNode) {
                  updatedJobs[repoId] = { jobId, currentNode };
                  changed = true;
                }
              }
            }
          } catch (err) {
            console.error(`Error polling job ${jobId}:`, err);
          }
        })
      );

      if (changed) {
        setActiveJobs(updatedJobs);
      }
      if (finishedAny) {
        fetchUserData(currentUsername);
      }
    }, 2000);

    return () => clearInterval(interval);
  }, [activeJobs, currentUsername]);

  const handleIngest = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!usernameInput.trim()) return;

    setIngesting(true);
    setStatusMessage("Triggering ingestion background task...");
    setConnectionError(null);
    try {
      const response = await fetch("http://127.0.0.1:8000/api/v1/users/ingest", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ username: usernameInput.trim() }),
      });

      if (response.ok) {
        setStatusMessage(`Ingestion task started! Fetching data for "${usernameInput.trim()}"...`);
        const targetUser = usernameInput.trim();
        setCurrentUsername(targetUser);
        
        // Poll for updates a few times
        let attempts = 0;
        const interval = setInterval(async () => {
          attempts++;
          await fetchUserData(targetUser);
          if (attempts >= 4) {
            clearInterval(interval);
            setIngesting(false);
            setStatusMessage("");
          }
        }, 3000); // Poll every 3 seconds for 12 seconds total
      } else {
        const errorData = await response.json();
        setStatusMessage(`Error: ${errorData.detail || "Failed to trigger ingestion"}`);
        setIngesting(false);
      }
    } catch (error) {
      setConnectionError("Connection error while triggering ingestion. Please check if the API is offline.");
      setIngesting(false);
    }
  };

  // Helper to format languages byte sizes to percentages
  const renderLanguageBar = (languages: Record<string, number>) => {
    const totalBytes = Object.values(languages).reduce((a, b) => a + b, 0);
    if (totalBytes === 0) return null;

    // Sort languages by size
    const sortedLangs = Object.entries(languages).sort((a, b) => b[1] - a[1]);

    return (
      <div className="mt-3">
        <div className="flex h-2 w-full overflow-hidden rounded-full bg-zinc-800">
          {sortedLangs.map(([lang, bytes], idx) => {
            const percentage = (bytes / totalBytes) * 100;
            // Palette tailored to look modern & premium
            const colors = [
              "bg-cyan-500 shadow-[0_0_8px_rgba(6,182,212,0.5)]", 
              "bg-indigo-500 shadow-[0_0_8px_rgba(99,102,241,0.5)]", 
              "bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)]", 
              "bg-amber-500 shadow-[0_0_8px_rgba(245,158,11,0.5)]", 
              "bg-rose-500 shadow-[0_0_8px_rgba(244,63,94,0.5)]", 
              "bg-violet-500 shadow-[0_0_8px_rgba(139,92,246,0.5)]"
            ];
            const colorClass = colors[idx % colors.length];
            return (
              <div
                key={lang}
                className={`h-full transition-all duration-300 ${colorClass}`}
                style={{ width: `${percentage}%` }}
                title={`${lang}: ${percentage.toFixed(1)}%`}
              />
            );
          })}
        </div>
        <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-xs text-zinc-400">
          {sortedLangs.slice(0, 3).map(([lang, bytes]) => {
            const percentage = (bytes / totalBytes) * 100;
            return (
              <span key={lang} className="flex items-center gap-1.5">
                <span className="h-1.5 w-1.5 rounded-full bg-zinc-500" />
                <span>{lang}</span>
                <span className="font-semibold text-zinc-300">
                  {percentage.toFixed(1)}%
                </span>
              </span>
            );
          })}
          {sortedLangs.length > 3 && (
            <span className="text-zinc-500">+{sortedLangs.length - 3} more</span>
          )}
        </div>
      </div>
    );
  };

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 font-sans antialiased selection:bg-blue-600/30 selection:text-blue-200">
      {/* Top Header */}
      <header className="sticky top-0 z-50 border-b border-zinc-900 bg-zinc-950/80 backdrop-blur-md">
        <div className="mx-auto flex max-w-7xl h-16 items-center justify-between px-4 sm:px-6 lg:px-8">
          <div className="flex items-center gap-4">
            <span className="text-xl font-bold tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-blue-400 via-indigo-400 to-cyan-400">
              RepoProof
            </span>
            <span className="rounded-full border border-blue-900/30 bg-blue-950/30 px-2.5 py-0.5 text-xs font-semibold text-blue-400">
              Repository Intelligence
            </span>
          </div>
          <div className="text-xs text-zinc-400 bg-zinc-900/60 border border-zinc-800 px-3 py-1.5 rounded-lg flex items-center gap-2">
            <span className="h-2 w-2 rounded-full bg-green-500 animate-pulse" />
            <span>Connected Profile: <strong className="text-zinc-200">{currentUsername}</strong></span>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
        
        {/* Connection/Backend Error Warning */}
        {connectionError && (
          <div className="mb-8 rounded-xl border border-red-900/50 bg-red-950/20 p-5 text-sm text-red-200 shadow-lg shadow-red-950/10">
            <div className="flex items-start gap-3">
              <svg className="h-5 w-5 text-red-400 mt-0.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
              <div>
                <h4 className="font-bold text-red-400">Backend Communication Failure</h4>
                <p className="mt-1 text-zinc-400">{connectionError}</p>
                <div className="mt-3 flex gap-3">
                  <button 
                    onClick={() => fetchUserData(currentUsername)}
                    className="rounded bg-red-900/50 hover:bg-red-900/80 border border-red-700/50 px-3 py-1 text-xs font-semibold text-red-200 transition-colors"
                  >
                    Retry Connection
                  </button>
                  <code className="text-zinc-500 select-all font-mono text-xs py-1">
                    wsl -d Ubuntu-24.04 -u root docker compose ps
                  </code>
                </div>
              </div>
            </div>
          </div>
        )}

        <div className="grid grid-cols-1 gap-8 lg:grid-cols-3">
          
          {/* Left Column: Form and Profile Metadata */}
          <div className="space-y-6 lg:col-span-1">
            {/* Input Ingest Card */}
            <div className="rounded-xl border border-zinc-900 bg-zinc-900/40 p-6 shadow-xl backdrop-blur-sm">
              <h2 className="text-md font-semibold text-zinc-200 mb-4 flex items-center gap-2">
                <svg className="h-4.5 w-4.5 text-blue-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
                </svg>
                Ingest GitHub Username
              </h2>
              <form onSubmit={handleIngest} className="space-y-4">
                <div>
                  <label htmlFor="username" className="block text-[10px] font-semibold uppercase tracking-wider text-zinc-500 mb-1">
                    GitHub Username
                  </label>
                  <input
                    type="text"
                    id="username"
                    placeholder="e.g. Atulmishra22"
                    value={usernameInput}
                    onChange={(e) => setUsernameInput(e.target.value)}
                    className="w-full rounded-lg border border-zinc-800 bg-zinc-950 px-3.5 py-2 text-sm text-zinc-200 placeholder-zinc-600 outline-none focus:border-blue-500/80 focus:ring-1 focus:ring-blue-500/20 transition-all"
                    disabled={ingesting}
                  />
                </div>
                <button
                  type="submit"
                  disabled={ingesting || !usernameInput.trim()}
                  className="w-full rounded-lg bg-gradient-to-r from-blue-600 to-indigo-600 py-2.5 text-sm font-semibold text-white shadow-lg shadow-blue-900/20 hover:from-blue-500 hover:to-indigo-500 focus:outline-none disabled:opacity-40 disabled:cursor-not-allowed transition-all"
                >
                  {ingesting ? "Ingesting Account..." : "Ingest Repositories"}
                </button>
              </form>

              {statusMessage && (
                <div className="mt-4 rounded-lg border border-zinc-800/80 bg-zinc-950/80 p-3 text-xs text-zinc-400 flex items-start gap-2.5">
                  <span className="flex h-2 w-2 rounded-full bg-blue-500 animate-ping mt-1" />
                  <span>{statusMessage}</span>
                </div>
              )}
            </div>

            {/* Profile Info Summary */}
            {loading && !profile ? (
              /* Profile Card Skeleton */
              <div className="rounded-xl border border-zinc-900 bg-zinc-900/20 p-6 animate-pulse space-y-4">
                <div className="h-24 w-24 rounded-full bg-zinc-800 mx-auto" />
                <div className="h-5 w-36 bg-zinc-800 rounded mx-auto" />
                <div className="h-3.5 w-24 bg-zinc-850 rounded mx-auto" />
                <div className="space-y-2 mt-4 pt-4 border-t border-zinc-900">
                  <div className="h-3 w-full bg-zinc-900 rounded" />
                  <div className="h-3 w-4/5 bg-zinc-900 rounded mx-auto" />
                </div>
              </div>
            ) : profile ? (
              <div className="rounded-xl border border-zinc-900 bg-zinc-900/40 p-6 shadow-xl backdrop-blur-sm">
                <div className="flex flex-col items-center text-center">
                  {profile.avatar_url ? (
                    <div className="relative group">
                      <div className="absolute -inset-0.5 rounded-full bg-gradient-to-tr from-blue-500 to-cyan-500 opacity-60 blur" />
                      <img
                        src={profile.avatar_url}
                        alt={`${profile.name || profile.username}'s avatar`}
                        className="relative h-24 w-24 rounded-full border-2 border-zinc-950 object-cover shadow-2xl"
                      />
                    </div>
                  ) : (
                    <div className="flex h-24 w-24 items-center justify-center rounded-full border border-zinc-800 bg-zinc-900 text-3xl font-bold">
                      {profile.username[0]?.toUpperCase()}
                    </div>
                  )}
                  <h3 className="mt-5 text-lg font-bold text-zinc-100">{profile.name || profile.username}</h3>
                  <a
                    href={`https://github.com/${profile.username}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-xs font-semibold text-cyan-400 hover:text-cyan-300 flex items-center gap-1.5 mt-1"
                  >
                    @{profile.username}
                    <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                    </svg>
                  </a>
                  {profile.bio && (
                    <p className="mt-3 text-xs text-zinc-400 leading-relaxed px-2">{profile.bio}</p>
                  )}
                </div>

                <div className="mt-6 border-t border-zinc-900/80 pt-4 text-xs space-y-2.5 text-zinc-500">
                  {profile.email && (
                    <div className="flex justify-between">
                      <span className="font-semibold">Email</span>
                      <span className="text-zinc-300 font-mono">{profile.email}</span>
                    </div>
                  )}
                  {profile.github_id && (
                    <div className="flex justify-between">
                      <span className="font-semibold">GitHub ID</span>
                      <span className="text-zinc-300 font-mono">{profile.github_id}</span>
                    </div>
                  )}
                </div>
              </div>
            ) : null}

            {/* Profile README Section */}
            {loading && !profile ? (
              <div className="rounded-xl border border-zinc-900 bg-zinc-900/20 p-6 animate-pulse space-y-3">
                <div className="h-4 w-28 bg-zinc-800 rounded" />
                <div className="h-32 bg-zinc-850 rounded" />
              </div>
            ) : profile?.readme ? (
              <div className="rounded-xl border border-zinc-900 bg-zinc-900/40 p-6 shadow-xl backdrop-blur-sm">
                <h3 className="text-xs font-bold uppercase tracking-wider text-zinc-500 mb-3 flex items-center gap-1.5">
                  <svg className="h-3.5 w-3.5 text-cyan-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                  </svg>
                  Profile Bio README
                </h3>
                <div className="max-h-80 overflow-y-auto rounded-lg bg-zinc-950 p-4 border border-zinc-900 font-mono text-[10px] leading-relaxed text-zinc-400 scrollbar-thin scrollbar-thumb-zinc-800">
                  <pre className="whitespace-pre-wrap">{profile.readme}</pre>
                </div>
              </div>
            ) : null}

          </div>

          {/* Right Column: Repositories List Grid */}
          <div className="lg:col-span-2 space-y-6">
            <div className="flex items-center justify-between border-b border-zinc-900 pb-4">
              <h2 className="text-lg font-bold tracking-tight text-zinc-200">
                Discovered Repositories
              </h2>
              <span className="rounded-full bg-zinc-900 px-3 py-1.5 text-xs font-semibold text-zinc-300 border border-zinc-800">
                {repositories.length} public projects
              </span>
            </div>

            {loading ? (
              /* Repositories Loading Skeleton */
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {[1, 2, 3, 4].map((id) => (
                  <div key={id} className="rounded-xl border border-zinc-900 bg-zinc-900/10 p-5 animate-pulse space-y-4">
                    <div className="flex justify-between items-center">
                      <div className="h-5 w-40 bg-zinc-800 rounded" />
                      <div className="h-4.5 w-16 bg-zinc-800 rounded-full" />
                    </div>
                    <div className="h-3 w-48 bg-zinc-850 rounded" />
                    <div className="h-2 w-full bg-zinc-900 rounded-full mt-4" />
                    <div className="flex justify-between items-center mt-2">
                      <div className="h-3.5 w-16 bg-zinc-900 rounded" />
                      <div className="h-3.5 w-12 bg-zinc-900 rounded" />
                    </div>
                  </div>
                ))}
              </div>
            ) : repositories.length === 0 ? (
              <div className="flex flex-col h-72 items-center justify-center rounded-xl border border-dashed border-zinc-800 bg-zinc-900/10 p-8 text-center">
                <svg className="h-12 w-12 text-zinc-600 mb-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />
                </svg>
                <h3 className="text-base font-semibold text-zinc-300">No Projects Found</h3>
                <p className="mt-1.5 text-xs text-zinc-500 max-w-xs mx-auto">Use the panel on the left to discover and import repositories from a public profile.</p>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {repositories.map((repo) => (
                  <div key={repo.id} className="group relative rounded-xl border border-zinc-900 bg-zinc-900/30 p-5 shadow-md hover:border-zinc-800 hover:bg-zinc-900/50 hover:shadow-lg hover:shadow-blue-950/5 transition-all duration-300 flex flex-col justify-between">
                    <div>
                      <div className="flex items-start justify-between gap-3">
                        <div className="space-y-1">
                          <h3 className="font-semibold text-zinc-100 group-hover:text-blue-400 transition-colors">
                            <a href={repo.github_url} target="_blank" rel="noopener noreferrer" className="flex items-center gap-1.5 break-all text-sm leading-snug">
                              {repo.name}
                              <svg className="h-3.5 w-3.5 opacity-0 group-hover:opacity-100 text-blue-400 transition-all transform translate-x-[-4px] group-hover:translate-x-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                              </svg>
                            </a>
                          </h3>
                          <p className="text-[10px] text-zinc-500 font-medium uppercase tracking-wider">Default branch: {repo.default_branch}</p>
                        </div>

                        {/* Status Badge */}
                        <span className={`inline-flex rounded-full border px-2 py-0.5 text-[9px] font-bold uppercase tracking-wider ${
                          repo.analysis_status === "complete" 
                            ? "bg-green-950/20 text-green-400 border-green-900/40"
                            : repo.analysis_status === "failed"
                            ? "bg-red-950/20 text-red-400 border-red-900/40"
                            : repo.analysis_status === "analyzing"
                            ? "bg-blue-950/20 text-blue-400 border-blue-900/40 animate-pulse"
                            : "bg-zinc-950/20 text-zinc-400 border-zinc-800"
                        }`}>
                          {repo.analysis_status === "analyzing" && activeJobs[repo.id]?.currentNode
                            ? `analyzing (${activeJobs[repo.id].currentNode})`
                            : repo.analysis_status}
                        </span>
                      </div>

                      {/* Language bar breakdown */}
                      {Object.keys(repo.languages).length > 0 && renderLanguageBar(repo.languages)}
                    </div>

                    <div className="mt-5 pt-3.5 border-t border-zinc-900/50 flex items-center justify-between text-xs text-zinc-500">
                      {repo.primary_language ? (
                        <span className="flex items-center gap-1.5 font-medium text-zinc-400">
                          <span className="h-2 w-2 rounded-full bg-blue-500 shadow-[0_0_6px_rgba(59,130,246,0.8)]" />
                          {repo.primary_language}
                        </span>
                      ) : (
                        <span className="text-zinc-600">Documentation</span>
                      )}
                      
                      <div className="flex items-center gap-3">
                        <span className="flex items-center gap-1.5 font-medium text-zinc-400">
                          <svg className="h-3.5 w-3.5 text-amber-500 fill-current" viewBox="0 0 24 24">
                            <path d="M12 17.27L18.18 21l-1.64-7.03L22 9.24l-7.19-.61L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21z"/>
                          </svg>
                          {repo.star_count}
                        </span>
                        
                        <button
                          onClick={() => handleAnalyze(repo.id)}
                          disabled={repo.analysis_status === "analyzing"}
                          className={`transition-all bg-blue-600 hover:bg-blue-500 text-white font-bold text-[10px] px-3 py-1 rounded transition-colors duration-150 ${
                            repo.analysis_status === "analyzing"
                              ? "opacity-50 cursor-not-allowed"
                              : "opacity-0 group-hover:opacity-100"
                          }`}
                        >
                          {repo.analysis_status === "analyzing" ? "Analyzing..." : "Analyze"}
                        </button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

        </div>
      </main>
    </div>
  );
}
