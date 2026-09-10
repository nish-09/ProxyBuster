"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { ApiError } from "@/lib/api";

export default function LoginPage() {
  const { login } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [cooldownSeconds, setCooldownSeconds] = useState<number | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setCooldownSeconds(null);
    setSubmitting(true);
    try {
      const me = await login(email, password);
      router.push(me.role === "student" ? "/student/dashboard" : me.role === "admin" ? "/admin/dashboard" : "/professor/dashboard");
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 423 && err.remainingSeconds !== undefined) {
          setCooldownSeconds(err.remainingSeconds);
        } else {
          setError(err.message);
        }
      } else {
        setError("Something went wrong. Please try again.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-background p-6">
      <div className="w-full max-w-md bg-surface border-2 border-outline rounded-lg shadow-[6px_6px_0_#111111] p-stack-lg">
        <div className="flex items-center gap-3 mb-stack-lg">
          <div className="w-11 h-11 rounded-md bg-primary border-2 border-outline flex items-center justify-center text-on-primary">
            <span className="material-symbols-outlined filled">security</span>
          </div>
          <div>
            <h1 className="font-headline-lg text-headline-lg font-extrabold text-on-surface">Proxy Busters</h1>
            <p className="font-label-sm text-label-sm text-on-surface-variant uppercase tracking-wider">Sign in to continue</p>
          </div>
        </div>

        {cooldownSeconds !== null && (
          <div className="mb-stack-md rounded-md border-2 border-outline bg-secondary-container p-4 text-center">
            <p className="font-body-md text-body-md text-on-surface">
              Session Lock Active — for security, you can&apos;t sign back in for{" "}
              <span className="font-extrabold">{Math.ceil(cooldownSeconds / 60)} more minute(s)</span> after logging out.
            </p>
          </div>
        )}

        {error && (
          <div className="mb-stack-md rounded-md border-2 border-outline bg-error-container p-3">
            <p className="font-body-md text-body-md text-on-error-container font-semibold">{error}</p>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block font-label-md text-label-md text-on-surface-variant mb-1" htmlFor="email">
              EMAIL
            </label>
            <input
              id="email"
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full h-11 px-3 bg-white border-2 border-outline rounded-md text-body-md font-body-md focus:ring-2 focus:ring-primary/30 focus:border-primary transition-all"
              placeholder="you@college.edu"
            />
          </div>
          <div>
            <label className="block font-label-md text-label-md text-on-surface-variant mb-1" htmlFor="password">
              PASSWORD
            </label>
            <input
              id="password"
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full h-11 px-3 bg-white border-2 border-outline rounded-md text-body-md font-body-md focus:ring-2 focus:ring-primary/30 focus:border-primary transition-all"
              placeholder="••••••••"
            />
          </div>
          <button
            type="submit"
            disabled={submitting}
            className="w-full h-11 rounded-md bg-primary text-on-primary font-label-md text-label-md font-bold border-2 border-outline transition-colors disabled:opacity-60"
          >
            {submitting ? "Signing in..." : "Sign In"}
          </button>
        </form>

        <p className="mt-stack-md text-center font-body-md text-body-md text-on-surface-variant">
          New here?{" "}
          <Link href="/register" className="text-primary font-bold hover:underline">
            Create an account
          </Link>
        </p>
      </div>
    </div>
  );
}
