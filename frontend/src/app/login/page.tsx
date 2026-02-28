"use client";

import { useState } from "react";
import Link from "next/link";
import Image from "next/image";
import { useRouter } from "next/navigation";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function LoginPage() {
    const router = useRouter();
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [error, setError] = useState("");
    const [loading, setLoading] = useState(false);

    const handleLogin = async (e: React.FormEvent) => {
        e.preventDefault();
        setError("");
        setLoading(true);

        try {
            const res = await fetch(`${API_BASE}/api/auth/login`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ email, password }),
            });
            const data = await res.json();

            if (data.status === "success" && data.data) {
                localStorage.setItem("sv_token", data.data.access_token);
                localStorage.setItem("sv_refresh", data.data.refresh_token);
                localStorage.setItem("sv_user", JSON.stringify(data.data.user));
                router.push("/app");
            } else {
                setError(data.message || "Login failed");
            }
        } catch {
            setError("Server not reachable. Please start the backend.");
        } finally {
            setLoading(false);
        }
    };

    const handleGuest = () => {
        localStorage.setItem("sv_user", JSON.stringify({ email: "guest", name: "Guest", loggedIn: true, isGuest: true }));
        router.push("/app");
    };

    return (
        <div className="auth-container">
            <div className="glass-card auth-card">
                <div style={{ textAlign: "center", marginBottom: 12 }}>
                    <Image src="/logo.png" alt="SilentVoice" width={80} height={80}
                        style={{ borderRadius: "50%", boxShadow: "0 0 30px rgba(124, 77, 255, 0.15)" }} />
                </div>
                <h1>Welcome Back</h1>
                <p className="auth-subtitle">Sign in to your SilentVoice account</p>

                {error && (
                    <div style={{
                        padding: "10px 14px", marginBottom: 16, borderRadius: 10,
                        background: "rgba(255, 23, 68, 0.08)", border: "1px solid rgba(255, 23, 68, 0.2)",
                        color: "#ff4081", fontSize: "0.82rem", textAlign: "center",
                    }}>
                        ⚠️ {error}
                    </div>
                )}

                <form onSubmit={handleLogin}>
                    <div className="form-group">
                        <label>Email</label>
                        <input type="email" className="form-input" placeholder="you@example.com"
                            value={email} onChange={(e) => setEmail(e.target.value)} required
                            style={{ minHeight: 48 }} />
                    </div>
                    <div className="form-group">
                        <label>Password</label>
                        <input type="password" className="form-input" placeholder="••••••••"
                            value={password} onChange={(e) => setPassword(e.target.value)} required
                            style={{ minHeight: 48 }} />
                    </div>
                    <button type="submit" className="btn btn-primary btn-full btn-lg" disabled={loading}
                        style={{ marginTop: 8 }}>
                        {loading ? "Signing in…" : "Sign In"}
                    </button>
                </form>

                <div className="auth-divider">or</div>

                <button className="btn btn-secondary btn-full btn-lg" onClick={handleGuest}>
                    Continue as Guest
                </button>

                <p className="auth-footer">
                    Don&apos;t have an account?{" "}<Link href="/register">Create one</Link>
                </p>

                <div style={{ textAlign: "center", marginTop: 20, fontSize: "0.7rem", color: "var(--sv-text-muted)" }}>
                    © 2026 SilentVoice · Licensed to Dharaanishan
                </div>
            </div>
        </div>
    );
}
