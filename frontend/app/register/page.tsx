"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { ApiError, type UserRole } from "@/lib/api";

export default function RegisterPage() {
  const { register, login } = useAuth();
  const router = useRouter();

  const [role, setRole] = useState<UserRole>("student");
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [rollNumber, setRollNumber] = useState("");
  const [program, setProgram] = useState("");
  const [semester, setSemester] = useState("1");
  const [department, setDepartment] = useState("");
  const [inviteCode, setInviteCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await register({
        email,
        password,
        full_name: fullName,
        role,
        roll_number: role === "student" ? rollNumber : undefined,
        program: role === "student" ? program : undefined,
        semester: role === "student" ? Number(semester) : undefined,
        department: role === "professor" ? department : undefined,
        invite_code: role === "professor" ? inviteCode : undefined,
      });
      const me = await login(email, password);
      router.push(me.role === "student" ? "/student/dashboard" : "/professor/dashboard");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  const inputClass =
    "w-full h-10 px-3 bg-surface-container-low border border-outline rounded-md text-body-md font-body-md text-on-surface focus:outline-none focus:border-primary transition-all";
  const labelClass = "block font-label-md text-label-md text-on-surface-variant mb-1";

  return (
    <div className="min-h-screen flex items-center justify-center bg-background p-6 py-12">
      <div className="w-full max-w-md bg-surface-container-lowest border border-outline rounded-lg card-shadow p-stack-lg">
        <div className="flex items-center gap-3 mb-stack-lg">
          <div className="w-11 h-11 rounded-md bg-primary border border-outline shadow-[inset_0_1px_0_rgba(255,255,255,0.2),0_2px_5px_rgba(0,0,0,0.4)] flex items-center justify-center text-on-primary">
            <span className="material-symbols-outlined filled">security</span>
          </div>
          <div>
            <h1 className="font-headline-lg text-headline-lg font-bold text-on-surface">Proxy Busters</h1>
            <p className="font-label-sm text-label-sm text-on-surface-variant">Create your account</p>
          </div>
        </div>

        <div className="mb-stack-md grid grid-cols-2 gap-2 rounded-md bg-surface-container-low p-1 border border-outline shadow-[inset_0_1px_3px_rgba(0,0,0,0.3)]">
          {(["student", "professor"] as UserRole[]).map((r) => (
            <button
              key={r}
              type="button"
              onClick={() => setRole(r)}
              className={`py-2 rounded font-label-md text-label-md capitalize transition-all ${
                role === r
                  ? "bg-surface-container-high text-on-surface font-semibold border border-outline shadow-[inset_0_1px_0_rgba(255,255,255,0.06)]"
                  : "text-on-surface-variant border border-transparent"
              }`}
            >
              {r}
            </button>
          ))}
        </div>

        {error && (
          <div className="mb-stack-md rounded-md border border-outline bg-error-container p-3 shadow-[inset_0_1px_3px_rgba(0,0,0,0.3)]">
            <p className="font-body-md text-body-md text-on-error-container font-medium">{error}</p>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className={labelClass} htmlFor="full_name">
              Full name
            </label>
            <input id="full_name" required value={fullName} onChange={(e) => setFullName(e.target.value)} className={inputClass} />
          </div>
          <div>
            <label className={labelClass} htmlFor="email">
              Email
            </label>
            <input id="email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} className={inputClass} />
          </div>
          <div>
            <label className={labelClass} htmlFor="password">
              Password
            </label>
            <input
              id="password"
              type="password"
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className={inputClass}
            />
          </div>

          {role === "student" ? (
            <>
              <div>
                <label className={labelClass} htmlFor="roll_number">
                  Roll number
                </label>
                <input id="roll_number" required value={rollNumber} onChange={(e) => setRollNumber(e.target.value)} className={inputClass} />
              </div>
              <div>
                <label className={labelClass} htmlFor="program">
                  Program
                </label>
                <input
                  id="program"
                  required
                  value={program}
                  onChange={(e) => setProgram(e.target.value)}
                  placeholder="B.Tech Computer Science"
                  className={inputClass}
                />
              </div>
              <div>
                <label className={labelClass} htmlFor="semester">
                  Semester
                </label>
                <input
                  id="semester"
                  type="number"
                  min={1}
                  max={12}
                  required
                  value={semester}
                  onChange={(e) => setSemester(e.target.value)}
                  className={inputClass}
                />
              </div>
            </>
          ) : (
            <>
              <div>
                <label className={labelClass} htmlFor="department">
                  Department
                </label>
                <input id="department" required value={department} onChange={(e) => setDepartment(e.target.value)} className={inputClass} />
              </div>
              <div>
                <label className={labelClass} htmlFor="invite_code">
                  Professor invite code
                </label>
                <input
                  id="invite_code"
                  required
                  value={inviteCode}
                  onChange={(e) => setInviteCode(e.target.value)}
                  placeholder="Provided by your institution admin"
                  className={inputClass}
                />
              </div>
            </>
          )}

          <button
            type="submit"
            disabled={submitting}
            className="w-full h-10 rounded-md bg-primary text-on-primary font-label-md text-label-md font-semibold border border-outline transition-colors disabled:opacity-60"
          >
            {submitting ? "Creating account..." : "Create Account"}
          </button>
        </form>

        <p className="mt-stack-md text-center font-body-md text-body-md text-on-surface-variant">
          Already have an account?{" "}
          <Link href="/login" className="text-tertiary font-semibold hover:underline">
            Sign in
          </Link>
        </p>
      </div>
    </div>
  );
}
