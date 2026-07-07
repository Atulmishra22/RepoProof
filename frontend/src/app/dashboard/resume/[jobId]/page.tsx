"use client";

import React, { useState, useEffect } from "react";
import { useRouter, useParams } from "next/navigation";
import ProfileCompletionModal from "@/components/ProfileCompletionModal";

interface JobStatusResponse {
  job_id: string;
  status: string;
  repo_ids: string[];
  missing_fields: string[];
  needs_clarification: boolean;
  personal_context: any;
  presigned_url: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

const STEPS = [
  { id: "facts", label: "Loading approved facts" },
  { id: "context", label: "Verifying profile completeness" },
  { id: "merge", label: "Merging & deduplicating facts" },
  { id: "latex", label: "Generating LaTeX resume structure" },
  { id: "healing", label: "Running AI compilation self-healing" },
  { id: "upload", label: "Finalizing document & uploading PDF" },
];

export default function MultiResumeStatusPage() {
  const router = useRouter();
  const params = useParams();
  const jobId = params?.jobId as string;

  const [job, setJob] = useState<JobStatusResponse | null>(null);
  const [currentStep, setCurrentStep] = useState(0);
  const [loading, setLoading] = useState(true);
  const [polling, setPolling] = useState(true);
  const [showClarifyModal, setShowClarifyModal] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!jobId) return;

    const fetchStatus = async () => {
      try {
        const res = await fetch(`http://localhost:8000/api/v1/users/me/resume/${jobId}`);
        if (!res.ok) {
          if (res.status === 404) {
            setError("Resume job not found.");
            setPolling(false);
            return;
          }
          throw new Error("Failed to fetch job status.");
        }
        const data: JobStatusResponse = await res.json();
        setJob(data);

        // Map status to current progress step
        const statusMap: Record<string, number> = {
          queued: 0,
          running: 1,
          starting: 1,
          facts_loaded: 2,
          context_verified: 2,
          facts_merged: 3,
          latex_generated: 4,
          complete: 6,
          failed: 5,
          interrupted: 1,
        };

        const step = statusMap[data.status] ?? 0;
        setCurrentStep(step);

        if (data.status === "complete") {
          setPolling(false);
          setLoading(false);
        } else if (data.status === "failed") {
          setPolling(false);
          setError(data.error_message || "Resume generation failed. Please try again.");
          setLoading(false);
        } else if (data.status === "interrupted") {
          setPolling(false);
          setShowClarifyModal(true);
          setLoading(false);
        }
      } catch (err) {
        console.error("Polling error:", err);
      }
    };

    fetchStatus();

    let interval: NodeJS.Timeout | null = null;
    if (polling) {
      interval = setInterval(fetchStatus, 3000);
    }

