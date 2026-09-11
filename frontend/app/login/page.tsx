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
      <div className="w-full max-w-md bg-surface-container-lowest border border-outline rounded-xl card-shadow p-stack-lg">
        <div className="flex items-center gap-3 mb-stack-lg">
          <div className="w-12 h-12 rounded-lg bg-primary flex items-center justify-center text-on-primary clay-raised">
            <span className="material-symbols-outlined filled">security</span>
          </div>
          <div>
            <h1 className="font-headline-lg text-headline-lg font-bold text-on-surface">Proxy Busters</h1>
            <p className="font-label-sm text-label-sm text-on-surface-variant">Smart attendance. Less proxy.</p>
          </div>
        </div>

        {cooldownSeconds !== null && (
          <div className="mb-stack-md rounded-md border border-outline bg-secondary-container p-4 text-center clay-recessed">
            <p className="font-body-md text-body-md text-on-secondary-container">
              Session Lock Active — for security, you can&apos;t sign back in for{" "}
              <span className="font-bold">{Math.ceil(cooldownSeconds / 60)} more minute(s)</span> after logging out.
            </p>
          </div>
        )}

        {error && (
          <div className="mb-stack-md rounded-md border border-outline bg-error-container p-3 clay-recessed">
            <p className="font-body-md text-body-md text-on-error-container font-medium">{error}</p>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block font-label-md text-label-md text-on-surface-variant mb-1" htmlFor="email">
              Email
            </label>
            <input
              id="email"
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full h-11 px-3 bg-surface-container-low border border-outline rounded-lg text-body-md font-body-md text-on-surface focus:outline-none focus:border-primary transition-all"
              placeholder="you@college.edu"
            />
          </div>
          <div>
            <label className="block font-label-md text-label-md text-on-surface-variant mb-1" htmlFor="password">
              Password
            </label>
            <input
              id="password"
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full h-11 px-3 bg-surface-container-low border border-outline rounded-lg text-body-md font-body-md text-on-surface focus:outline-none focus:border-primary transition-all"
              placeholder="••••••••"
            />
          </div>
          <button
            type="submit"
            disabled={submitting}
            className="w-full h-11 rounded-lg bg-primary text-on-primary font-label-md text-label-md font-semibold transition-colors disabled:opacity-60"
          >
            {submitting ? "Signing in..." : "Sign In"}
          </button>
        </form>

        <p className="mt-stack-md text-center font-body-md text-body-md text-on-surface-variant">
          New here?{" "}
          <Link href="/register" className="text-tertiary font-semibold hover:underline">
            Create an account
          </Link>
        </p>
      </div>
    </div>
  );
}
