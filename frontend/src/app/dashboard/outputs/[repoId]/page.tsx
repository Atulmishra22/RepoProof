"use client";

import React, { useState, useEffect } from "react";
import { useRouter, useParams } from "next/navigation";

interface Output {
  id: string;
  analysis_job_id: string;
  output_type: string;
  content: string;
  version: number;
  minio_object_key: string;
  created_at: string;
  updated_at: string;
}

interface Repository {
  id: string;
  name: string;
  owner: string;
  github_url: string;
  analysis_status: string;
}

export default function OutputsPage() {
  const router = useRouter();
  const params = useParams();
  const repoId = params?.repoId as string;

  const [loading, setLoading] = useState(true);
  const [repo, setRepo] = useState<Repository | null>(null);
  const [outputs, setOutputs] = useState<Output[]>([]);
  const [activeTab, setActiveTab] = useState<string>("resume");
  const [copied, setCopied] = useState<boolean>(false);
  const [downloadingZip, setDownloadingZip] = useState<boolean>(false);

  // Regeneration modal state
  const [showRegenModal, setShowRegenModal] = useState<boolean>(false);
  const [regenInstructions, setRegenInstructions] = useState<string>("");
  const [atsMode, setAtsMode] = useState<string>("experienced");
  const [isRegenerating, setIsRegenerating] = useState<boolean>(false);
  const [regenError, setRegenError] = useState<string | null>(null);

  // Presigned URL for PDF resume preview
  const [resumePdfUrl, setResumePdfUrl] = useState<string>("");

  useEffect(() => {
    if (repoId) {
      fetchRepositoryAndOutputs();
    }
  }, [repoId]);

  const fetchRepositoryAndOutputs = async () => {
    setLoading(true);
    try {
      // 1. Fetch repositories and find matching one to get the name
      const repoRes = await fetch("http://localhost:8000/api/v1/repositories");
      if (repoRes.ok) {
        const repoData = await repoRes.json();
        const found = repoData.repositories?.find((r: Repository) => r.id === repoId);
        if (found) {
          setRepo(found);
        }
      }

      // 2. Fetch outputs
      const outputsRes = await fetch(`http://localhost:8000/api/v1/repositories/${repoId}/outputs`);
      if (outputsRes.ok) {
        const outputsData = await outputsRes.json();
        setOutputs(outputsData || []);
        
        // Find resume output and fetch its PDF download URL
        const resumeOut = outputsData.find((o: Output) => o.output_type === "resume_bullets");
        if (resumeOut) {
          fetchResumePdfUrl(resumeOut.id);
        }
      }
    } catch (err) {
      console.error("Error fetching outputs:", err);
    } finally {
      setLoading(false);
    }
  };

  const fetchResumePdfUrl = async (outputId: string) => {
    try {
      const urlRes = await fetch(`http://localhost:8000/api/v1/outputs/${outputId}/download?format=pdf`);
      if (urlRes.ok) {
        const data = await urlRes.json();
        setResumePdfUrl(data.download_url);
      }
    } catch (err) {
      console.error("Error fetching PDF URL:", err);
    }
  };

  const getActiveOutput = (): Output | undefined => {
    const typeMapping: Record<string, string> = {
      resume: "resume_bullets",
      linkedin: "linkedin_desc",
      readme: "readme",
      portfolio: "portfolio_doc"
    };
    const targetType = typeMapping[activeTab];
    return outputs.find((o) => o.output_type === targetType);
  };

  const activeOutput = getActiveOutput();

  const handleCopyCode = () => {
    if (activeOutput) {
      navigator.clipboard.writeText(activeOutput.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const handleDownloadFile = async (format?: string) => {
    if (!activeOutput) return;
    try {
      let query = "";
      if (format) {
        query = `?format=${format}`;
      }
      const dlRes = await fetch(`http://localhost:8000/api/v1/outputs/${activeOutput.id}/download${query}`);
      if (dlRes.ok) {
        const data = await dlRes.json();
        // Trigger browser download by clicking a link
        const link = document.createElement("a");
        link.href = data.download_url;
        // set download filename
        const ext = format === "tex" ? "tex" : (activeOutput.output_type === "resume_bullets" ? "pdf" : "md");
        link.setAttribute("download", `repo_proof_${activeTab}.${ext}`);
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
      } else {
        alert("Failed to fetch download link.");
      }
    } catch (err) {
      console.error("Download error:", err);
      alert("Error initiating file download.");
    }
  };

  const handleDownloadAllZip = async () => {
    setDownloadingZip(true);
    try {
      const zipRes = await fetch(`http://localhost:8000/api/v1/repositories/${repoId}/outputs/export`);
      if (zipRes.ok) {
        const data = await zipRes.json();
        const link = document.createElement("a");
        link.href = data.download_url;
        link.setAttribute("download", `${repo?.name || "repository"}_outputs.zip`);
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
      } else {
        alert("Failed to build ZIP export bundle.");
      }
    } catch (err) {
      console.error("ZIP export error:", err);
      alert("Error downloading zip bundle.");
    } finally {
      setDownloadingZip(false);
    }
  };

  const handleRegenerate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!activeOutput) return;
    setIsRegenerating(true);
    setRegenError(null);

    try {
      const regenRes = await fetch(`http://localhost:8000/api/v1/outputs/${activeOutput.id}/regenerate`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          ats_mode: atsMode,
          custom_instructions: regenInstructions
        })
      });

      if (regenRes.ok) {
        const data = await regenRes.json();
        // Update local outputs array with the newly regenerated output
        setOutputs((prev) =>
          prev.map((o) => (o.id === activeOutput.id ? { ...o, content: data.output.content, version: data.output.version } : o))
        );
        setShowRegenModal(false);
        setRegenInstructions("");
        
        // If resume, refresh PDF Url
        if (activeOutput.output_type === "resume_bullets") {
          fetchResumePdfUrl(activeOutput.id);
        }
      } else {
        const errData = await regenRes.json();
        setRegenError(errData.detail || "Failed to regenerate document.");
      }
    } catch (err) {
      console.error("Regeneration error:", err);
      setRegenError("Server connection failed during regeneration.");
    } finally {
      setIsRegenerating(false);
    }
  };

  const parseBold = (text: string) => {
    const parts = text.split(/\*\*(.*?)\*\*/g);
    return parts.map((part, i) => {
      if (i % 2 === 1) {
        return <strong key={i} className="font-semibold text-zinc-100">{part}</strong>;
      }
      return part;
    });
  };

  const renderMarkdown = (md: string) => {
    if (!md) return null;
    const lines = md.split("\n");
    return lines.map((line, idx) => {
      if (line.startsWith("# ")) {
        return <h1 key={idx} className="text-2xl font-extrabold text-zinc-100 mt-6 mb-4 border-b border-zinc-800 pb-2">{line.substring(2)}</h1>;
      }
      if (line.startsWith("## ")) {
        return <h2 key={idx} className="text-xl font-bold text-zinc-100 mt-5 mb-3">{line.substring(3)}</h2>;
      }
      if (line.startsWith("### ")) {
        return <h3 key={idx} className="text-lg font-bold text-zinc-200 mt-4 mb-2">{line.substring(4)}</h3>;
      }
      if (line.trim().startsWith("- ") || line.trim().startsWith("* ")) {
        const cleanLine = line.trim().substring(2);
        return (
          <li key={idx} className="ml-5 list-disc text-sm text-zinc-300 my-1.5">
            {parseBold(cleanLine)}
          </li>
        );
      }
      if (line.startsWith("```")) {
        return null; // Skip code formatting tags for text flow
      }
      if (line.trim() === "") {
        return <div key={idx} className="h-2" />;
      }
      return <p key={idx} className="text-sm text-zinc-300 leading-relaxed my-2">{parseBold(line)}</p>;
    });
  };

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 font-sans antialiased selection:bg-blue-600/30 selection:text-blue-200">
      {/* Top Header */}
      <header className="sticky top-0 z-40 border-b border-zinc-900 bg-zinc-950/80 backdrop-blur-md">
        <div className="mx-auto flex max-w-7xl h-16 items-center justify-between px-4 sm:px-6 lg:px-8">
          <div className="flex items-center gap-4">
            <button
              onClick={() => router.push("/dashboard")}
              className="flex items-center gap-2 text-sm text-zinc-400 hover:text-zinc-200 bg-zinc-900/60 border border-zinc-800 px-3 py-1.5 rounded-lg transition-all"
            >
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
              </svg>
              Back to Dashboard
            </button>
            <span className="text-xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-blue-400 via-indigo-400 to-cyan-400">
              Generated Outputs
            </span>
          </div>
          {repo && (
            <div className="text-xs text-zinc-400 bg-zinc-900/60 border border-zinc-800 px-3 py-1.5 rounded-lg font-mono">
              repo: <span className="text-blue-400 font-bold">{repo.owner} / {repo.name}</span>
            </div>
          )}
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
        {loading ? (
          <div className="flex h-[500px] flex-col items-center justify-center gap-4">
            <div className="h-12 w-12 animate-spin rounded-full border-4 border-zinc-800 border-t-blue-500" />
            <p className="text-sm text-zinc-400 animate-pulse">Loading compiled documents and assets...</p>
          </div>
        ) : outputs.length === 0 ? (
          <div className="flex h-[400px] flex-col items-center justify-center rounded-2xl border border-zinc-900 bg-zinc-900/20 p-8 text-center backdrop-blur-md">
            <svg className="mx-auto h-12 w-12 text-zinc-600 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
            <h3 className="text-lg font-bold text-zinc-200">No Outputs Compiled Yet</h3>
            <p className="mt-2 text-sm text-zinc-400 max-w-md">
              The analysis workflow must complete the review phase before outputs are compiled. Please resume the review on your dashboard.
            </p>
            <button
              onClick={() => router.push("/dashboard")}
              className="mt-6 rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-500 transition-colors"
            >
              Go to Dashboard
            </button>
          </div>
        ) : (
          <div>
            {/* Global Actions Block */}
            <div className="mb-6 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 bg-zinc-900/40 border border-zinc-900 p-4 rounded-2xl backdrop-blur-md">
              <div>
                <h2 className="text-base font-bold text-zinc-200">Marketing & Job Application Assets</h2>
                <p className="text-xs text-zinc-400 mt-1">Generated and ATS-optimized assets ready for your profile improvement.</p>
              </div>
              <button
                onClick={handleDownloadAllZip}
                disabled={downloadingZip}
                className="flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 px-4 py-2.5 text-sm font-bold text-white hover:from-blue-500 hover:to-indigo-500 shadow-lg shadow-blue-550/20 transition-all disabled:opacity-50"
              >
                {downloadingZip ? (
                  <>
                    <div className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
                    Zipping files...
                  </>
                ) : (
                  <>
                    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                    </svg>
                    Download All (.zip)
                  </>
                )}
              </button>
            </div>

            {/* Tabs Selector */}
            <div className="mb-6 flex border-b border-zinc-900">
              <button
                onClick={() => { setActiveTab("resume"); setCopied(false); }}
                className={`px-5 py-3 text-sm font-semibold border-b-2 transition-all ${activeTab === "resume" ? "border-blue-500 text-blue-400" : "border-transparent text-zinc-400 hover:text-zinc-200"}`}
              >
                Resume (PDF & LaTeX)
              </button>
              <button
                onClick={() => { setActiveTab("linkedin"); setCopied(false); }}
                className={`px-5 py-3 text-sm font-semibold border-b-2 transition-all ${activeTab === "linkedin" ? "border-blue-500 text-blue-400" : "border-transparent text-zinc-400 hover:text-zinc-200"}`}
              >
                LinkedIn Summary
              </button>
              <button
                onClick={() => { setActiveTab("readme"); setCopied(false); }}
                className={`px-5 py-3 text-sm font-semibold border-b-2 transition-all ${activeTab === "readme" ? "border-blue-500 text-blue-400" : "border-transparent text-zinc-400 hover:text-zinc-200"}`}
              >
                GitHub README
              </button>
              <button
                onClick={() => { setActiveTab("portfolio"); setCopied(false); }}
                className={`px-5 py-3 text-sm font-semibold border-b-2 transition-all ${activeTab === "portfolio" ? "border-blue-500 text-blue-400" : "border-transparent text-zinc-400 hover:text-zinc-200"}`}
              >
                Developer Portfolio
              </button>
            </div>

            {/* Split Grid */}
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
              {/* Left Column: Output Preview */}
              <div className="lg:col-span-7 bg-zinc-900/20 border border-zinc-900 p-6 rounded-2xl backdrop-blur-md">
                <div className="mb-4 flex items-center justify-between">
                  <h3 className="text-sm font-bold tracking-wider uppercase text-zinc-400 flex items-center gap-2">
                    <span className="h-2.5 w-2.5 rounded-full bg-blue-500" />
                    Format Preview
                  </h3>
                  {activeOutput && (
                    <span className="rounded-full border border-zinc-800 bg-zinc-900/60 px-2.5 py-0.5 text-xs text-zinc-500">
                      Version {activeOutput.version}
                    </span>
                  )}
                </div>

                <div className="max-h-[600px] overflow-y-auto rounded-xl border border-zinc-900 bg-zinc-950/40 p-6">
                  {activeTab === "resume" ? (
                    resumePdfUrl ? (
                      <div>
                        <iframe
                          src={resumePdfUrl}
                          className="w-full h-[600px] rounded-xl border border-zinc-800 bg-zinc-900/40"
                          title="Resume PDF Preview"
                        />
                        <div className="mt-4 flex items-center justify-between text-xs text-zinc-400 bg-zinc-900/40 border border-zinc-800/80 px-4 py-3 rounded-xl">
                          <span>PDF Preview loading slowly?</span>
                          <a
                            href={resumePdfUrl}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-blue-400 hover:text-blue-300 font-semibold flex items-center gap-1"
                          >
                            Open PDF in new tab
                            <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                            </svg>
                          </a>
                        </div>
                      </div>
                    ) : (
                      <div className="flex h-[300px] flex-col items-center justify-center text-center">
                        <div className="h-8 w-8 animate-spin rounded-full border-2 border-zinc-850 border-t-blue-500 mb-3" />
                        <p className="text-xs text-zinc-500">Generating secure PDF download link...</p>
                      </div>
                    )
                  ) : activeOutput ? (
                    <div className="prose prose-invert max-w-none">
                      {renderMarkdown(activeOutput.content)}
                    </div>
                  ) : (
                    <p className="text-sm text-zinc-500">Document data missing.</p>
                  )}
                </div>
              </div>

              {/* Right Column: Code & Actions */}
              <div className="lg:col-span-5 flex flex-col gap-6">
                {/* Control Panel Card */}
                <div className="bg-zinc-900/20 border border-zinc-900 p-6 rounded-2xl backdrop-blur-md">
                  <h3 className="text-sm font-bold tracking-wider uppercase text-zinc-400 mb-4 flex items-center gap-2">
                    <svg className="h-4 w-4 text-blue-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4" />
                    </svg>
                    Control Panel
                  </h3>
                  
                  <div className="flex flex-col gap-3">
                    <button
                      onClick={handleCopyCode}
                      className="w-full flex items-center justify-center gap-2 rounded-xl bg-zinc-900 border border-zinc-800 px-4 py-2.5 text-sm font-semibold text-zinc-200 hover:text-zinc-100 hover:border-zinc-700 transition-all"
                    >
                      {copied ? (
                        <>
                          <svg className="h-4 w-4 text-green-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                          </svg>
                          Copied to Clipboard!
                        </>
                      ) : (
                        <>
                          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 012-2h2a2 2 0 012 2m-5 4h5m-5 4h5m-5 1.5H11" />
                          </svg>
                          Copy Raw Code
                        </>
                      )}
                    </button>

                    {activeTab === "resume" ? (
                      <div className="grid grid-cols-2 gap-3">
                        <button
                          onClick={() => handleDownloadFile("pdf")}
                          className="flex items-center justify-center gap-2 rounded-xl bg-blue-650/10 border border-blue-900/30 px-4 py-2.5 text-sm font-semibold text-blue-400 hover:bg-blue-600/20 transition-all"
                        >
                          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                          </svg>
                          Download PDF
                        </button>
                        <button
                          onClick={() => handleDownloadFile("tex")}
                          className="flex items-center justify-center gap-2 rounded-xl bg-indigo-650/10 border border-indigo-900/30 px-4 py-2.5 text-sm font-semibold text-indigo-400 hover:bg-indigo-600/20 transition-all"
                        >
                          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
                          </svg>
                          Download LaTeX
                        </button>
                      </div>
                    ) : (
                      <button
                        onClick={() => handleDownloadFile()}
                        className="w-full flex items-center justify-center gap-2 rounded-xl bg-blue-650/10 border border-blue-900/30 px-4 py-2.5 text-sm font-semibold text-blue-400 hover:bg-blue-600/20 transition-all"
                      >
                        <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                        </svg>
                        Download Markdown (.md)
                      </button>
                    )}

                    <button
                      onClick={() => { setShowRegenModal(true); setRegenError(null); }}
                      className="w-full mt-2 flex items-center justify-center gap-2 rounded-xl bg-zinc-900 hover:bg-zinc-850 border border-zinc-800 hover:border-zinc-700 px-4 py-2.5 text-sm font-bold text-amber-400 hover:text-amber-300 transition-all"
                    >
                      <svg className="h-4 w-4 text-amber-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                      </svg>
                      Improve / Refine with AI
                    </button>
                  </div>
                </div>

                {/* Source Code Box */}
                <div className="bg-zinc-900/20 border border-zinc-900 p-6 rounded-2xl backdrop-blur-md">
                  <div className="mb-4 flex items-center justify-between">
                    <h3 className="text-sm font-bold tracking-wider uppercase text-zinc-400 flex items-center gap-2">
                      <svg className="h-4 w-4 text-zinc-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
                      </svg>
                      Source Code Content
                    </h3>
                  </div>

                  <div className="relative">
                    <textarea
                      readOnly
                      value={activeOutput ? activeOutput.content : ""}
                      className="w-full h-[380px] rounded-xl border border-zinc-900 bg-zinc-950/60 p-4 font-mono text-xs text-zinc-400 leading-relaxed resize-none focus:outline-none focus:ring-0"
                    />
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}
      </main>

      {/* Regeneration Modal */}
      {showRegenModal && activeOutput && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <div className="w-full max-w-lg rounded-2xl border border-zinc-800 bg-zinc-950 p-6 shadow-2xl animate-in fade-in zoom-in-95 duration-200">
            <div className="flex items-center justify-between border-b border-zinc-900 pb-4 mb-4">
              <h3 className="text-lg font-bold text-zinc-200 flex items-center gap-2">
                <svg className="h-5 w-5 text-amber-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                </svg>
                AI Refiner & Optimizer
              </h3>
              <button
                onClick={() => setShowRegenModal(false)}
                className="text-zinc-500 hover:text-zinc-300 transition-colors"
                disabled={isRegenerating}
              >
                <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <form onSubmit={handleRegenerate} className="space-y-4">
              {regenError && (
                <div className="p-3 text-xs text-rose-400 bg-rose-950/20 border border-rose-900/30 rounded-lg">
                  {regenError}
                </div>
              )}

              {activeTab === "resume" && (
                <div>
                  <label className="block text-xs font-bold text-zinc-400 uppercase tracking-wider mb-2">ATS Target Tier</label>
                  <div className="grid grid-cols-3 gap-2">
                    <button
                      type="button"
                      onClick={() => setAtsMode("experienced")}
                      className={`px-3 py-2 rounded-lg border text-xs font-semibold transition-all ${atsMode === "experienced" ? "bg-blue-600/10 border-blue-500 text-blue-400" : "bg-zinc-900 border-zinc-800 text-zinc-400 hover:text-zinc-300"}`}
                    >
                      Experienced ATS
                    </button>
                    <button
                      type="button"
                      onClick={() => setAtsMode("beginner")}
                      className={`px-3 py-2 rounded-lg border text-xs font-semibold transition-all ${atsMode === "beginner" ? "bg-blue-600/10 border-blue-500 text-blue-400" : "bg-zinc-900 border-zinc-800 text-zinc-400 hover:text-zinc-300"}`}
                    >
                      Beginner ATS
                    </button>
                    <button
                      type="button"
                      onClick={() => setAtsMode("custom")}
                      className={`px-3 py-2 rounded-lg border text-xs font-semibold transition-all ${atsMode === "custom" ? "bg-blue-600/10 border-blue-500 text-blue-400" : "bg-zinc-900 border-zinc-800 text-zinc-400 hover:text-zinc-300"}`}
                    >
                      Custom Mode
                    </button>
                  </div>
                </div>
              )}

              <div>
                <label className="block text-xs font-bold text-zinc-400 uppercase tracking-wider mb-2">
                  Custom Refinement Instructions
                </label>
                <textarea
                  required
                  value={regenInstructions}
                  onChange={(e) => setRegenInstructions(e.target.value)}
                  placeholder="e.g. Highlight my database scaling details, make the bullet points shorter, or adjust the summary description to focus on systems engineering."
                  className="w-full h-32 rounded-xl border border-zinc-800 bg-zinc-900/60 p-4 text-sm text-zinc-200 focus:outline-none focus:border-zinc-700 transition-colors resize-none placeholder:text-zinc-600"
                  disabled={isRegenerating}
                />
              </div>

              <div className="flex items-center justify-end gap-3 pt-4 border-t border-zinc-900">
                <button
                  type="button"
                  onClick={() => setShowRegenModal(false)}
                  className="rounded-xl border border-zinc-800 hover:border-zinc-700 px-4 py-2 text-sm font-semibold text-zinc-400 hover:text-zinc-300 transition-all"
                  disabled={isRegenerating}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isRegenerating}
                  className="flex items-center gap-2 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 px-4 py-2 text-sm font-bold text-white shadow-lg shadow-blue-550/20 transition-all disabled:opacity-50"
                >
                  {isRegenerating ? (
                    <>
                      <div className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
                      Regenerating & Recompiling...
                    </>
                  ) : (
                    <>
                      Apply AI Refinement
                    </>
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
