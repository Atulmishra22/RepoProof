"use client";

import React, { useState, useEffect, useRef } from "react";

export interface ProfileFormData {
  email: string;
  target_role: string;
  full_name: string;
  phone: string;
  location: string;
  college: string;
  degree: string;
  cgpa: string;
  graduation_year: string;
  linkedin_url: string;
  portfolio_url: string;
}

interface ProfileCompletionModalProps {
  isOpen: boolean;
  jobId: string;
  jobType: "single" | "multi";
  missingFields?: string[];
  prefillData?: Partial<ProfileFormData>;
  onSuccess: () => void;
  onClose: () => void;
}

const FIELD_LABELS: Record<keyof ProfileFormData, string> = {
  full_name: "Full Name",
  email: "Email Address",
  phone: "Phone Number",
  location: "Location",
  college: "College / University",
  degree: "Degree & Major",
  cgpa: "CGPA / GPA",
  graduation_year: "Graduation Year",
  target_role: "Target Role",
  linkedin_url: "LinkedIn URL",
  portfolio_url: "Portfolio URL",
};

const REQUIRED_FIELDS: (keyof ProfileFormData)[] = [
  "full_name",
  "email",
  "target_role",
];

const API_BASE = "http://localhost:8000/api/v1";

export default function ProfileCompletionModal({
  isOpen,
  jobId,
  jobType,
  missingFields,
  prefillData,
  onSuccess,
  onClose,
}: ProfileCompletionModalProps) {
  const [form, setForm] = useState<ProfileFormData>({
    email: "",
    target_role: "",
    full_name: "",
    phone: "",
    location: "",
    college: "",
    degree: "",
    cgpa: "",
    graduation_year: "",
    linkedin_url: "",
    portfolio_url: "",
  });

  const [autoDetectedFields, setAutoDetectedFields] = useState<Set<keyof ProfileFormData>>(new Set());
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [isVisible, setIsVisible] = useState(false);
  const modalRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (isOpen) {
      const t = setTimeout(() => setIsVisible(true), 10);
      return () => clearTimeout(t);
    } else {
      setIsVisible(false);
    }
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return;

    const fetchProfile = async () => {
      try {
        const res = await fetch(`${API_BASE}/users/me/profile`);
        if (res.ok) {
          const data: Partial<ProfileFormData> = await res.json();
          const detected = new Set<keyof ProfileFormData>();

          setForm((prev) => {
            const merged = { ...prev };
            (Object.keys(FIELD_LABELS) as (keyof ProfileFormData)[]).forEach((key) => {
              const savedVal = (data as ProfileFormData)[key];
              const prefillVal = prefillData?.[key];
              const value = prefillVal ?? savedVal ?? "";
              if (value) {
                merged[key] = value;
                detected.add(key);
              }
            });
            return merged;
          });
          setAutoDetectedFields(detected);
        }
      } catch {
        // Silently fail - user can fill manually
      }
    };

    if (prefillData) {
      const detected = new Set<keyof ProfileFormData>();
      setForm((prev) => {
        const merged = { ...prev };
        (Object.keys(prefillData) as (keyof ProfileFormData)[]).forEach((key) => {
          if (prefillData[key]) {
            merged[key] = prefillData[key]!;
            detected.add(key);
          }
        });
        return merged;
      });
      setAutoDetectedFields(detected);
    }

    fetchProfile();
  }, [isOpen]);

  const handleChange = (key: keyof ProfileFormData, value: string) => {
    setForm((prev) => ({ ...prev, [key]: value }));
    setSubmitError(null);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    for (const field of REQUIRED_FIELDS) {
      if (!form[field].trim()) {
        setSubmitError(`"${FIELD_LABELS[field]}" is required. Please fill it in.`);
        return;
      }
    }
    setIsSubmitting(true);
    setSubmitError(null);
    try {
      const endpoint =
        jobType === "single"
          ? `${API_BASE}/reviews/${jobId}/clarify`
          : `${API_BASE}/users/me/resume/clarify/${jobId}`;
      const res = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(form),
      });
      if (res.ok) {
        onSuccess();
        onClose();
      } else {
        const err = await res.json().catch(() => ({ detail: "Unknown error" }));
        setSubmitError(err.detail || "Failed to submit profile. Please try again.");
      }
    } catch {
      setSubmitError("Failed to connect to the backend. Please check your connection.");
    } finally {
      setIsSubmitting(false);
    }
  };

  if (!isOpen) return null;

  const renderField = (
    key: keyof ProfileFormData,
    placeholder: string,
    type: string = "text",
    fullWidth: boolean = false
  ) => {
    const isRequired = REQUIRED_FIELDS.includes(key);
    const isAutoDetected = autoDetectedFields.has(key);
    const isMissing = missingFields?.includes(key);
    return (
      <div className={fullWidth ? "col-span-2" : ""} key={key}>
        <label
          htmlFor={`pcm-${key}`}
          className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-wider text-zinc-500 mb-1.5"
        >
          {FIELD_LABELS[key]}
          {isRequired && <span className="text-red-400 text-xs">*</span>}
          {isAutoDetected && (
            <span className="inline-flex items-center gap-0.5 rounded-full bg-emerald-950/40 border border-emerald-900/50 px-1.5 py-0.5 text-[8px] font-semibold text-emerald-400 uppercase tracking-wider">
              <svg className="h-2.5 w-2.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
              </svg>
              Auto-detected
            </span>
          )}
          {isMissing && !isAutoDetected && (
            <span className="inline-flex items-center gap-0.5 rounded-full bg-amber-950/40 border border-amber-900/50 px-1.5 py-0.5 text-[8px] font-semibold text-amber-400 uppercase tracking-wider">
              Missing
            </span>
          )}
        </label>
        <input
          id={`pcm-${key}`}
          type={type}
          placeholder={placeholder}
          value={form[key]}
          onChange={(e) => handleChange(key, e.target.value)}
          className={`w-full rounded-lg border bg-zinc-950 px-3.5 py-2.5 text-sm text-zinc-200 placeholder-zinc-600 outline-none transition-all ${
            isRequired && !form[key].trim()
              ? "border-zinc-700 focus:border-red-500/50 focus:ring-1 focus:ring-red-500/20"
              : "border-zinc-800 focus:border-blue-500/60 focus:ring-1 focus:ring-blue-500/20"
          }`}
        />
      </div>
    );
  };

  return (
    <div
      className={`fixed inset-0 z-[60] flex items-center justify-center p-4 transition-all duration-300 ${
        isVisible ? "opacity-100" : "opacity-0"
      }`}
    >
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={onClose} />
      <div
        ref={modalRef}
        className={`relative w-full max-w-2xl max-h-[90vh] overflow-y-auto rounded-2xl border border-zinc-800 bg-zinc-900 shadow-2xl transition-all duration-300 scrollbar-thin scrollbar-thumb-zinc-800 ${
          isVisible ? "translate-y-0 opacity-100" : "translate-y-4 opacity-0"
        }`}
      >
        {/* Header */}
        <div className="sticky top-0 z-10 border-b border-zinc-800 bg-zinc-900/95 backdrop-blur-sm px-6 py-5">
          <div className="flex items-start justify-between">
            <div>
              <h2 className="text-lg font-bold text-zinc-100 flex items-center gap-2.5">
                <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-blue-500/15 border border-blue-500/30">
                  <svg className="h-4 w-4 text-blue-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                  </svg>
                </span>
                Complete Your Profile
              </h2>
              <p className="text-xs text-zinc-400 mt-1.5 leading-relaxed">
                The AI needs a few details to build your resume header and education section.
              </p>
            </div>
            <button
              onClick={onClose}
              className="rounded-lg border border-zinc-800 bg-zinc-950 p-1.5 text-zinc-400 hover:text-zinc-100 hover:border-zinc-700 transition-all ml-4 flex-shrink-0"
            >
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>

        {/* Form Body */}
        <form onSubmit={handleSubmit} className="px-6 pb-6 pt-5 space-y-6">
          {/* Section 1: Personal Details */}
          <div>
            <h3 className="text-[10px] font-bold uppercase tracking-widest text-zinc-500 mb-3 flex items-center gap-2">
              <span className="h-px flex-1 bg-zinc-800" />
              Personal Details
              <span className="h-px flex-1 bg-zinc-800" />
            </h3>
            <div className="grid grid-cols-2 gap-4">
              {renderField("full_name", "e.g. Jane Doe")}
              {renderField("email", "e.g. jane@example.com", "email")}
              {renderField("phone", "e.g. +1 (555) 000-0000", "tel")}
              {renderField("location", "e.g. San Francisco, CA")}
            </div>
          </div>

          <div className="h-px bg-zinc-800/60" />

          {/* Section 2: Education */}
          <div>
            <h3 className="text-[10px] font-bold uppercase tracking-widest text-zinc-500 mb-3 flex items-center gap-2">
              <span className="h-px flex-1 bg-zinc-800" />
              Education
              <span className="h-px flex-1 bg-zinc-800" />
            </h3>
            <div className="grid grid-cols-2 gap-4">
              {renderField("college", "e.g. MIT / IIT Bombay")}
              {renderField("degree", "e.g. B.Tech Computer Science")}
              {renderField("cgpa", "e.g. 8.7 / 10")}
              {renderField("graduation_year", "e.g. 2025")}
            </div>
          </div>

          <div className="h-px bg-zinc-800/60" />

          {/* Section 3: Links & Role */}
          <div>
            <h3 className="text-[10px] font-bold uppercase tracking-widest text-zinc-500 mb-3 flex items-center gap-2">
              <span className="h-px flex-1 bg-zinc-800" />
              Links &amp; Role
              <span className="h-px flex-1 bg-zinc-800" />
            </h3>
            <div className="grid grid-cols-2 gap-4">
              {renderField("target_role", "e.g. Senior Software Engineer", "text", true)}
              {renderField("linkedin_url", "e.g. https://linkedin.com/in/janedoe", "url")}
              {renderField("portfolio_url", "e.g. https://janedoe.dev", "url")}
            </div>
          </div>

          {submitError && (
            <div className="rounded-lg border border-red-900/50 bg-red-950/20 p-3.5 flex items-start gap-2.5">
              <svg className="h-4 w-4 text-red-400 shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
              <p className="text-xs text-red-300 leading-relaxed">{submitError}</p>
            </div>
          )}

          <div className="flex items-center justify-between pt-1">
            <p className="text-[10px] text-zinc-500">
              <span className="text-red-400">*</span> Required fields
            </p>
            <button
              type="submit"
              disabled={isSubmitting}
              className="flex items-center gap-2 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 disabled:opacity-60 disabled:cursor-not-allowed px-6 py-2.5 text-sm font-bold text-white transition-all duration-200 shadow-lg shadow-blue-900/20"
            >
              {isSubmitting ? (
                <>
                  <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
                  </svg>
                  Submitting...
                </>
              ) : (
                <>Generate Resume &rarr;</>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
