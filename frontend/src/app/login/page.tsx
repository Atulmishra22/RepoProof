"use client";

import React, { useState } from "react";
import { signIn } from "next-auth/react";
import { useRouter } from "next/navigation";
import { Sparkles, Mail, ShieldAlert, Layers, Lock, User, CheckCircle } from "lucide-react";

export default function LoginPage() {
  const router = useRouter();
  const [isRegistering, setIsRegistering] = useState(false);
  
  // Fields
  const [email, setEmail] = useState("developer@repoproof.com");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [name, setName] = useState("Developer User");
  const [tier, setTier] = useState("FREE");
  
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  const handleGithubLogin = async () => {
    setLoading(true);
    setError(null);
    setSuccessMsg(null);
    try {
      await signIn("github", { callbackUrl: "/dashboard" });
    } catch (err: any) {
      setError(err.message || "Failed to log in with GitHub.");
      setLoading(false);
    }
  };

  const handleDeveloperAuth = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setSuccessMsg(null);

    if (isRegistering) {
      if (password !== confirmPassword) {
        setError("Passwords do not match.");
        setLoading(false);
        return;
      }
      if (password.length < 6) {
        setError("Password must be at least 6 characters long.");
        setLoading(false);
        return;
      }

      try {
        const response = await fetch("/api/auth/register", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            email,
            password,
            name,
            subscription_tier: tier,
          }),
        });

        const data = await response.json();
        if (data.success) {
          setSuccessMsg("Registration successful! You can now log in.");
          setIsRegistering(false);
          setPassword("");
          setConfirmPassword("");
        } else {
          setError(data.error || "Failed to register developer account.");
        }
      } catch (err: any) {
        setError("Connection to registration API failed.");
      } finally {
        setLoading(false);
      }
    } else {
      // Login
      try {
        const response = await fetch("/api/auth/mock-login", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            email,
            password,
            subscription_tier: tier,
          }),
        });

        const data = await response.json();
        if (data.success) {
          router.push("/dashboard");
          router.refresh();
        } else {
          setError(data.error || "Failed to log in.");
        }
      } catch (err: any) {
        setError("Connection to login API failed.");
      } finally {
        setLoading(false);
      }
    }
  };

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-zinc-950 text-zinc-100 font-sans antialiased selection:bg-blue-600/30 selection:text-blue-200 overflow-hidden relative">
      {/* Background glow effects */}
      <div className="absolute top-1/4 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[500px] h-[500px] bg-gradient-to-tr from-blue-500/10 to-indigo-500/10 rounded-full blur-[120px] pointer-events-none" />
      <div className="absolute bottom-1/4 left-1/3 w-[300px] h-[300px] bg-gradient-to-br from-cyan-500/5 to-purple-500/5 rounded-full blur-[100px] pointer-events-none" />

      <main className="relative z-10 w-full max-w-md px-6 py-12">
        {/* Brand Header */}
        <div className="flex flex-col items-center text-center mb-8">
          <div className="inline-flex items-center justify-center h-12 w-12 rounded-2xl bg-gradient-to-tr from-blue-600 to-indigo-600 shadow-md shadow-blue-500/25 mb-4">
            <Sparkles className="h-6 w-6 text-white" />
          </div>
          <h1 className="text-3xl font-extrabold tracking-tight text-white mb-2">
            {isRegistering ? "Register for " : "Sign in to "}
            <span className="bg-clip-text text-transparent bg-gradient-to-r from-blue-400 via-indigo-400 to-cyan-400">
              RepoProof
            </span>
          </h1>
          <p className="text-zinc-400 text-xs">
            Advanced Repository Intelligence Platform
          </p>
        </div>

        {/* Login Card */}
        <div className="rounded-2xl border border-zinc-900 bg-zinc-900/30 backdrop-blur-xl p-8 shadow-2xl">
          {error && (
            <div className="mb-6 flex items-start gap-3 rounded-xl border border-red-500/20 bg-red-500/10 p-4 text-xs text-red-400">
              <ShieldAlert className="h-4 w-4 shrink-0 animate-bounce" />
              <div>
                <span className="font-semibold text-white">Authentication Error</span>
                <p className="mt-1 leading-relaxed">{error}</p>
              </div>
            </div>
          )}

          {successMsg && (
            <div className="mb-6 flex items-start gap-3 rounded-xl border border-emerald-500/20 bg-emerald-500/10 p-4 text-xs text-emerald-400">
              <CheckCircle className="h-4 w-4 shrink-0" />
              <div>
                <span className="font-semibold text-white">Success</span>
                <p className="mt-1 leading-relaxed">{successMsg}</p>
              </div>
            </div>
          )}

          {/* GitHub OAuth Button */}
          {!isRegistering && (
            <>
              <button
                onClick={handleGithubLogin}
                disabled={loading}
                className="flex h-11 w-full items-center justify-center gap-3 rounded-xl bg-white text-zinc-950 font-semibold hover:bg-zinc-100 active:scale-[0.98] transition-all duration-200 shadow-lg disabled:opacity-50 disabled:pointer-events-none cursor-pointer"
              >
                <svg className="h-5 w-5 fill-current" viewBox="0 0 24 24">
                  <path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z" />
                </svg>
                <span>Continue with GitHub</span>
              </button>

              {/* Divider */}
              <div className="relative my-6 flex items-center justify-center">
                <div className="absolute inset-0 flex items-center">
                  <div className="w-full border-t border-zinc-900" />
                </div>
                <span className="relative z-10 px-3 bg-zinc-950 text-[10px] uppercase font-bold tracking-widest text-zinc-600">
                  Local Credentials
                </span>
              </div>
            </>
          )}

          {/* Credentials / Developer Form */}
          <form onSubmit={handleDeveloperAuth} className="space-y-4">
            {isRegistering && (
              <div>
                <label htmlFor="name" className="block text-[10px] font-bold uppercase tracking-wider text-zinc-500 mb-1.5">
                  Full Name
                </label>
                <div className="relative">
                  <span className="absolute inset-y-0 left-0 flex items-center pl-3.5 pointer-events-none">
                    <User className="h-4 w-4 text-zinc-600" />
                  </span>
                  <input
                    type="text"
                    id="name"
                    required
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    className="block w-full h-11 pl-10 pr-4 rounded-xl border border-zinc-900 bg-zinc-900/10 focus:border-blue-500/50 focus:ring-1 focus:ring-blue-500/50 text-sm placeholder-zinc-600 transition-all outline-none"
                    placeholder="Jane Doe"
                  />
                </div>
              </div>
            )}

            <div>
              <label htmlFor="email" className="block text-[10px] font-bold uppercase tracking-wider text-zinc-500 mb-1.5">
                Developer Email
              </label>
              <div className="relative">
                <span className="absolute inset-y-0 left-0 flex items-center pl-3.5 pointer-events-none">
                  <Mail className="h-4 w-4 text-zinc-600" />
                </span>
                <input
                  type="email"
                  id="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="block w-full h-11 pl-10 pr-4 rounded-xl border border-zinc-900 bg-zinc-900/10 focus:border-blue-500/50 focus:ring-1 focus:ring-blue-500/50 text-sm placeholder-zinc-600 transition-all outline-none"
                  placeholder="name@repoproof.com"
                />
              </div>
            </div>

            <div>
              <label htmlFor="pass" className="block text-[10px] font-bold uppercase tracking-wider text-zinc-500 mb-1.5">
                Password
              </label>
              <div className="relative">
                <span className="absolute inset-y-0 left-0 flex items-center pl-3.5 pointer-events-none">
                  <Lock className="h-4 w-4 text-zinc-600" />
                </span>
                <input
                  type="password"
                  id="pass"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="block w-full h-11 pl-10 pr-4 rounded-xl border border-zinc-900 bg-zinc-900/10 focus:border-blue-500/50 focus:ring-1 focus:ring-blue-500/50 text-sm placeholder-zinc-600 transition-all outline-none"
                  placeholder={isRegistering ? "Choose a password" : "devpass"}
                />
              </div>
            </div>

            {isRegistering && (
              <div>
                <label htmlFor="confirmPass" className="block text-[10px] font-bold uppercase tracking-wider text-zinc-500 mb-1.5">
                  Confirm Password
                </label>
                <div className="relative">
                  <span className="absolute inset-y-0 left-0 flex items-center pl-3.5 pointer-events-none">
                    <Lock className="h-4 w-4 text-zinc-600" />
                  </span>
                  <input
                    type="password"
                    id="confirmPass"
                    required
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    className="block w-full h-11 pl-10 pr-4 rounded-xl border border-zinc-900 bg-zinc-900/10 focus:border-blue-500/50 focus:ring-1 focus:ring-blue-500/50 text-sm placeholder-zinc-600 transition-all outline-none"
                    placeholder="Verify password"
                  />
                </div>
              </div>
            )}

            <div>
              <label htmlFor="tier" className="block text-[10px] font-bold uppercase tracking-wider text-zinc-500 mb-1.5">
                Subscription Tier
              </label>
              <div className="relative">
                <span className="absolute inset-y-0 left-0 flex items-center pl-3.5 pointer-events-none">
                  <Layers className="h-4 w-4 text-zinc-600" />
                </span>
                <select
                  id="tier"
                  value={tier}
                  onChange={(e) => setTier(e.target.value)}
                  className="block w-full h-11 pl-10 pr-4 rounded-xl border border-zinc-900 bg-zinc-900/10 focus:border-blue-500/50 focus:ring-1 focus:ring-blue-500/50 text-sm transition-all outline-none appearance-none cursor-pointer"
                >
                  <option value="FREE" className="bg-zinc-950">Free Tier (5 scans/hour)</option>
                  <option value="PRO" className="bg-zinc-950">Pro Tier (100 scans/hour)</option>
                </select>
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="flex h-11 w-full items-center justify-center rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 font-semibold text-white hover:from-blue-500 hover:to-indigo-500 active:scale-[0.98] transition-all duration-200 shadow-lg shadow-blue-900/20 disabled:opacity-50 disabled:pointer-events-none mt-2 cursor-pointer"
            >
              {loading ? "Signing in..." : isRegistering ? "Register Developer Account" : "Developer Login"}
            </button>
          </form>

          {/* Form Toggle Links */}
          <div className="mt-6 text-center">
            <button
              type="button"
              onClick={() => {
                setIsRegistering(!isRegistering);
                setError(null);
                setSuccessMsg(null);
                setPassword("");
                setConfirmPassword("");
              }}
              className="text-xs text-blue-400 hover:text-blue-300 transition-colors font-medium cursor-pointer"
            >
              {isRegistering
                ? "Already have an account? Sign in here"
                : "Create a local developer account"}
            </button>
          </div>
        </div>

        {/* Footer info */}
        <p className="mt-8 text-center text-xs text-zinc-600">
          Secure sandbox environment. Database-backed credentials session bypass logic enabled.
        </p>
      </main>
    </div>
  );
}
