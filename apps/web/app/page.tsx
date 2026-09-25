"use client";

import { FormEvent, useEffect, useState } from "react";
import MarketTerminal from "./terminal";
import PilotV2 from "./pilot-v2";

type Session = { authenticated: boolean; username?: string; csrf_token?: string };

async function api<T>(path: string, csrf?: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (csrf) headers.set("X-CSRF-Token", csrf);
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  const response = await fetch(path, { ...init, headers, credentials: "same-origin", cache: "no-store" });
  const content = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(content.detail ?? `A solicitação falhou (HTTP ${response.status}).`);
  return content as T;
}

function Login({ onSuccess }: { onSuccess: (username: string, csrf: string) => void }) {
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  async function submit(event: FormEvent) {
    event.preventDefault(); setLoading(true); setError("");
    try {
      const result = await api<{ username: string; csrf_token: string }>("/api/auth/login", undefined, { method: "POST", body: JSON.stringify({ username, password }) });
      onSuccess(result.username, result.csrf_token);
    } catch (err) { setError(err instanceof Error ? err.message : "Não foi possível entrar."); }
    finally { setLoading(false); }
  }
  return <main className="login-shell">
    <div className="login-brand"><div className="brand-mark">P</div><span>PaperLab</span><small>PILOTO DE SIMULAÇÃO</small></div>
    <form onSubmit={submit} className="login-card">
      <span className="eyebrow">ÁREA PRIVADA</span><h1>Acesse o piloto</h1>
      <p>Entre com a conta de administrador configurada neste ambiente.</p>
      <label>Usuário<input autoComplete="username" value={username} onChange={(event) => setUsername(event.target.value)} required /></label>
      <label>Senha<input type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} required /></label>
      {error && <div className="form-error" role="alert">{error}</div>}
      <button className="primary-button full-button" disabled={loading}>{loading ? "Entrando…" : "Entrar"}</button>
      <div className="login-note"><span className="lock-icon">◆</span>Sessão protegida · acesso privado</div>
    </form>
  </main>;
}

export default function Home() {
  const [session, setSession] = useState<Session>({ authenticated: false });
  const [message, setMessage] = useState("");
  useEffect(() => {
    api<Session>("/api/session").then(setSession).catch((err) => setMessage(err instanceof Error ? err.message : "Não foi possível carregar a sessão."));
  }, []);
  async function logout() {
    try { await api("/api/auth/logout", session.csrf_token, { method: "POST" }); } catch { /* a sessão pode ter expirado */ }
    setSession({ authenticated: false });
  }
  if (!session.authenticated || !session.csrf_token) return <Login onSuccess={(username, csrf_token) => setSession({ authenticated: true, username, csrf_token })} />;
  const username = session.username ?? "administrador";
  return <div className="pilot-shell">
    <header className="pilot-appbar">
      <div className="pilot-brand"><div className="brand-mark">P</div><div><strong>PaperLab</strong><span>Piloto com capital virtual</span></div></div>
      <div className="pilot-appbar-right"><span>MON/USDC · horário de São Paulo</span><button onClick={logout} aria-label="Sair da conta">Sair · {username}</button></div>
    </header>
    <main className="pilot-content">
      {message && <div className="pilot-notice" role="status"><span>{message}</span><button onClick={() => setMessage("")} aria-label="Fechar aviso">×</button></div>}
      <PilotV2 csrf={session.csrf_token} />
      <details className="v2-legacy"><summary>Consultar teste anterior</summary><MarketTerminal csrf={session.csrf_token} onMessage={setMessage} /></details>
    </main>
  </div>;
}
