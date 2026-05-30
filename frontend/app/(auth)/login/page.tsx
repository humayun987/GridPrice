"use client";

import { useState } from "react";
import { signIn } from "next-auth/react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleLogin = async () => {
    setLoading(true);
    setError("");
    const result = await signIn("credentials", {
      email,
      password,
      redirect: false,
    });
    setLoading(false);
    if (result?.error) {
      setError("Invalid credentials or account not approved yet.");
    } else {
      router.push("/dashboard");
    }
  };

  return (
    <div className="min-h-screen flex">
      {/* Left Panel */}
      <div className="hidden lg:flex lg:w-1/2 bg-zinc-950 flex-col justify-between p-12">
        <div>
          <span className="text-white font-semibold text-lg tracking-tight">
            tatva<span className="text-emerald-400">.gridprice</span>
          </span>
        </div>
        <div className="space-y-6">
          <div className="space-y-2">
            <p className="text-zinc-400 text-sm uppercase tracking-widest font-medium">
              AI-Native Forecasting
            </p>
            <h1 className="text-white text-4xl font-bold leading-tight">
              Predict electricity<br />prices with precision.
            </h1>
          </div>
          <p className="text-zinc-400 text-base leading-relaxed max-w-sm">
            15-minute block-wise GDAM, DAM and RTM forecasts powered by machine learning. Built for enterprise procurement teams.
          </p>
          <div className="flex gap-8 pt-4">
            <div>
              <p className="text-emerald-400 text-2xl font-bold">96</p>
              <p className="text-zinc-500 text-sm">Daily blocks</p>
            </div>
            <div>
              <p className="text-emerald-400 text-2xl font-bold">3</p>
              <p className="text-zinc-500 text-sm">Markets covered</p>
            </div>
            <div>
              <p className="text-emerald-400 text-2xl font-bold">P10–P90</p>
              <p className="text-zinc-500 text-sm">Confidence range</p>
            </div>
          </div>
        </div>
        <p className="text-zinc-600 text-sm">© 2026 Tatva Energy Intelligence</p>
      </div>

      {/* Right Panel */}
      <div className="flex-1 flex items-center justify-center bg-white px-8">
        <div className="w-full max-w-sm space-y-8">
          <div className="space-y-2">
            <h2 className="text-2xl font-bold text-zinc-900">Welcome back</h2>
            <p className="text-zinc-500 text-sm">Sign in to your forecasting dashboard</p>
          </div>

          {error && (
            <div className="text-sm text-red-600 bg-red-50 border border-red-100 px-4 py-3 rounded-lg">
              {error}
            </div>
          )}

          <div className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="email" className="text-zinc-700 text-sm font-medium">
                Email address
              </Label>
              <Input
                id="email"
                type="email"
                placeholder="you@company.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="h-11 border-zinc-200 focus:border-zinc-400 focus:ring-0"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="password" className="text-zinc-700 text-sm font-medium">
                Password
              </Label>
              <Input
                id="password"
                type="password"
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="h-11 border-zinc-200 focus:border-zinc-400 focus:ring-0"
                onKeyDown={(e) => e.key === "Enter" && handleLogin()}
              />
            </div>
          </div>

          <Button
            className="w-full h-11 bg-zinc-900 hover:bg-zinc-700 text-white font-medium"
            onClick={handleLogin}
            disabled={loading}
          >
            {loading ? "Signing in..." : "Sign In"}
          </Button>

          <p className="text-sm text-center text-zinc-500">
            Don't have access?{" "}
            <a href="/request-access" className="text-zinc-900 font-medium hover:underline">
              Request Access
            </a>
          </p>
        </div>
      </div>
    </div>
  );
}