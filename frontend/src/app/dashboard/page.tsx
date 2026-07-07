"use client";

import React, { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { signIn, signOut } from "next-auth/react";
import ProfileCompletionModal from "@/components/ProfileCompletionModal";

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
  latest_job_id?: string | null;
  created_at: string;
  updated_at: string;
  recommendation_score?: number;
  recommended?: boolean;
}

interface UserProfile {
  full_name: string | null;
  email: string;
  phone: string | null;
  location: string | null;
  college: string | null;
  degree: string | null;
  cgpa: string | null;
  graduation_year: string | null;
  linkedin_url: string | null;
  portfolio_url: string | null;
  github_username: string | null;
  profile_complete: boolean;
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
  const router = useRouter();
  const handleSignOut = async () => {
    await signOut({ callbackUrl: "/login" });
  };
  const [authUser, setAuthUser] = useState<any>(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [usernameInput, setUsernameInput] = useState("");
  const [currentUsername, setCurrentUsername] = useState("");
  const [profile, setProfile] = useState<Profile | null>(null);
  const [repositories, setRepositories] = useState<Repository[]>([]);
  const [loading, setLoading] = useState(true);
  const [onboardingRequired, setOnboardingRequired] = useState(false);
  const [selectedRepoIds, setSelectedRepoIds] = useState<string[]>([]);
  const [userProfile, setUserProfile] = useState<UserProfile | null>(null);
  const [buildingResume, setBuildingResume] = useState(false);
  const [resumeJobId, setResumeJobId] = useState<string | null>(null);
  const [showProfileModal, setShowProfileModal] = useState(false);

  const fetchUserProfile = async () => {
    try {
      const res = await fetch("http://localhost:8000/api/v1/users/me/profile");
      if (res.ok) {
        const data: UserProfile = await res.json();
        setUserProfile(data);
      }
    } catch {
      // Silently fail — non-critical
    }
  };

  useEffect(() => {
    async function fetchAuthProfile() {
      try {
        const res = await fetch("http://localhost:8000/api/v1/auth/me");
        if (res.ok) {
          const data = await res.json();
          setAuthUser(data);
          if (data.github_username) {
            setCurrentUsername(data.github_username);
            setOnboardingRequired(false);
            // Auto-trigger ingestion for OAuth users (check if this is first login)
            if (data.auth_provider === "github") {
              await triggerAutoIngest(data.github_username);
            }
            // Fetch user profile data for completeness indicator
            await fetchUserProfile();
          } else {
            setOnboardingRequired(true);
            setLoading(false);
          }
        } else {
          router.push("/login");
        }
      } catch (err) {
        setConnectionError("Failed to verify authenticated session with backend.");
        setLoading(false);
      } finally {
        setAuthLoading(false);
      }
    }
    fetchAuthProfile();
  }, []);

  const triggerAutoIngest = async (username: string) => {
    try {
      console.log(`[AUTO-INGEST] Starting ingest for ${username}`);
      const ingestRes = await fetch("http://localhost:8000/api/v1/users/ingest", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ username, force_refresh: false }),
      });

      const ingestData = await ingestRes.json();
      console.log("[AUTO-INGEST] Ingest response:", ingestData);