    return () => {
      if (interval) clearInterval(interval);
    };
  }, [jobId, polling]);

  const handleClarificationSuccess = () => {
    setShowClarifyModal(false);
    setPolling(true);
    setLoading(true);
  };

  const getStepStatus = (index: number) => {
    if (job?.status === "failed" && index === currentStep) return "failed";
    if (currentStep > index) return "completed";
    if (currentStep === index && job?.status !== "interrupted") return "active";
    if (job?.status === "interrupted" && index === 1) return "interrupted";
    return "pending";
  };

  return (
    <div className="min-h-screen bg-black text-zinc-100 flex flex-col items-center justify-center p-6 select-none font-sans">
      <div className="w-full max-w-xl rounded-2xl border border-zinc-800 bg-zinc-950/40 backdrop-blur-md p-8 shadow-2xl relative overflow-hidden">
        {/* Glow effect */}
        <div className="absolute -top-40 -left-40 h-80 w-80 rounded-full bg-violet-600/10 blur-[120px]" />
        <div className="absolute -bottom-40 -right-40 h-80 w-80 rounded-full bg-indigo-600/10 blur-[120px]" />

        {/* Success State */}
        {job?.status === "complete" ? (
          <div className="space-y-6 text-center py-4 relative z-10">
            <div className="inline-flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-tr from-violet-500/10 to-indigo-500/10 border border-violet-500/30 shadow-[0_0_20px_rgba(139,92,246,0.15)] animate-pulse">
              <svg className="h-8 w-8 text-violet-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
            <div>
              <h1 className="text-2xl font-bold tracking-tight bg-gradient-to-r from-zinc-100 via-zinc-200 to-zinc-300 bg-clip-text text-transparent">
                Resume Generated!
              </h1>
              <p className="text-sm text-zinc-500 mt-2">
                We successfully merged facts across {job.repo_ids.length} of your projects into a unified LaTeX resume.
              </p>
            </div>

            <div className="pt-4 flex flex-col sm:flex-row gap-3 justify-center items-center">
              {job.presigned_url ? (
                <a
                  href={job.presigned_url}
                  download="combined_resume.pdf"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-6 py-3 rounded-xl bg-gradient-to-r from-violet-600 to-purple-600 hover:from-violet-500 hover:to-purple-500 text-white font-semibold text-sm transition-all shadow-[0_0_15px_rgba(139,92,246,0.35)]"
                >
                  <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                  </svg>
                  Download PDF
                </a>
              ) : (
                <span className="text-xs text-zinc-500">PDF generation complete. Presigned URL missing.</span>
              )}
              <button
                onClick={() => router.push("/dashboard")}
                className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-6 py-3 rounded-xl bg-zinc-900 border border-zinc-800 hover:bg-zinc-800 hover:border-zinc-700 text-zinc-300 font-semibold text-sm transition-all"
              >
                Back to Dashboard
              </button>
            </div>
          </div>
        ) : error ? (
          /* Error State */
          <div className="space-y-6 text-center py-4 relative z-10">
            <div className="inline-flex h-16 w-16 items-center justify-center rounded-2xl bg-red-500/10 border border-red-500/20">
              <svg className="h-8 w-8 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
            </div>
            <div>
              <h1 className="text-xl font-bold tracking-tight text-red-400">
                Resume Generation Failed
              </h1>
              <p className="text-xs text-zinc-500 mt-3 bg-zinc-950 p-4 rounded-xl border border-zinc-900 overflow-x-auto text-left font-mono leading-relaxed whitespace-pre-wrap max-h-48 scrollbar-thin">
                {error}
              </p>
            </div>
            <div className="pt-4 flex gap-3 justify-center">
              <button
                onClick={() => router.push("/dashboard")}
                className="px-5 py-2.5 rounded-lg bg-zinc-900 border border-zinc-800 hover:bg-zinc-800 text-zinc-300 font-semibold text-xs transition-all"
              >
                Back to Dashboard
              </button>
            </div>
          </div>
        ) : (
          /* Pipeline Processing State */
          <div className="space-y-8 relative z-10">
            <div className="flex items-center justify-between">
              <div>
                <h1 className="text-lg font-bold tracking-tight text-zinc-200">
                  Building Combined Resume
                </h1>
                <p className="text-xs text-zinc-500 mt-1">Merging technical facts and generating single-page LaTeX PDF</p>
              </div>
              {job?.status === "interrupted" ? (
                <span className="rounded-full bg-amber-950/40 border border-amber-900/40 px-2.5 py-1 text-[10px] font-bold text-amber-400 uppercase tracking-wide">
                  Clarification Required
                </span>
              ) : (
                <div className="flex h-5 w-5 items-center justify-center">
                  <svg className="animate-spin h-4 w-4 text-violet-400" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                  </svg>
                </div>
              )}
            </div>

            {/* Pipeline progress steps */}
            <div className="space-y-4">
              {STEPS.map((step, idx) => {
                const status = getStepStatus(idx);
                return (
                  <div key={step.id} className="flex items-center gap-3">
                    <div className="flex items-center justify-center h-5 w-5 rounded-full border text-xs">
                      {status === "completed" ? (
                        <div className="h-5 w-5 rounded-full bg-violet-600 border border-violet-500 flex items-center justify-center text-white">
                          <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                          </svg>
                        </div>
                      ) : status === "active" ? (
                        <div className="h-5 w-5 rounded-full border border-violet-500/50 flex items-center justify-center relative">
                          <span className="h-2 w-2 rounded-full bg-violet-400 animate-ping absolute" />
                          <span className="h-2 w-2 rounded-full bg-violet-400 relative" />
                        </div>
                      ) : status === "interrupted" ? (
                        <div className="h-5 w-5 rounded-full bg-amber-950/40 border border-amber-900/50 flex items-center justify-center text-amber-400">
                          <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01" />
                          </svg>
                        </div>
                      ) : status === "failed" ? (
                        <div className="h-5 w-5 rounded-full bg-red-950/40 border border-red-900/50 flex items-center justify-center text-red-400">
                          <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                          </svg>
                        </div>
                      ) : (
                        <div className="h-5 w-5 rounded-full border border-zinc-800 flex items-center justify-center bg-zinc-950 text-zinc-600 text-[10px] font-semibold">
                          {idx + 1}
                        </div>
                      )}
                    </div>
                    <span
                      className={`text-xs font-semibold leading-relaxed ${
                        status === "completed"
                          ? "text-zinc-400"
                          : status === "active"
                          ? "text-violet-400"
                          : status === "interrupted"
                          ? "text-amber-400"
                          : status === "failed"
                          ? "text-red-400"
                          : "text-zinc-600"
                      }`}
                    >
                      {step.label}
                    </span>
                  </div>
                );
              })}
            </div>

            {job?.status === "interrupted" && (
              <div className="p-4 rounded-xl bg-amber-950/10 border border-amber-900/20 text-center space-y-3">
                <p className="text-xs text-amber-400 leading-relaxed font-semibold">
                  Personal profile fields are incomplete or invalid. Please complete them to continue resume generation.
                </p>
                <button
                  onClick={() => setShowClarifyModal(true)}
                  className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-gradient-to-r from-amber-600 to-yellow-600 hover:from-amber-500 hover:to-yellow-500 text-white text-xs font-bold transition-all shadow-[0_0_10px_rgba(245,158,11,0.2)]"
                >
                  Provide Details
                </button>
              </div>
            )}
          </div>
        )}
      </div>

      {job && (
        <ProfileCompletionModal
          isOpen={showClarifyModal}
          jobId={jobId}
          jobType="multi"
          missingFields={job.missing_fields}
          prefillData={job.personal_context}
          onSuccess={handleClarificationSuccess}
          onClose={() => setShowClarifyModal(false)}
        />
      )}
    </div>
  );
}
