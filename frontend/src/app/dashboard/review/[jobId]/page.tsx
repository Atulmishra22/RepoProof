"use client";

import React, { use, useEffect, useState, useRef } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useReviewStore, Fact } from "../../reviewStore";
import { 
  ArrowLeft, 
  Trash2, 
  Plus, 
  Send, 
  Sparkles, 
  Check, 
  Loader2, 
  Code, 
  FileText, 
  Briefcase, 
  AlertCircle 
} from "lucide-react";

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

const CATEGORIES = [
  { value: "technology_used", label: "Technology Used" },
  { value: "architecture_pattern", label: "Architecture Pattern" },
  { value: "complexity_metric", label: "Complexity Metric" },
  { value: "contribution", label: "Contribution" },
  { value: "performance_optimization", label: "Performance Optimization" },
  { value: "security_hardening", label: "Security Hardening" },
  { value: "cost_saving", label: "Cost Saving" }
];

export default function ReviewPage({ params }: { params: Promise<{ jobId: string }> }) {
  const router = useRouter();
  const { jobId } = use(params);
  
  const {
    facts,
    suggestedQuestions,
    chatHistory,
    isLoadingFacts,
    isSendingMessage,
    isResuming,
    error: storeError,
    fetchFacts,
    updateFact,
    deleteFact,
    addFact,
    sendChatMessage,
    submitReview,
    clearStore
  } = useReviewStore();

  const [repoName, setRepoName] = useState<string>("");
  const [repoOwner, setRepoOwner] = useState<string>("");
  const [jobStatus, setJobStatus] = useState<string>("");
  const [localError, setLocalError] = useState<string | null>(null);
  const [chatInput, setChatInput] = useState("");
  const chatEndRef = useRef<HTMLDivElement>(null);

  // Load Job and Repository details first, then fetch facts
  useEffect(() => {
    let active = true;
    
    async function loadJobDetails() {
      try {
        const res = await fetch(`${BACKEND_URL}/api/v1/repositories/placeholder/analysis/${jobId}`);
        if (!res.ok) {
          throw new Error("Could not load analysis job details.");
        }
        const jobData = await res.json();
        if (!active) return;
        
        setJobStatus(jobData.status);
        
        // Now fetch repo metadata
        const reposRes = await fetch(`${BACKEND_URL}/api/v1/repositories?username=Atulmishra22`);
        if (reposRes.ok) {
          const reposData = await reposRes.json();
          const targetRepo = reposData.repositories.find(
            (r: any) => r.id === jobData.repository_id
          );
          if (targetRepo && active) {
            setRepoName(targetRepo.name);
            setRepoOwner(targetRepo.owner);
          }
        }
        
        // Fetch facts using the repository_id
        await fetchFacts(jobData.repository_id);
      } catch (err: any) {
        if (active) {
          setLocalError(err.message || "Failed to load review page context");
        }
      }
    }
    
    loadJobDetails();
    
    return () => {
      active = false;
      clearStore();
    };
  }, [jobId, fetchFacts, clearStore]);

  // Scroll to bottom of chat
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chatHistory, isSendingMessage]);

  const handleAddFact = () => {
    const newFact: Fact = {
      category: "technology_used",
      claim: "Implemented robust features using high-performance patterns.",
      source_file: "src/main.ts",
      snippet: "// new contribution",
      ats_impact: "Demonstrates capability to engineer production-ready code."
    };
    addFact(newFact);
  };

  const handleChatSend = async (text: string) => {
    if (!text.trim()) return;
    setChatInput("");
    await sendChatMessage(jobId, text);
  };

  const handleApprove = async () => {
    await submitReview(jobId, () => {
      router.push("/dashboard");
    });
  };

  if (isLoadingFacts) {
    return (
      <div className="min-h-screen bg-[#0d0e12] flex flex-col items-center justify-center text-white">
        <Loader2 className="h-10 w-10 animate-spin text-purple-500 mb-4" />
        <h2 className="text-xl font-medium tracking-wide">Loading facts extraction dashboard...</h2>
        <p className="text-gray-400 mt-2 text-sm">Reviewing codebase checkpoints from PostgresSaver...</p>
      </div>
    );
  }

  const activeError = localError || storeError;

  return (
    <div className="min-h-screen bg-[#0a0b0d] text-white flex flex-col font-sans">
      {/* Background decoration glows */}
      <div className="absolute top-0 left-1/4 w-[500px] h-[500px] bg-purple-500/10 rounded-full blur-[120px] pointer-events-none" />
      <div className="absolute bottom-0 right-1/4 w-[500px] h-[500px] bg-blue-500/5 rounded-full blur-[120px] pointer-events-none" />

      {/* Header */}
      <header className="border-b border-gray-800 bg-[#0f1115]/80 backdrop-blur-md sticky top-0 z-50 px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <button 
            onClick={() => router.push("/dashboard")}
            className="p-2 hover:bg-gray-800 rounded-lg transition-colors border border-gray-800"
          >
            <ArrowLeft className="h-4 w-4" />
          </button>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-xl font-bold tracking-tight">
                Review extracted claims
              </h1>
              <span className="px-2 py-0.5 rounded text-[11px] font-semibold bg-purple-500/20 text-purple-300 border border-purple-500/30 uppercase">
                Awaiting Developer Review
              </span>
            </div>
            <p className="text-xs text-gray-400 mt-0.5">
              Repository: <span className="text-gray-200 font-mono">{repoOwner}/{repoName}</span>
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <button 
            onClick={() => router.push("/dashboard")}
            className="px-4 py-2 text-sm text-gray-400 hover:text-white transition-colors"
          >
            Cancel
          </button>
          <button 
            onClick={handleApprove}
            disabled={isResuming}
            className="flex items-center gap-2 px-5 py-2 rounded-lg bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 font-semibold text-sm transition-all duration-200 shadow-lg shadow-purple-500/20 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isResuming ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Resuming...
              </>
            ) : (
              <>
                <Check className="h-4 w-4" />
                Approve & Complete Analysis
              </>
            )}
          </button>
        </div>
      </header>

      {/* Error Alert */}
      {activeError && (
        <div className="mx-6 mt-6 p-4 bg-red-900/30 border border-red-500/40 rounded-xl flex items-start gap-3">
          <AlertCircle className="h-5 w-5 text-red-400 flex-shrink-0 mt-0.5" />
          <div>
            <h4 className="font-semibold text-red-300 text-sm">System Error Encountered</h4>
            <p className="text-red-400 text-xs mt-1">{activeError}</p>
          </div>
        </div>
      )}

      {/* Workspace Grid */}
      <main className="flex-1 grid grid-cols-1 lg:grid-cols-12 gap-6 p-6 h-[calc(100vh-80px)] overflow-hidden">
        {/* Left Side: Facts Editor (7 Cols) */}
        <section className="lg:col-span-7 flex flex-col h-full bg-[#0f1115]/50 border border-gray-800 rounded-2xl overflow-hidden backdrop-blur-sm">
          <div className="p-4 border-b border-gray-800 flex items-center justify-between bg-[#13161c]/40">
            <div>
              <h3 className="font-semibold text-sm">Candidate Claims & Facts</h3>
              <p className="text-[11px] text-gray-400 mt-0.5">Edit, customize or remove facts generated from the codebase</p>
            </div>
            <button 
              onClick={handleAddFact}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-gray-700 bg-gray-850 hover:bg-gray-800 text-xs font-semibold transition-colors"
            >
              <Plus className="h-3.5 w-3.5 text-purple-400" />
              Add Custom Claim
            </button>
          </div>

          {/* Facts Scroll Area */}
          <div className="flex-1 overflow-y-auto p-6 space-y-6 scrollbar-thin">
            {facts.length === 0 ? (
              <div className="h-64 border border-dashed border-gray-800 rounded-2xl flex flex-col items-center justify-center text-gray-500">
                <FileText className="h-10 w-10 mb-2 opacity-50" />
                <p className="text-sm">No candidate facts extracted yet.</p>
                <button 
                  onClick={handleAddFact} 
                  className="mt-3 text-xs text-purple-400 hover:text-purple-300 underline"
                >
                  Create one manually
                </button>
              </div>
            ) : (
              facts.map((fact, index) => (
                <div 
                  key={index} 
                  className="relative p-5 bg-[#14161f]/60 rounded-xl border border-gray-800 hover:border-gray-750 transition-all duration-200 group"
                >
                  {/* Delete Button */}
                  <button 
                    onClick={() => deleteFact(index)}
                    className="absolute top-4 right-4 p-1.5 hover:bg-red-950/40 text-gray-400 hover:text-red-400 rounded-lg border border-transparent hover:border-red-900/30 transition-colors opacity-0 group-hover:opacity-100"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {/* Category Selector */}
                    <div>
                      <label className="block text-[10px] font-semibold text-purple-400 uppercase tracking-wider mb-1.5">
                        Category
                      </label>
                      <select 
                        value={fact.category}
                        onChange={(e) => updateFact(index, { category: e.target.value })}
                        className="w-full bg-[#0a0b0d] border border-gray-800 rounded-lg px-3 py-1.5 text-xs text-gray-200 focus:outline-none focus:border-purple-500 transition-colors"
                      >
                        {CATEGORIES.map((cat) => (
                          <option key={cat.value} value={cat.value}>{cat.label}</option>
                        ))}
                      </select>
                    </div>

                    {/* Source File Citation */}
                    <div>
                      <label className="block text-[10px] font-semibold text-purple-400 uppercase tracking-wider mb-1.5">
                        Source File Reference
                      </label>
                      <div className="relative">
                        <Code className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-gray-500" />
                        <input 
                          type="text" 
                          value={fact.source_file}
                          onChange={(e) => updateFact(index, { source_file: e.target.value })}
                          className="w-full bg-[#0a0b0d] border border-gray-800 rounded-lg pl-8 pr-3 py-1.5 text-xs text-gray-200 font-mono focus:outline-none focus:border-purple-500 transition-colors"
                        />
                      </div>
                    </div>

                    {/* Claim Text (Resume Bullet Point) */}
                    <div className="md:col-span-2">
                      <label className="block text-[10px] font-semibold text-purple-400 uppercase tracking-wider mb-1.5">
                        Claim Statement (Resume Bullet Point)
                      </label>
                      <textarea 
                        rows={2}
                        value={fact.claim}
                        onChange={(e) => updateFact(index, { claim: e.target.value })}
                        className="w-full bg-[#0a0b0d] border border-gray-800 rounded-lg p-3 text-xs text-gray-200 focus:outline-none focus:border-purple-500 transition-colors resize-none leading-relaxed"
                      />
                    </div>

                    {/* ATS Impact Card */}
                    <div className="md:col-span-2">
                      <label className="block text-[10px] font-semibold text-purple-400 uppercase tracking-wider mb-1.5 flex items-center gap-1">
                        <Briefcase className="h-3 w-3" />
                        ATS Relevance / Impact explanation
                      </label>
                      <textarea 
                        rows={2}
                        value={fact.ats_impact}
                        onChange={(e) => updateFact(index, { ats_impact: e.target.value })}
                        className="w-full bg-[#0a0b0d] border border-gray-800 rounded-lg p-3 text-xs text-gray-300 focus:outline-none focus:border-purple-500 transition-colors resize-none leading-relaxed italic"
                      />
                    </div>

                    {/* Code Snippet Evidence */}
                    <div className="md:col-span-2">
                      <label className="block text-[10px] font-semibold text-purple-400 uppercase tracking-wider mb-1.5">
                        Code Evidence Snippet
                      </label>
                      <textarea 
                        rows={3}
                        value={fact.snippet}
                        onChange={(e) => updateFact(index, { snippet: e.target.value })}
                        className="w-full bg-[#08090c] border border-gray-850 rounded-lg p-3 text-[11px] text-emerald-400 font-mono focus:outline-none focus:border-purple-500 transition-colors resize-none leading-5"
                      />
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        </section>

        {/* Right Side: AI Refiner Chat (5 Cols) */}
        <section className="lg:col-span-5 flex flex-col h-full bg-[#0f1115]/50 border border-gray-800 rounded-2xl overflow-hidden backdrop-blur-sm">
          <div className="p-4 border-b border-gray-800 flex items-center justify-between bg-[#13161c]/40">
            <div className="flex items-center gap-2">
              <Sparkles className="h-4 w-4 text-purple-400 animate-pulse" />
              <h3 className="font-semibold text-sm">AI pairing refiner</h3>
            </div>
            <span className="text-[10px] bg-blue-500/10 text-blue-300 border border-blue-500/20 px-2 py-0.5 rounded font-mono">
              gpt-4o-mini
            </span>
          </div>

          {/* Messages Area */}
          <div className="flex-1 overflow-y-auto p-4 space-y-4 scrollbar-thin flex flex-col">
            {chatHistory.map((msg, index) => (
              <div 
                key={index}
                className={`max-w-[85%] rounded-2xl p-4 text-xs leading-relaxed ${
                  msg.role === "user" 
                    ? "bg-purple-600 text-white rounded-br-none self-end shadow-md"
                    : "bg-[#161a22] text-gray-200 border border-gray-800 rounded-bl-none self-start"
                }`}
              >
                <p className="whitespace-pre-line">{msg.content}</p>
              </div>
            ))}
            
            {isSendingMessage && (
              <div className="bg-[#161a22] text-gray-400 border border-gray-800 rounded-2xl rounded-bl-none p-4 text-xs self-start flex items-center gap-2">
                <Loader2 className="h-3.5 w-3.5 animate-spin text-purple-400" />
                <span>AI partner is reviewing codebase files...</span>
              </div>
            )}
            <div ref={chatEndRef} />
          </div>

          {/* Suggestion Chips */}
          {suggestedQuestions.length > 0 && (
            <div className="px-4 py-2.5 bg-[#12151c]/60 border-t border-gray-850">
              <p className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider mb-2">Suggested Code Questions</p>
              <div className="flex flex-wrap gap-2 max-h-20 overflow-y-auto pr-1">
                {suggestedQuestions.map((q, idx) => (
                  <button
                    key={idx}
                    onClick={() => handleChatSend(q)}
                    disabled={isSendingMessage}
                    className="text-[10px] text-purple-300 bg-purple-500/10 border border-purple-500/20 hover:bg-purple-500/20 px-2.5 py-1 rounded-full text-left transition-colors truncate max-w-full disabled:opacity-50"
                    title={q}
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Message Input */}
          <div className="p-4 border-t border-gray-800 bg-[#13161c]/40">
            <div className="relative">
              <input 
                type="text" 
                placeholder="Ask AI to edit, draft claims, or explain files..."
                value={chatInput}
                onChange={(e) => setChatInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleChatSend(chatInput)}
                disabled={isSendingMessage}
                className="w-full bg-[#0a0b0d] border border-gray-800 rounded-xl pl-4 pr-12 py-3 text-xs text-gray-200 placeholder-gray-500 focus:outline-none focus:border-purple-500 transition-colors disabled:opacity-50"
              />
              <button 
                onClick={() => handleChatSend(chatInput)}
                disabled={isSendingMessage || !chatInput.trim()}
                className="absolute right-2 top-2 p-2 bg-purple-600 hover:bg-purple-500 disabled:bg-gray-800 disabled:text-gray-600 text-white rounded-lg transition-colors"
              >
                <Send className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}