      if (ingestRes.ok) {
        // Poll for data to populate (retry up to 10 times)
        let attempts = 0;
        const maxAttempts = 10;
        const pollInterval = setInterval(async () => {
          attempts++;
          console.log(`[AUTO-INGEST] Poll attempt ${attempts}/${maxAttempts}`);
          await fetchUserData(username);
          if (attempts >= maxAttempts) {
            clearInterval(pollInterval);
            setLoading(false);
            console.log("[AUTO-INGEST] Polling completed");
          }
        }, 1500);
      } else {
        console.error("[AUTO-INGEST] Ingest failed:", ingestData);
        setLoading(false);
      }
    } catch (error) {
      console.error("[AUTO-INGEST] Exception:", error);
      setLoading(false);
    }
  };
  const [ingesting, setIngesting] = useState(false);
  const [isSyncing, setIsSyncing] = useState(false);

  const handleManualSync = async () => {
    if (!currentUsername) return;
    setIsSyncing(true);
    try {
      const response = await fetch("http://localhost:8000/api/v1/users/ingest", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ username: currentUsername, force_refresh: true }),
      });

      if (response.ok) {
        let attempts = 0;
        const interval = setInterval(async () => {
          attempts++;
          await fetchUserData(currentUsername);
          if (attempts >= 4) {
            clearInterval(interval);
            setIsSyncing(false);
          }
        }, 3000);
      } else {
        setIsSyncing(false);
        alert("Failed to refresh GitHub data.");
      }
    } catch (error) {
      setIsSyncing(false);
      alert("Error connecting to server while syncing data.");
    }
  };

  const [statusMessage, setStatusMessage] = useState("");
  const [connectionError, setConnectionError] = useState<string | null>(null);
  const [activeJobs, setActiveJobs] = useState<Record<string, { jobId: string; currentNode: string | null }>>({});
  const [reviewAlert, setReviewAlert] = useState<{ repositoryId: string; repoName: string; jobId: string } | null>(null);

  // Analysis result states
  const [selectedRepo, setSelectedRepo] = useState<Repository | null>(null);
  const [analysisResult, setAnalysisResult] = useState<{
    facts: Array<{
      category: string;
      claim: string;
      source_file: string;
      snippet: string;
      ats_impact: string;
    }>;
    suggested_questions: string[];
    llm_tokens_used: number;
    llm_cost_usd: number;
  } | null>(null);
  const [loadingResult, setLoadingResult] = useState(false);
  const [copiedIndex, setCopiedIndex] = useState<number | null>(null);

  const handleViewResults = async (repo: Repository) => {
    setSelectedRepo(repo);
    setLoadingResult(true);
    setAnalysisResult(null);
    setCopiedIndex(null);
    try {
      const response = await fetch(`http://localhost:8000/api/v1/repositories/${repo.id}/analysis-result`);
      if (response.ok) {
        const data = await response.json();
        setAnalysisResult(data);
      } else {
        alert("Failed to fetch analysis results.");
      }
    } catch (err) {
      console.error("Error fetching analysis result:", err);
      alert("Failed to connect to backend to fetch results.");
    } finally {
      setLoadingResult(false);
    }
  };

  const copyToClipboard = (text: string, index: number) => {
    navigator.clipboard.writeText(text);
    setCopiedIndex(index);
    setTimeout(() => setCopiedIndex(null), 2000);
  };

  const fetchUserData = async (username: string) => {
    setLoading(true);
    setConnectionError(null);
    try {
      const response = await fetch(`http://localhost:8000/api/v1/repositories?username=${username}`);
      console.log(`[FETCH] Response status: ${response.status} for user: ${username}`);
      
      if (response.ok) {
        const data = await response.json();
        console.log(`[FETCH] Backend returned:`, data);
        console.log(`[FETCH] Repository count: ${data.repositories?.length || 0}`);
        
        if (data.onboarding_required) {
          console.warn("[FETCH] Onboarding still required - repos may not be ingested yet");
          setOnboardingRequired(true);
          setRepositories([]);
          setProfile(null);
        } else {
          setOnboardingRequired(false);
          const repos = data.repositories || [];
          console.log(`[FETCH] Setting ${repos.length} repositories in state`);
          setRepositories(repos);
          setProfile(data.profile || null);
          const recommendedIds = repos
            .filter((r: any) => r.recommended)
            .map((r: any) => r.id);
          setSelectedRepoIds(recommendedIds);
        }
      } else {
        const errorData = await response.text();
        console.error(`[FETCH] Backend error (${response.status}):`, errorData);
        setConnectionError(`Backend responded with status ${response.status}. Please check backend logs.`);
      }
    } catch (error) {
      console.error("[FETCH] Exception:", error);
      setConnectionError("Failed to fetch data from backend. Make sure the FastAPI container is running inside WSL.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (currentUsername) {
      fetchUserData(currentUsername);
    }
  }, [currentUsername]);

  const toggleRepoSelection = (repoId: string) => {
    setSelectedRepoIds((prev) => {
      if (prev.includes(repoId)) {
        return prev.filter((id) => id !== repoId);
      } else {
        if (prev.length >= 3) {
          alert("You can select a maximum of 3 repositories to analyze and include in your resume.");
          return prev;
        }
        return [...prev, repoId];
      }
    });
  };

  const handleBuildResume = async () => {
    if (selectedRepoIds.length === 0) return;
    setBuildingResume(true);
    try {
      const res = await fetch("http://localhost:8000/api/v1/users/me/resume", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ repo_ids: selectedRepoIds }),
      });
      if (res.ok) {
        const data = await res.json();
        setResumeJobId(data.job_id);
        router.push(`/dashboard/resume/${data.job_id}`);
      } else {
        const err = await res.json();
        setStatusMessage(`Error: ${err.detail || "Failed to start resume generation"}`);
      }
    } catch {
      setStatusMessage("Failed to connect to backend.");
    } finally {
      setBuildingResume(false);
    }
  };

  const handleAnalyze = async (repoId: string) => {
    try {
      const response = await fetch(`http://localhost:8000/api/v1/repositories/${repoId}/analyze`, {
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
        if (response.status === 429) {
          setConnectionError("Rate Limit Reached: Free accounts are limited to 5 repository analyses per hour. Please wait a bit or upgrade to Pro to unlock unlimited runs.");
        } else {
          alert(`Failed to start analysis: ${errData.detail || "Unknown error"}`);
        }
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
          const response = await fetch(`http://localhost:8000/api/v1/repositories/${repo.id}/analyze`, {
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

  // Establish WebSocket connection to listen for real-time human-in-the-loop review alerts
  useEffect(() => {
    const wsUrl = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000/api/v1/ws/reviews";
    let ws: WebSocket;
    let reconnectTimeout: NodeJS.Timeout;

    function connect() {
      ws = new WebSocket(wsUrl);
      
      ws.onopen = () => {
        console.log("Connected to RepoProof WebSocket status broadcast server.");
      };
      
      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === "status_update") {
            // Re-fetch user data to refresh repository status indicators
            fetchUserData(currentUsername);
            
            if (data.status === "awaiting_review") {
              const matchedRepo = repositories.find(r => r.id === data.repository_id);
              const repoLabel = matchedRepo ? matchedRepo.name : "your repository";
              setReviewAlert({
                repositoryId: data.repository_id,
                repoName: repoLabel,
                jobId: data.job_id
              });
            }
          }
        } catch (err) {
          console.error("Error handling WebSocket message:", err);
        }
      };

      ws.onclose = () => {
        console.log("WebSocket disconnected. Retrying in 5 seconds...");
        reconnectTimeout = setTimeout(connect, 5000);
      };
    }

    connect();

    return () => {
      if (ws) ws.close();
      clearTimeout(reconnectTimeout);
    };
  }, [repositories, currentUsername]);

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
            const res = await fetch(`http://localhost:8000/api/v1/repositories/${repoId}/analysis/${jobId}`);
            if (res.ok) {
              const data = await res.json();
              const status = data.status; // e.g. queued, running, complete, failed, interrupted
              const currentNode = data.current_node;

              if (status === "interrupted" || status === "complete" || status === "failed" || status === "timed_out") {
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
      const response = await fetch("http://localhost:8000/api/v1/users/ingest", {
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

  if (authLoading) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center bg-zinc-950 text-zinc-100 font-sans antialiased">
        <div className="flex flex-col items-center gap-3">
          <svg className="animate-spin h-8 w-8 text-blue-500" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
          </svg>
          <span className="text-sm text-zinc-500 font-medium">Verifying Session...</span>
        </div>
      </div>
    );
  }

  if (authUser && !authUser.github_username) {
    return (
      <div className="flex min-h-screen flex-col bg-zinc-950 text-zinc-100 font-sans antialiased selection:bg-blue-600/30 selection:text-blue-200">
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
            <button
              onClick={handleSignOut}
              className="rounded-lg bg-zinc-900 hover:bg-zinc-850 border border-zinc-800 hover:border-zinc-700 px-3 py-1.5 text-xs font-semibold text-zinc-300 hover:text-white transition-all cursor-pointer"
            >
              Sign Out
            </button>
          </div>
        </header>

        <main className="flex-1 flex items-center justify-center px-4 py-12">
          <div className="w-full max-w-md rounded-2xl border border-zinc-900 bg-zinc-900/30 backdrop-blur-xl p-8 shadow-2xl relative">
            <div className="absolute top-0 right-0 -translate-y-1/2 translate-x-1/2 w-48 h-48 bg-blue-500/5 rounded-full blur-3xl pointer-events-none" />
            
            <div className="flex flex-col items-center text-center mb-6">
              <div className="inline-flex items-center justify-center h-12 w-12 rounded-2xl bg-zinc-900 border border-zinc-800 mb-4 text-zinc-300">
                <svg className="h-6 w-6 fill-current" viewBox="0 0 24 24">
                  <path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z" />
                </svg>
              </div>
              <h2 className="text-xl font-bold text-white">Connect GitHub Profile</h2>
              <p className="text-xs text-zinc-400 mt-2 leading-relaxed">
                Welcome to RepoProof! To analyze your repositories and compile resume metrics, link your public GitHub account.
              </p>
            </div>

            <form onSubmit={async (e) => {
              e.preventDefault();
              if (!usernameInput.trim()) return;
              setLoading(true);
              setIngesting(true);
              setStatusMessage("Linking profile and starting repository ingestion...");
              try {
                const updateRes = await fetch("http://localhost:8000/api/v1/users/me", {
                  method: "PATCH",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({ github_username: usernameInput.trim() })
                });
                
                if (!updateRes.ok) {
                  throw new Error("Failed to link GitHub username on backend.");
                }

                const updateData = await updateRes.json();
                
                const ingestRes = await fetch("http://localhost:8000/api/v1/users/ingest", {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({ username: usernameInput.trim() })
                });

                if (ingestRes.ok) {
                  setStatusMessage("Ingestion task triggered! Importing code file trees...");
                  setAuthUser(updateData.user);
                  setCurrentUsername(usernameInput.trim());
                  
                  let attempts = 0;
                  const interval = setInterval(async () => {
                    attempts++;
                    await fetchUserData(usernameInput.trim());
                    if (attempts >= 4) {
                      clearInterval(interval);
                      setIngesting(false);
                      setStatusMessage("");
                    }
                  }, 2500);
                } else {
                  throw new Error("Failed to start ingestion task.");
                }
              } catch (err: any) {
                setConnectionError(err.message || "Failed to link and ingest GitHub profile.");
                setIngesting(false);
                setLoading(false);
              }
            }} className="space-y-4">
              <div>
                <label htmlFor="github_username_onboarding" className="block text-[10px] font-bold uppercase tracking-wider text-zinc-500 mb-1.5">
                  GitHub Username
                </label>
                <input
                  type="text"
                  id="github_username_onboarding"
                  required
                  placeholder="e.g. Atulmishra22"
                  value={usernameInput}
                  onChange={(e) => setUsernameInput(e.target.value)}
                  className="block w-full h-11 px-4 rounded-xl border border-zinc-900 bg-zinc-900/10 focus:border-blue-500/50 focus:ring-1 focus:ring-blue-500/50 text-sm placeholder-zinc-600 transition-all outline-none"
                  disabled={ingesting}
                />
              </div>

              <button
                type="submit"
                disabled={ingesting || !usernameInput.trim()}
                className="flex h-11 w-full items-center justify-center rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 font-semibold text-white hover:from-blue-500 hover:to-indigo-500 active:scale-[0.98] transition-all duration-200 shadow-lg shadow-blue-900/20 disabled:opacity-50 disabled:pointer-events-none cursor-pointer text-sm"
              >
                {ingesting ? "Linking & Importing..." : "Link & Ingest Profile"}
              </button>
            </form>

            {statusMessage && (
              <div className="mt-4 rounded-lg border border-zinc-800 bg-zinc-950 p-3 text-xs text-zinc-400 flex items-start gap-2.5">
                <span className="flex h-2 w-2 rounded-full bg-blue-500 animate-ping mt-1" />
                <span className="leading-relaxed">{statusMessage}</span>
              </div>
            )}
          </div>
        </main>
      </div>
    );
  }

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
          <div className="flex items-center gap-3">
            <div className="text-xs text-zinc-400 bg-zinc-900/60 border border-zinc-800 px-3 py-1.5 rounded-lg flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-green-500 animate-pulse" />
              <span>Connected Profile: <strong className="text-zinc-200">{currentUsername}</strong></span>
            </div>
            {currentUsername && (
              <button
                onClick={handleManualSync}
                disabled={isSyncing}
                className="text-xs font-semibold text-zinc-300 hover:text-white bg-zinc-900 hover:bg-zinc-850 border border-zinc-800 hover:border-zinc-700 px-3 py-1.5 rounded-lg transition-all flex items-center gap-1.5 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
              >
                {isSyncing ? (
                  <>
                    <svg className="animate-spin h-3.5 w-3.5 text-zinc-400" viewBox="0 0 24 24" fill="none">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                    </svg>
                    <span>Syncing...</span>
                  </>
                ) : (
                  <>
                    <svg className="h-3.5 w-3.5 text-zinc-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182m0-4.991v4.99" />
                    </svg>
                    <span>Refresh GitHub Data</span>
                  </>
                )}
              </button>
            )}
            <button
              onClick={handleSignOut}
              className="rounded-lg bg-zinc-900 hover:bg-zinc-850 border border-zinc-800 hover:border-zinc-700 px-3 py-1.5 text-xs font-semibold text-zinc-300 hover:text-white transition-all cursor-pointer"
            >
              Sign Out
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">

        {/* Real-time Review Alert Banner */}
        {reviewAlert && (
          <div className="mb-8 rounded-xl border border-amber-900/50 bg-gradient-to-r from-amber-950/20 to-orange-950/15 p-5 text-sm text-amber-200 shadow-lg shadow-amber-950/15 animate-pulse">
            <div className="flex items-center justify-between gap-4 flex-wrap sm:flex-nowrap">
              <div className="flex items-start gap-3">
                <svg className="h-5 w-5 text-amber-400 mt-0.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
                </svg>
                <div>
                  <h4 className="font-bold text-amber-400">Analysis Awaiting Review</h4>
                  <p className="mt-1 text-zinc-400">Extracted claims are ready for review and refinement for repository: <span className="text-zinc-200 font-mono font-semibold">{reviewAlert.repoName}</span></p>
                </div>
              </div>
              <div className="flex items-center gap-3 shrink-0">
                <button
                  onClick={() => setReviewAlert(null)}
                  className="px-3 py-1.5 rounded text-xs text-zinc-400 hover:text-zinc-200 transition-colors"
                >
                  Dismiss
                </button>
                <button 
                  onClick={() => {
                    setReviewAlert(null);
                    router.push(`/dashboard/review/${reviewAlert.jobId}`);
                  }}
                  className="rounded-lg bg-gradient-to-r from-amber-600 to-orange-600 hover:from-amber-500 hover:to-orange-500 border border-transparent px-4 py-1.5 text-xs font-semibold text-white transition-all shadow-[0_0_8px_rgba(245,158,11,0.2)] cursor-pointer"
                >
                  Review & Refine Now
                </button>
              </div>
            </div>
          </div>
        )}
        
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

        {onboardingRequired ? (
          <div className="mx-auto max-w-2xl py-12">
            <div className="rounded-2xl border border-zinc-900 bg-zinc-900/20 p-8 shadow-2xl backdrop-blur-md text-center space-y-6">
              <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-blue-500/10 text-blue-400">
                <svg className="h-8 w-8" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M13 10V3L4 14h7v7l9-11h-7z" />
                </svg>
              </div>
              
              <div className="space-y-2">
                <h2 className="text-2xl font-bold tracking-tight text-zinc-100">Welcome to RepoProof</h2>
                <p className="text-sm text-zinc-400 max-w-md mx-auto">
                  Connect your profile to analyze repositories and generate developer resumes, GitHub READMEs, and portfolios.
                </p>
              </div>

              <div className="pt-4 border-t border-zinc-900 space-y-4">
                {/* Option 1: Ingest via input */}
                <form onSubmit={handleIngest} className="space-y-3">
                  <label htmlFor="onboard-username" className="block text-xs font-semibold text-zinc-400 text-left">
                    Option 1: Enter a GitHub username to analyze public repos
                  </label>
                  <div className="flex gap-3">
                    <input
                      type="text"
                      id="onboard-username"
                      placeholder="e.g. Atulmishra22"
                      value={usernameInput}
                      onChange={(e) => setUsernameInput(e.target.value)}
                      className="flex-1 rounded-lg border border-zinc-800 bg-zinc-950 px-3.5 py-2 text-sm text-zinc-200 placeholder-zinc-600 outline-none focus:border-blue-500/80 focus:ring-1 focus:ring-blue-500/20 transition-all"
                      disabled={ingesting}
                    />
                    <button
                      type="submit"
                      disabled={ingesting || !usernameInput.trim()}
                      className="rounded-lg bg-blue-600 hover:bg-blue-500 px-5 py-2 text-sm font-semibold text-white shadow-lg disabled:opacity-40 transition-all"
                    >
                      {ingesting ? "Ingesting..." : "Get Started"}
                    </button>
                  </div>
                </form>

                {statusMessage && (
                  <div className="rounded-lg border border-zinc-850 bg-zinc-950/50 p-3 text-xs text-zinc-400 flex items-start gap-2.5 text-left">
                    <span className="flex h-2 w-2 rounded-full bg-blue-500 animate-ping mt-1" />
                    <span>{statusMessage}</span>
                  </div>
                )}

                <div className="relative py-4 flex items-center justify-center">
                  <div className="absolute inset-0 flex items-center">
                    <div className="w-full border-t border-zinc-850"></div>
                  </div>
                  <span className="relative bg-zinc-950 px-3 text-[10px] uppercase font-bold text-zinc-600 tracking-wider">or</span>
                </div>

                {/* Option 2: Connect via OAuth */}
                <div className="space-y-3 text-left">
                  <label className="block text-xs font-semibold text-zinc-400">
                    Option 2: Connect your GitHub Account (OAuth) to analyze private repos
                  </label>
                  <button
                    onClick={() => signIn("github")}
                    className="w-full flex items-center justify-center gap-2.5 rounded-lg border border-zinc-800 bg-zinc-950 hover:bg-zinc-900 py-3 text-sm font-semibold text-zinc-200 hover:text-white transition-all shadow-md"
                  >
                    <svg className="h-5 w-5 fill-white" viewBox="0 0 24 24">
                      <path fillRule="evenodd" clipRule="evenodd" d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.53 1.032 1.53 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482C19.138 20.193 22 16.44 22 12.017 22 6.484 17.522 2 12 2z" />
                    </svg>
                    Connect GitHub Account
                  </button>
                </div>
              </div>
            </div>
          </div>
        ) : (
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

            {/* Profile Completeness Indicator */}
            {userProfile !== null && (
              <div className="rounded-xl border border-zinc-800 bg-zinc-900/30 p-4">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-[10px] font-bold uppercase tracking-wider text-zinc-500">
                    Resume Profile
                  </span>
                  <button
                    onClick={() => setShowProfileModal(true)}
                    className="text-[10px] font-semibold text-blue-400 hover:text-blue-300 transition-colors"
                  >
                    {userProfile.profile_complete ? "Edit Profile" : "Complete Profile →"}
                  </button>
                </div>
                {/* Progress bar: count non-null required fields out of 3 */}
                {(() => {
                  const requiredFields = [userProfile.full_name, userProfile.email, userProfile.github_username];
                  const filled = requiredFields.filter(Boolean).length;
                  return (
                    <>
                      <div className="flex h-1.5 w-full overflow-hidden rounded-full bg-zinc-800">
                        <div
                          className="h-full bg-gradient-to-r from-blue-500 to-indigo-500 transition-all duration-500"
                          style={{ width: `${(filled / 3) * 100}%` }}
                        />
                      </div>
                      <p className="mt-1.5 text-[10px] text-zinc-500">
                        Profile{" "}
                        <span className="font-bold text-zinc-300">{filled}/3</span>{" "}
                        required fields complete
                        {userProfile.profile_complete && (
                          <span className="ml-1.5 text-emerald-400">✓ Ready</span>
                        )}
                      </p>
                    </>
                  );
                })()}
              </div>
            )}

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
            <div className="flex flex-col sm:flex-row sm:items-center justify-between border-b border-zinc-900 pb-4 gap-3">
              <div>
                <h2 className="text-lg font-bold tracking-tight text-zinc-200">
                  Discovered Repositories
                </h2>
                <p className="text-[10px] text-zinc-500 mt-0.5">Select up to 3 projects to analyze for resume generation</p>
              </div>
              <div className="flex items-center gap-3">
                <span className="rounded-full bg-zinc-900 px-3 py-1.5 text-xs font-semibold text-zinc-300 border border-zinc-800">
                  {repositories.length} public projects
                </span>
                {selectedRepoIds.length > 0 && (
                  <div className="flex items-center gap-2">
                    {/* Analyze Selected */}
                    <button
                      onClick={async () => {
                        setStatusMessage(`Triggering batch analysis for ${selectedRepoIds.length} repositories...`);
                        for (const id of selectedRepoIds) {
                          const targetRepo = repositories.find(r => r.id === id);
                          if (targetRepo && targetRepo.analysis_status !== "analyzing") {
                            await handleAnalyze(id);
                          }
                        }
                        setStatusMessage("");
                      }}
                      className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-white text-xs font-bold transition-all border border-zinc-700"
                    >
                      Analyze Selected ({selectedRepoIds.length}/3)
                    </button>

                    {/* Build Combined Resume - only when ALL selected repos are complete */}
                    {selectedRepoIds.every(id =>
                      repositories.find(r => r.id === id)?.analysis_status === "complete"
                    ) && (
                      <button
                        onClick={handleBuildResume}
                        disabled={buildingResume}
                        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-gradient-to-r from-violet-600 to-purple-600 hover:from-violet-500 hover:to-purple-500 disabled:opacity-60 text-white text-xs font-bold transition-all shadow-[0_0_12px_rgba(139,92,246,0.3)]"
                      >
                        {buildingResume ? (
                          <>
                            <svg className="animate-spin h-3 w-3" viewBox="0 0 24 24" fill="none"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z"/></svg>
                            Building...
                          </>
                        ) : (
                          <>
                            <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>
                            Build Combined Resume ({selectedRepoIds.length})
                          </>
                        )}
                      </button>
                    )}
                  </div>
                )}
              </div>
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
                        <div className="flex items-start gap-2.5">
                          <input
                            type="checkbox"
                            checked={selectedRepoIds.includes(repo.id)}
                            onChange={() => toggleRepoSelection(repo.id)}
                            className="mt-1 h-3.5 w-3.5 rounded border-zinc-800 bg-zinc-950 text-blue-600 focus:ring-blue-500 focus:ring-offset-zinc-950 cursor-pointer"
                          />
                          <div className="space-y-1">
                            <h3 className="font-semibold text-zinc-100 group-hover:text-blue-400 transition-colors">
                              <a href={repo.github_url} target="_blank" rel="noopener noreferrer" className="flex items-center gap-1.5 break-all text-sm leading-snug">
                                {repo.name}
                                <svg className="h-3.5 w-3.5 opacity-0 group-hover:opacity-100 text-blue-400 transition-all transform translate-x-[-4px] group-hover:translate-x-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                                </svg>
                              </a>
                            </h3>
                            <div className="flex items-center gap-2">
                              <p className="text-[10px] text-zinc-500 font-medium uppercase tracking-wider">Default branch: {repo.default_branch}</p>
                              {repo.recommendation_score !== undefined && (
                                <span className="text-[9px] text-zinc-400 bg-zinc-900 border border-zinc-850 px-1.5 py-0.5 rounded font-mono">
                                  RQS: {repo.recommendation_score}
                                </span>
                              )}
                            </div>
                          </div>
                        </div>
                        <div className="flex items-center gap-2 flex-shrink-0">
                          {repo.recommended && (
                            <span className="inline-flex items-center gap-1 rounded bg-blue-950/40 text-blue-400 border border-blue-900/50 px-2 py-0.5 text-[8px] font-bold uppercase tracking-wider">
                              ★ Recommended
                            </span>
                          )}
                          <span className={`inline-flex rounded-full border px-2 py-0.5 text-[9px] font-bold uppercase tracking-wider ${
                            repo.analysis_status === "complete" 
                              ? "bg-green-950/20 text-green-400 border-green-900/40"
                              : repo.analysis_status === "awaiting_review"
                              ? "bg-amber-950/20 text-amber-400 border-amber-900/40"
                              : repo.analysis_status === "failed"
                              ? "bg-red-950/20 text-red-400 border-red-900/40"
                              : repo.analysis_status === "analyzing"
                              ? "bg-blue-950/20 text-blue-400 border-blue-900/40 animate-pulse"
                              : "bg-zinc-950/20 text-zinc-400 border-zinc-800"
                          }`}>
                            {repo.analysis_status === "analyzing" && activeJobs[repo.id]?.currentNode
                              ? `analyzing (${activeJobs[repo.id].currentNode})`
                              : repo.analysis_status === "awaiting_review"
                              ? "awaiting review"
                              : repo.analysis_status}
                          </span>
                        </div>
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
                        
                        {repo.analysis_status === "complete" ? (
                          <div className="flex gap-2">
                            <button
                              onClick={() => handleViewResults(repo)}
                              className="bg-zinc-800 hover:bg-zinc-700 text-zinc-300 font-bold text-[10px] px-2.5 py-1.5 rounded transition-colors border border-zinc-700"
                            >
                              View Facts
                            </button>
                            <button
                              onClick={() => router.push(`/dashboard/outputs/${repo.id}`)}
                              className="bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white font-bold text-[10px] px-2.5 py-1.5 rounded transition-all shadow-[0_0_8px_rgba(99,102,241,0.3)]"
                            >
                              View Outputs
                            </button>
                          </div>
                        ) : repo.analysis_status === "awaiting_review" ? (
                          <button
                            onClick={() => router.push(`/dashboard/review/${repo.latest_job_id}`)}
                            className="bg-gradient-to-r from-amber-600 to-orange-600 hover:from-amber-500 hover:to-orange-500 text-white font-bold text-[10px] px-3.5 py-1.5 rounded transition-all duration-150 shadow-[0_0_8px_rgba(245,158,11,0.3)]"
                          >
                            Review & Refine
                          </button>
                        ) : (
                          <button
                            onClick={() => handleAnalyze(repo.id)}
                            disabled={repo.analysis_status === "analyzing"}
                            className={`transition-all bg-blue-600 hover:bg-blue-500 text-white font-bold text-[10px] px-3.5 py-1.5 rounded transition-colors duration-150 shadow-[0_0_8px_rgba(37,99,235,0.3)] ${
                              repo.analysis_status === "analyzing"
                                ? "opacity-50 cursor-not-allowed"
                                : "opacity-0 group-hover:opacity-100"
                            }`}
                          >
                            {repo.analysis_status === "analyzing" ? "Analyzing..." : "Analyze"}
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

        </div>
        )}
      </main>

      {/* Premium Analysis Results Modal */}
      {selectedRepo && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-zinc-950/80 backdrop-blur-sm animate-fade-in">
          <div className="relative w-full max-w-4xl max-h-[85vh] overflow-y-auto rounded-xl border border-zinc-800 bg-zinc-900/95 p-6 shadow-2xl backdrop-blur-md flex flex-col justify-between scrollbar-thin scrollbar-thumb-zinc-800">
            {/* Modal Header */}
            <div className="flex items-start justify-between border-b border-zinc-800 pb-4 mb-5">
              <div>
                <h3 className="text-lg font-bold text-zinc-100 flex items-center gap-2">
                  <span className="bg-clip-text text-transparent bg-gradient-to-r from-blue-400 to-indigo-400">
                    {selectedRepo.name}
                  </span>
                  <span className="text-zinc-500 text-xs font-normal">analysis details</span>
                </h3>
                <a
                  href={selectedRepo.github_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs text-zinc-400 hover:text-cyan-400 font-mono flex items-center gap-1.5 mt-1"
                >
                  {selectedRepo.github_url}
                  <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                  </svg>
                </a>
              </div>
              
              <button
                onClick={() => setSelectedRepo(null)}
                className="rounded-lg border border-zinc-800 bg-zinc-950 p-1.5 text-zinc-400 hover:text-zinc-100 hover:border-zinc-700 transition-all"
              >
                <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            {/* Modal Content */}
            {loadingResult ? (
              <div className="flex flex-col items-center justify-center py-20 space-y-4">
                <div className="h-8 w-8 animate-spin rounded-full border-4 border-blue-500 border-t-transparent" />
                <p className="text-sm text-zinc-400 font-medium">Fetching analysis results from storage...</p>
              </div>
            ) : analysisResult ? (
              <div className="space-y-6">
                
                {/* Cost and Usage Metrics Banner */}
                <div className="grid grid-cols-3 gap-4 rounded-xl border border-zinc-800/80 bg-zinc-950/50 p-4 text-center">
                  <div>
                    <span className="block text-[10px] font-semibold uppercase tracking-wider text-zinc-500">Analysis Cost</span>
                    <span className="mt-1 block text-md font-bold text-emerald-400 font-mono">
                      ${analysisResult.llm_cost_usd.toFixed(6)}
                    </span>
                  </div>
                  <div className="border-x border-zinc-800">
                    <span className="block text-[10px] font-semibold uppercase tracking-wider text-zinc-500">Tokens Consumed</span>
                    <span className="mt-1 block text-md font-bold text-blue-400 font-mono">
                      {analysisResult.llm_tokens_used.toLocaleString()}
                    </span>
                  </div>
                  <div>
                    <span className="block text-[10px] font-semibold uppercase tracking-wider text-zinc-500">Model Used</span>
                    <span className="mt-1 block text-xs font-bold text-zinc-300">
                      gemini-3.1-flash-lite
                    </span>
                  </div>
                </div>

                {/* Extracted Facts (ATS Resume Feed) */}
                <div>
                  <h4 className="text-xs font-bold uppercase tracking-wider text-zinc-400 mb-3.5 flex items-center gap-2">
                    <svg className="h-4 w-4 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                    ATS Resume Bullet Points & Fact Claims ({analysisResult.facts?.length || 0})
                  </h4>
                  
                  {(!analysisResult.facts || analysisResult.facts.length === 0) ? (
                    <p className="text-xs text-zinc-500 italic p-4 border border-zinc-850 rounded-xl bg-zinc-950/20 text-center">
                      No facts could be validated for this repository.
                    </p>
                  ) : (
                    <div className="space-y-4">
                      {analysisResult.facts.map((fact, idx) => {
                        // Category colors
                        const categoryStyles: Record<string, string> = {
                          technology_used: "bg-amber-950/30 text-amber-400 border-amber-900/30",
                          architecture_pattern: "bg-purple-950/30 text-purple-400 border-purple-900/30",
                          complexity_metric: "bg-cyan-950/30 text-cyan-400 border-cyan-900/30",
                          contribution: "bg-blue-950/30 text-blue-400 border-blue-900/30",
                          performance_optimization: "bg-emerald-950/30 text-emerald-400 border-emerald-900/30",
                          security_hardening: "bg-rose-950/30 text-rose-400 border-rose-900/30",
                          cost_saving: "bg-teal-950/30 text-teal-400 border-teal-900/30",
                        };
                        const badgeStyle = categoryStyles[fact.category] || "bg-zinc-950/30 text-zinc-400 border-zinc-900";

                        return (
                          <div 
                            key={idx} 
                            className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-4 hover:bg-zinc-900/60 transition-colors"
                          >
                            {/* Card Header: Category & Copy button */}
                            <div className="flex items-center justify-between mb-2">
                              <span className={`inline-flex rounded-full border px-2.5 py-0.5 text-[9px] font-bold uppercase tracking-wider ${badgeStyle}`}>
                                {fact.category.replace("_", " ")}
                              </span>
                              
                              <button
                                onClick={() => copyToClipboard(fact.claim, idx)}
                                className={`text-[10px] font-semibold px-2 py-1 rounded border transition-all flex items-center gap-1.5 ${
                                  copiedIndex === idx
                                    ? "bg-green-950/20 border-green-800 text-green-400"
                                    : "bg-zinc-950 border-zinc-800 text-zinc-400 hover:text-zinc-200 hover:border-zinc-700"
                                }`}
                              >
                                {copiedIndex === idx ? (
                                  <>
                                    <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
                                    </svg>
                                    Copied!
                                  </>
                                ) : (
                                  <>
                                    <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 012-2h2a2 2 0 012 2m0 0h2a2 2 0 012 2v3m2 4H10m0 0l3-3m-3 3l3 3" />
                                    </svg>
                                    Copy Bullet Point
                                  </>
                                )}
                              </button>
                            </div>

                            {/* Bullet point claim */}
                            <p className="text-sm font-semibold text-zinc-100 pr-2 leading-relaxed">
                              {fact.claim}
                            </p>

                            {/* ATS Impact explanation */}
                            <div className="mt-3 rounded-lg bg-zinc-950/40 border border-zinc-850 p-3">
                              <span className="block text-[9px] font-semibold uppercase tracking-wider text-zinc-500">ATS impact & Expertise profile</span>
                              <p className="mt-1 text-xs text-zinc-400 leading-relaxed">{fact.ats_impact}</p>
                            </div>

                            {/* Evidence Code Snippet */}
                            {fact.source_file && fact.snippet && (
                              <div className="mt-3">
                                <span className="text-[10px] font-bold text-zinc-500 flex items-center gap-1.5 mb-1.5 font-mono">
                                  <svg className="h-3 w-3 text-zinc-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
                                  </svg>
                                  Citation: {fact.source_file}
                                </span>
                                <div className="rounded-lg bg-zinc-950 p-3 border border-zinc-900 overflow-x-auto text-[10px] font-mono text-zinc-300 leading-relaxed scrollbar-thin scrollbar-thumb-zinc-800">
                                  <pre className="whitespace-pre">{fact.snippet}</pre>
                                </div>
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>

                {/* Developer Feedback Questions */}
                {analysisResult.suggested_questions && analysisResult.suggested_questions.length > 0 && (
                  <div className="border-t border-zinc-800 pt-5">
                    <h4 className="text-xs font-bold uppercase tracking-wider text-zinc-400 mb-3 flex items-center gap-2">
                      <svg className="h-4 w-4 text-indigo-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                      </svg>
                      Developer Verification & Follow-up Questions
                    </h4>
                    <ul className="space-y-2.5">
                      {analysisResult.suggested_questions.map((question, qIdx) => (
                        <li 
                          key={qIdx} 
                          className="rounded-lg bg-indigo-950/10 border border-indigo-900/30 p-3.5 text-xs text-zinc-300 leading-relaxed flex items-start gap-2.5"
                        >
                          <span className="flex h-5 w-5 items-center justify-center rounded-full bg-indigo-900/30 text-[9px] font-bold text-indigo-400 shrink-0">
                            {qIdx + 1}
                          </span>
                          <span>{question}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                
              </div>
            ) : null}
          </div>
        </div>
      )}

      {/* Profile Completion Modal — shown when user clicks Complete Profile or from resume status page */}
      <ProfileCompletionModal
        isOpen={showProfileModal}
        jobId={resumeJobId || ""}
        jobType="multi"
        onSuccess={() => {
          setShowProfileModal(false);
          fetchUserProfile();
        }}
        onClose={() => setShowProfileModal(false)}
      />
    </div>
  );
}
