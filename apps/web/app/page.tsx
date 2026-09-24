"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

type Arm = {
  arm: string; equity_usd: string; cash_usd: string; position_qty: string; position_mark_usd: string;
  return_pct: string; max_drawdown_usd: string; exposure_pct: string; trade_count: number;
  closed_operations: number; win_rate_pct: string | null; average_gain_usd: string | null;
  average_loss_usd: string | null; trading_cost_usd: string; ai_infrastructure_cost_usd: string | null;
  ai_cost_status: string; veto_count: number; abstention_count: number; failure_count: number;
  avg_latency_ms: number; evaluated_opportunities: number; sample_status: string;
  flat_cash_benchmark_usd: string; buy_and_hold_benchmark_usd: string;
  equity_curve: { at: string; equity_usd: string }[];
};
type Dashboard = {
  banner: string; mode: string; timezone: string;
  experiment: { id: string; name: string; status: string; entries_paused: boolean; config_hash: string; next_bar_index: number };
  snapshot: { cycle_id: string; cycle_index: number; cutoff_at: string; source: string; hash: string; synthetic: boolean } | null;
  arms: Record<string, Arm>;
  decisions: { id: number; cycle_id: string; snapshot_id: string; arm: string; candidate: string; action: string; outcome: string; reason_code: string; reason: string; filter_result: string | null; evidence_ids: string[]; created_at: string }[];
  integrations: Record<string, { status: string; message: string; checked_at: string | null }>;
  limitations: string[];
};
type IntegrationData = {
  alpaca_paper: { status: string; message: string; checked_at: string | null };
  alpaca_data: { status: string; message: string; checked_at: string | null };
  openrouter: { status: string; message: string; checked_at: string | null };
  configuration: { alpaca_paper_accounts_configured: Record<string, boolean>; alpaca_data_configured: boolean; openrouter_configured: boolean; openrouter_model_configured: boolean; jev_model: string; status: string };
  capabilities: { alpaca_orders_only_paper: boolean; order_origin: string; alpaca_data_read_only: boolean; model_tools: boolean; external_calls_run_automatically: boolean };
};
type DecisionDetail = {
  id: number; cycle_id: string; snapshot_id: string; snapshot_hash: string; arm: string;
  candidate: string; action: string; outcome: string; reason_code: string; reason: string;
  filter_result: string | null; evidence_ids: string[]; latency_ms: number;
  created_at: string;
  sources: { article_id: string; source: string; title: string; summary: string; content_hash: string; synthetic: boolean; created_at: string; updated_at: string; first_seen_at: string }[];
  orders: { client_order_id: string; side: string; status: string; quantity: string; notional_usd: string; mode: string; fills: { quantity: string; price: string; fee_amount: string | null; occurred_at: string }[] }[];
};

const money = (value?: string | null) => value == null ? "—" : new Intl.NumberFormat("pt-BR", { style: "currency", currency: "USD", maximumFractionDigits: 2 }).format(Number(value));
const percent = (value?: string | null) => value == null ? "—" : `${Number(value).toFixed(2).replace(".", ",")}%`;
const atSaoPaulo = (value?: string | null) => value ? new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "short", timeZone: "America/Sao_Paulo" }).format(new Date(value)) : "—";
const armNames: Record<string, string> = { A: "Base", B: "JEV", C: "Texto + JEV" };

async function api<T>(path: string, csrf?: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (csrf) headers.set("X-CSRF-Token", csrf);
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  const response = await fetch(path, { ...init, headers, credentials: "same-origin", cache: "no-store" });
  const content = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(content.detail ?? `A solicitação falhou (HTTP ${response.status}).`);
  return content as T;
}

function LineChart({ arms }: { arms: Record<string, Arm> }) {
  const colors: Record<string, string> = { A: "#147b60", B: "#5271a8", C: "#bd7e31" };
  const paths = useMemo(() => {
    const all = Object.values(arms).flatMap((arm) => arm.equity_curve.map((point) => Number(point.equity_usd)));
    if (!all.length) return [];
    const min = Math.min(...all) - 5, max = Math.max(...all) + 5;
    const width = 720, height = 230, insetX = 12, insetY = 14;
    return Object.entries(arms).map(([key, arm]) => {
      const values = arm.equity_curve.map((point) => Number(point.equity_usd));
      const path = values.map((value, index) => {
        const x = insetX + (values.length <= 1 ? 0 : index * (width - insetX * 2) / (values.length - 1));
        const y = height - insetY - ((value - min) / (max - min || 1)) * (height - insetY * 2);
        return `${index === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
      }).join(" ");
      return { key, path, color: colors[key] };
    });
  }, [arms]);
  return <div className="chart-wrap">
    <svg className="chart" viewBox="0 0 720 230" role="img" aria-label="Curvas sintéticas de patrimônio das versões A, B e C" preserveAspectRatio="none">
      {[0, 1, 2, 3].map((line) => <line key={line} x1="0" x2="720" y1={36 + line * 50} y2={36 + line * 50} className="chart-grid" />)}
      {paths.map((item) => <path key={item.key} d={item.path} fill="none" stroke={item.color} strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />)}
    </svg>
    <div className="chart-legend">{Object.entries(armNames).map(([key, name]) => <span key={key}><i style={{ background: colorsFor(key) }} />{key} · {name}</span>)}</div>
  </div>;
}
function colorsFor(key: string) { return ({ A: "#147b60", B: "#5271a8", C: "#bd7e31" } as Record<string, string>)[key]; }

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
    <div className="login-brand"><div className="brand-mark">P</div><span>PaperLab</span><small>LABORATÓRIO DE SIMULAÇÃO</small></div>
    <form onSubmit={submit} className="login-card">
      <span className="eyebrow">ÁREA PRIVADA</span><h1>Acesse o laboratório</h1>
      <p>Entre com a conta de administrador configurada neste ambiente local.</p>
      <label>Usuário<input autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} required /></label>
      <label>Senha<input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required /></label>
      {error && <div className="form-error" role="alert">{error}</div>}
      <button className="primary-button full-button" disabled={loading}>{loading ? "Entrando…" : "Entrar"}</button>
      <div className="login-note"><span className="lock-icon">◆</span>Sessão protegida · acesso local</div>
    </form>
  </main>;
}

export default function Home() {
  const [authenticated, setAuthenticated] = useState(false);
  const [username, setUsername] = useState("");
  const [csrf, setCsrf] = useState("");
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [integrations, setIntegrations] = useState<IntegrationData | null>(null);
  const [allExperiments, setAllExperiments] = useState<{ id: string; name: string; mode: string; status: string; entries_paused: boolean; config_hash: string; created_at: string }[]>([]);
  const [history, setHistory] = useState<DecisionDetail[]>([]);
  const [section, setSection] = useState("visao");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async (token = csrf, experimentId?: string) => {
    const suffix = experimentId ? `?experiment_id=${encodeURIComponent(experimentId)}` : "";
    const data = await api<Dashboard>(`/api/dashboard${suffix}`, token);
    setDashboard(data);
    return data;
  }, [csrf]);

  useEffect(() => {
    if (!authenticated || !csrf || !dashboard?.experiment.id) return;
    const interval = window.setInterval(() => {
      refresh(csrf, dashboard.experiment.id).catch(() => undefined);
    }, 30_000);
    return () => window.clearInterval(interval);
  }, [authenticated, csrf, dashboard?.experiment.id, refresh]);

  useEffect(() => {
    api<{ authenticated: boolean; username?: string; csrf_token?: string }>("/api/session")
      .then(async (session) => {
        if (!session.authenticated) return;
        setAuthenticated(true); setUsername(session.username ?? "administrador"); setCsrf(session.csrf_token ?? "");
        const [data, integrationData, experimentsData, historyData] = await Promise.all([
          api<Dashboard>("/api/dashboard", session.csrf_token),
          api<IntegrationData>("/api/integrations", session.csrf_token),
          api<typeof allExperiments>("/api/experiments", session.csrf_token),
          api<DecisionDetail[]>("/api/decisions?limit=80", session.csrf_token),
        ]);
        setDashboard(data); setIntegrations(integrationData); setAllExperiments(experimentsData); setHistory(historyData);
      }).catch((err) => setMessage(err instanceof Error ? err.message : "Não foi possível carregar os dados."));
  }, []);

  async function reloadEverything() {
    const [data, integrationData, experimentsData, historyData] = await Promise.all([
      refresh(), api<IntegrationData>("/api/integrations", csrf),
      api<typeof allExperiments>("/api/experiments", csrf),
      api<DecisionDetail[]>(`/api/decisions?experiment_id=${dashboard?.experiment.id}&limit=80`, csrf),
    ]);
    setIntegrations(integrationData); setAllExperiments(experimentsData); setHistory(historyData);
    return data;
  }

  async function act(action: "start" | "pause" | "stop" | "cycle") {
    if (!dashboard) return;
    setBusy(true); setMessage("");
    try {
      const result = await api<{ result: { remaining_positions?: Record<string, { qty: string; mark_usd: string }> } }>(`/api/experiments/${dashboard.experiment.id}/${action}`, csrf, { method: "POST" });
      if (action === "stop" && result.result.remaining_positions && Object.keys(result.result.remaining_positions).length) {
        setMessage(`Experimento encerrado com posições fictícias remanescentes. Confira o painel antes de criar outro.`);
      } else if (action === "start") setMessage("Demonstração iniciada. O primeiro ciclo sintético foi gravado.");
      else if (action === "pause") setMessage("Novas entradas pausadas; saídas determinísticas e reconciliação continuam.");
      else if (action === "cycle") setMessage("Próximo ciclo sintético gravado e vinculado ao snapshot.");
      else setMessage("Experimento encerrado. Posições remanescentes não foram liquidadas.");
      await reloadEverything();
    } catch (err) { setMessage(err instanceof Error ? err.message : "A ação falhou."); }
    finally { setBusy(false); }
  }

  async function createExperiment(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setMessage(""); const formElement = event.currentTarget;
    const form = new FormData(event.currentTarget); const name = String(form.get("name") ?? "").trim();
    try {
      await api("/api/experiments", csrf, { method: "POST", body: JSON.stringify({ name, mode: "DEMO" }) });
      await reloadEverything(); setMessage("Novo experimento DEMO criado, pausado e com configuração congelada."); formElement.reset();
    } catch (err) { setMessage(err instanceof Error ? err.message : "Não foi possível criar o experimento."); }
    finally { setBusy(false); }
  }

  async function selectExperiment(experimentId: string) {
    setBusy(true); setMessage("");
    try {
      const [data, rows] = await Promise.all([
        refresh(csrf, experimentId),
        api<DecisionDetail[]>(`/api/decisions?experiment_id=${encodeURIComponent(experimentId)}&limit=80`, csrf),
      ]);
      setDashboard(data); setHistory(rows); setSection("visao");
    } catch (err) { setMessage(err instanceof Error ? err.message : "Não foi possível abrir esse experimento."); }
    finally { setBusy(false); }
  }

  async function runIntegrationCheck(which: "paper" | "data" | "openrouter") {
    setBusy(true); setMessage("");
    const endpoint = which === "paper" ? "/api/integrations/alpaca/preflight" : which === "data" ? "/api/integrations/alpaca/data-check" : "/api/integrations/openrouter/validate";
    try {
      const result = await api<{ ready: boolean; reason: string }>(endpoint, csrf, { method: "POST" });
      setMessage(result.reason); const data = await api<IntegrationData>("/api/integrations", csrf); setIntegrations(data);
    } catch (err) { setMessage(err instanceof Error ? err.message : "Verificação não concluída."); }
    finally { setBusy(false); }
  }

  async function exportFile(format: "json" | "csv") {
    setBusy(true);
    try {
      const response = await fetch(`/api/export?format=${format}&experiment_id=${dashboard?.experiment.id}`, { credentials: "same-origin", cache: "no-store" });
      if (!response.ok) throw new Error("Não foi possível exportar este experimento.");
      const blob = await response.blob(); const link = document.createElement("a"); link.href = URL.createObjectURL(blob);
      link.download = `paperlab-${dashboard?.experiment.id}.${format}`; link.click(); URL.revokeObjectURL(link.href);
      setMessage(`Exportação ${format.toUpperCase()} gerada sem segredos.`);
    } catch (err) { setMessage(err instanceof Error ? err.message : "Falha na exportação."); }
    finally { setBusy(false); }
  }

  async function logout() {
    try { await api("/api/auth/logout", csrf, { method: "POST" }); } catch { /* session cookie may already be expired */ }
    setAuthenticated(false); setDashboard(null); setCsrf(""); setUsername("");
  }

  if (!authenticated) return <Login onSuccess={(name, token) => {
    setUsername(name); setCsrf(token); setAuthenticated(true);
    Promise.all([refresh(token), api<IntegrationData>("/api/integrations", token), api<typeof allExperiments>("/api/experiments", token), api<DecisionDetail[]>("/api/decisions?limit=80", token)])
      .then(([data, links, experimentsData, decisionsData]) => { setDashboard(data); setIntegrations(links); setAllExperiments(experimentsData); setHistory(decisionsData); })
      .catch((err) => setMessage(err instanceof Error ? err.message : "Erro ao carregar o laboratório."));
  }} />;

  const activeDashboard = dashboard;
  const activeArms = activeDashboard?.arms ?? {};
  const selectedIntegrations = integrations;

  return <div className="app-shell">
    <aside className="sidebar">
      <div className="side-brand"><div className="brand-mark">P</div><div><strong>PaperLab</strong><small>SIMULATION STUDIO</small></div></div>
      <div className="workspace-label">ESPAÇO DE TRABALHO</div>
      <nav className="main-nav" aria-label="Navegação principal">
        <button className={section === "visao" ? "nav-item active" : "nav-item"} onClick={() => setSection("visao")}><span className="nav-symbol">◫</span>Visão geral</button>
        <button className={section === "experimentos" ? "nav-item active" : "nav-item"} onClick={() => setSection("experimentos")}><span className="nav-symbol">◷</span>Experimentos<span className="nav-count">{allExperiments.length || 1}</span></button>
        <button className={section === "historico" ? "nav-item active" : "nav-item"} onClick={() => setSection("historico")}><span className="nav-symbol">≋</span>Decisões e ordens</button>
        <button className={section === "integracoes" ? "nav-item active" : "nav-item"} onClick={() => setSection("integracoes")}><span className="nav-symbol">⌘</span>Integrações</button>
      </nav>
      <div className="sidebar-foot">
        <div className="privacy-card"><div className="privacy-dot" /><div><strong>Ambiente privado</strong><span>Local · administrador</span></div></div>
        <button className="profile-button" onClick={logout}><div className="avatar">{username.slice(0, 1).toUpperCase()}</div><span>{username}<small>Administrador</small></span><span className="logout-arrow">↗</span></button>
      </div>
    </aside>

    <main className="main-area">
      <header className="topbar">
        <div><div className="breadcrumbs">PAPERLAB <span>/</span> {section === "visao" ? "VISÃO GERAL" : section === "experimentos" ? "EXPERIMENTOS" : section === "historico" ? "DECISÕES E ORDENS" : "INTEGRAÇÕES"}</div><h1>{section === "visao" ? "Painel comparativo" : section === "experimentos" ? "Experimentos" : section === "historico" ? "Rastreabilidade" : "Conexões"}</h1></div>
        <div className="topbar-right"><span className="timezone-chip"><span className="timezone-dot" />Horário · São Paulo</span><div className="user-avatar">{username.slice(0, 1).toUpperCase()}</div></div>
      </header>

      <div className="content-area">
        <div className="mode-banner"><div className="demo-icon">✳</div><div><strong>{activeDashboard?.banner ?? "DEMONSTRAÇÃO — dados e decisões sintéticos"}</strong><span>Nenhuma chamada externa é feita automaticamente. Valores e decisões não representam dados de mercado.</span></div><span className="demo-badge">MODO DEMO</span></div>
        {message && <div className="notice" role="status"><span>{message}</span><button aria-label="Fechar aviso" onClick={() => setMessage("")}>×</button></div>}

        {!activeDashboard && <div className="loading-state"><div className="loader" />Carregando dados do laboratório…</div>}

        {activeDashboard && section === "visao" && <>
          <div className="page-intro"><div><div className="eyebrow">EXPERIMENTO ATUAL <span className="hash-pill">{activeDashboard.experiment.config_hash.slice(0, 10)}</span></div><h2>{activeDashboard.experiment.name}</h2><p>Mesmo snapshot e regra-base; filtros aplicados depois em cada carteira isolada.</p></div>
            <div className="action-cluster">
              {(activeDashboard.experiment.status === "paused" || activeDashboard.experiment.status === "paused_entries") ? <button className="primary-button" onClick={() => act("start")} disabled={busy}><span>▶</span> Iniciar demonstração</button> : <button className="secondary-button" onClick={() => act("pause")} disabled={busy}><span>Ⅱ</span> Pausar entradas</button>}
              <button className="icon-button" title="Gerar próximo ciclo sintético" onClick={() => act("cycle")} disabled={busy || activeDashboard.experiment.status === "paused" || activeDashboard.experiment.status === "ended"}>＋<span className="sr-only">Gerar ciclo DEMO</span></button>
              <button className="icon-button export-trigger" onClick={() => exportFile("csv")} disabled={busy} title="Exportar CSV">↓</button>
            </div>
          </div>

          <div className="status-row"><span className={`status-pill ${activeDashboard.experiment.status === "running" ? "status-running" : "status-paused"}`}><i />{activeDashboard.experiment.status === "running" ? "Em execução" : activeDashboard.experiment.status === "paused_entries" ? "Entradas pausadas" : activeDashboard.experiment.status === "ended" ? "Encerrado" : "Pausado"}</span><span className="status-separator" /><span>Instrumento <strong>BTC/USD</strong></span><span className="status-separator" /><span>Janela <strong>1 hora</strong></span><span className="status-separator" /><span>Corte do último ciclo <strong>{atSaoPaulo(activeDashboard.snapshot?.cutoff_at)}</strong></span><span className="status-spacer" /><button className="text-button" onClick={() => setSection("experimentos")}>Configuração congelada <span>↗</span></button></div>

          <section className="arm-grid" aria-label="Resultados das três versões">
            {(["A", "B", "C"] as const).map((key) => {
              const arm = activeArms[key]; if (!arm) return null;
              return <article className={`arm-card arm-${key.toLowerCase()}`} key={key}>
                <div className="arm-heading"><div className="arm-ident"><span className="arm-letter">{key}</span><div><strong>{armNames[key]}</strong><small>{key === "A" ? "Estratégia-base determinística" : key === "B" ? "Base + filtro JEV" : "Base + síntese + JEV"}</small></div></div><span className="arm-dot" /></div>
                <div className="arm-value-label">PATRIMÔNIO FICTÍCIO</div><div className="arm-value">{money(arm.equity_usd)}</div>
                <div className={`return-chip ${Number(arm.return_pct) < 0 ? "negative" : ""}`}>{percent(arm.return_pct)} <span>no período</span></div>
                <div className="arm-stats"><div><span>Caixa</span><strong>{money(arm.cash_usd)}</strong></div><div><span>Exposição</span><strong>{percent(arm.exposure_pct)}</strong></div><div><span>Ordens simuladas</span><strong>{arm.trade_count}</strong></div><div><span>Custos sintéticos</span><strong>{money(arm.trading_cost_usd)}</strong></div></div>
                <div className="arm-foot"><span>IA / infraestrutura</span><strong title={arm.ai_cost_status}>n/a na DEMO</strong></div>
              </article>;
            })}
          </section>

          <section className="analysis-grid">
            <article className="panel chart-panel"><div className="panel-heading"><div><div className="eyebrow">PATRIMÔNIO AO LONGO DO TEMPO</div><h3>Trajetória das carteiras</h3></div><button className="dots-button" aria-label="Opções do gráfico">···</button></div><LineChart arms={activeArms} /><div className="benchmark-row"><div><span className="benchmark-swatch flat" />Saldo fictício parado <strong>{money(activeArms.A?.flat_cash_benchmark_usd)}</strong></div><div><span className="benchmark-swatch hold" />Comprar e manter <strong>{money(activeArms.A?.buy_and_hold_benchmark_usd)}</strong><small> referência analítica</small></div></div><p className="chart-caption">Curvas geradas somente com candles sintéticos do modo DEMO. A taxa ilustrativa está versionada na configuração.</p></article>
            <article className="panel insights-panel"><div className="panel-heading"><div><div className="eyebrow">LEITURA DO EXPERIMENTO</div><h3>Qualidade da amostra</h3></div><span className="info-mark">i</span></div><div className="sample-count"><strong>{Math.max(...Object.values(activeArms).map((arm) => arm.closed_operations))}</strong><span>operações encerradas</span></div><div className="sample-state">{Object.values(activeArms).every((arm) => arm.closed_operations === 0) ? <><span className="sample-icon">◌</span><div><strong>Amostra insuficiente</strong><p>A taxa de acerto só aparece após operações encerradas.</p></div></> : <><span className="sample-icon">↗</span><div><strong>Resultados descritivos</strong><p>Compare apenas no período comum, com exposição e tamanho de amostra visíveis.</p></div></>}</div><div className="insight-divider" /><div className="control-stat"><span>Drawdown máximo <i title="Queda observada no patrimônio fictício.">i</i></span><div>{(["A", "B", "C"] as const).map((key) => <strong key={key}><em className={`mini-dot ${key.toLowerCase()}`} />{money(activeArms[key]?.max_drawdown_usd)}</strong>)}</div></div><div className="control-stat"><span>Vetos · abstenções</span><div>{(["A", "B", "C"] as const).map((key) => <strong key={key}><em className={`mini-dot ${key.toLowerCase()}`} />{activeArms[key]?.veto_count ?? 0} · {activeArms[key]?.abstention_count ?? 0}</strong>)}</div></div><div className="insight-note"><span>ⓘ</span><p>O desenho não isola IA generativa sem JEV. A DEMO não é avaliação de APIs nem resultado de mercado.</p></div></article>
          </section>

          <section className="panel recent-panel"><div className="panel-heading"><div><div className="eyebrow">TRILHA DE AUDITORIA</div><h3>Decisões recentes</h3></div><button className="text-button" onClick={() => setSection("historico")}>Ver histórico completo <span>→</span></button></div><DecisionTable rows={activeDashboard.decisions} compact onOpen={() => setSection("historico")} /></section>
        </>}

        {activeDashboard && section === "experimentos" && <section className="experiments-layout">
          <article className="panel experiment-current"><div className="panel-heading"><div><div className="eyebrow">CONFIGURAÇÃO IMUTÁVEL</div><h3>Versão atual</h3></div><span className="mode-chip">DEMO</span></div><div className="config-grid"><div><span>Estratégia</span><strong>SMA 20 × 50</strong></div><div><span>Ativo / janela</span><strong>BTC/USD · 1 hora</strong></div><div><span>Notional por entrada</span><strong>US$ 100 fictícios</strong></div><div><span>Política de filtro</span><strong>filter-v1</strong></div><div><span>Hash de configuração</span><strong className="mono">{activeDashboard.experiment.config_hash}</strong></div><div><span>Ciclo seguinte</span><strong>#{activeDashboard.experiment.next_bar_index}</strong></div></div><div className="panel-actions"><button className="primary-button" onClick={() => act(activeDashboard.experiment.status === "running" ? "pause" : "start")} disabled={busy}>{activeDashboard.experiment.status === "running" ? "Ⅱ Pausar entradas" : "▶ Iniciar demonstração"}</button><button className="danger-button" onClick={() => act("stop")} disabled={busy || activeDashboard.experiment.status === "ended"}>Encerrar experimento</button><button className="secondary-button" onClick={() => exportFile("json")} disabled={busy}>Exportar JSON</button></div><div className="experiment-warning"><strong>Encerrar não liquida posições.</strong> O sistema mostra o saldo e o valor marcado das posições remanescentes.</div></article>
          <article className="panel new-experiment"><div className="eyebrow">COMEÇAR DE NOVO</div><h3>Criar experimento DEMO</h3><p>Cria uma configuração congelada e três livros sintéticos separados. Não usa dados de mercado.</p><form onSubmit={createExperiment}><label>Nome do experimento<input name="name" required maxLength={120} placeholder="Ex.: Ciclo de demonstração 2" /></label><button className="primary-button" disabled={busy}>＋ Criar experimento</button></form></article>
          <article className="panel experiments-list"><div className="panel-heading"><div><div className="eyebrow">REGISTROS</div><h3>Experimentos criados</h3></div><span className="count-pill">{allExperiments.length}</span></div><div className="experiment-list">{allExperiments.map((item) => <button key={item.id} className={item.id === activeDashboard.experiment.id ? "experiment-list-item selected" : "experiment-list-item"} onClick={() => selectExperiment(item.id)} disabled={busy}><span className="experiment-icon">◷</span><span><strong>{item.name}</strong><small>{item.mode} · {item.status} · {atSaoPaulo(item.created_at)}</small></span><span className="mini-hash">{item.config_hash.slice(0, 7)}</span></button>)}</div></article>
        </section>}

        {activeDashboard && section === "historico" && <section className="panel history-panel"><div className="panel-heading"><div><div className="eyebrow">SNAPSHOT → EVIDÊNCIA → DECISÃO → ORDEM</div><h3>Histórico de decisões</h3></div><button className="secondary-button" onClick={() => exportFile("json")} disabled={busy}>Exportar JSON</button></div><p className="section-description">Cada registro aponta para o snapshot compartilhado, conteúdo disponível no corte do ciclo e eventuais fills sintéticos.</p><DecisionTable rows={history} onOpen={() => {}} /><div className="detail-list">{history.slice(0, 12).map((row) => <details key={row.id} className="decision-detail"><summary><span className={`table-arm ${row.arm.toLowerCase()}`}>{row.arm}</span><span>{row.cycle_id}</span><span>{row.outcome}</span><span className="detail-open">Abrir fontes e fills ＋</span></summary><div className="detail-content"><div className="trace-block"><div className="trace-label">VÍNCULO DO SNAPSHOT</div><div><span>Snapshot</span><code>{row.snapshot_id}</code></div><div><span>Hash</span><code>{row.snapshot_hash}</code></div><div><span>Candidato / decisão</span><strong>{row.candidate} · {row.action} · {row.reason_code}</strong></div><p>{row.reason}</p></div><div className="trace-block"><div className="trace-label">FONTES E VERSÕES DISPONÍVEIS</div>{row.sources.length ? row.sources.map((source) => <div className="source-item" key={source.article_id}><strong>{source.title}</strong><span>{source.article_id} · {source.source} · {source.synthetic ? "fixture sintético" : "feed externo"}</span><small>hash {source.content_hash.slice(0, 14)} · recebido {atSaoPaulo(source.first_seen_at)}</small></div>) : <p>Nenhum contexto textual novo disponível neste corte. O feed DEMO foi saudável.</p>}</div><div className="trace-block"><div className="trace-label">ORDENS E EXECUÇÕES</div>{row.orders.length ? row.orders.map((order) => <div className="order-trace" key={order.client_order_id}><strong>{order.side.toUpperCase()} · {order.status}</strong><span>client_order_id <code>{order.client_order_id}</code></span>{order.fills.map((fill, index) => <small key={index}>fill {fill.quantity} BTC/USD a {money(fill.price)} · taxa sintética {money(fill.fee_amount)} · {atSaoPaulo(fill.occurred_at)}</small>)}</div>) : <p>Nenhuma ordem vinculada a esta decisão.</p>}</div></div></details>)}</div></section>}

        {activeDashboard && section === "integracoes" && <section className="integration-layout">
          <div className="integration-intro"><div><div className="eyebrow">CONFIGURAÇÃO PENDENTE ATÉ VERIFICAÇÃO</div><h2>Conexões de simulação</h2><p>As chaves ficam no servidor e nunca são exibidas nesta tela. Nenhuma conexão externa roda ao abrir o app.</p></div><span className="config-state">{selectedIntegrations?.configuration.status === "configured" ? "Configuração completa" : "Aguardando configuração"}</span></div>
          <IntegrationCard title="Alpaca · paper trading" description="Preflight de leitura para três contas isoladas, saldos equivalentes e ausência de posições ou ordens herdadas." state={selectedIntegrations?.alpaca_paper} configured={Object.values(selectedIntegrations?.configuration.alpaca_paper_accounts_configured ?? {}).filter(Boolean).length + "/3 contas paper"} button="Executar preflight somente leitura" onClick={() => runIntegrationCheck("paper")} disabled={busy} accent="green" />
          <IntegrationCard title="Alpaca · dados e notícias" description="Cliente de dados separado e somente de leitura. O mapeamento de notícias BTCUSD é distinto do símbolo de ordens BTC/USD." state={selectedIntegrations?.alpaca_data} configured={selectedIntegrations?.configuration.alpaca_data_configured ? "Credenciais presentes" : "Credenciais pendentes"} button="Verificar acesso aos candles" onClick={() => runIntegrationCheck("data")} disabled={busy} accent="blue" />
          <IntegrationCard title="OpenRouter · texto + JEV" description="Geração estruturada apenas com fontes recebidas. JEV usa System One e ID de versão fixo; esta validação não envia um prompt." state={selectedIntegrations?.openrouter} configured={`${selectedIntegrations?.configuration.jev_model ?? "typesafe/jev-1.13"} · ${selectedIntegrations?.configuration.openrouter_model_configured ? "modelo de texto definido" : "modelo de texto pendente"}`} button="Validar modelo e schema" onClick={() => runIntegrationCheck("openrouter")} disabled={busy} accent="amber" />
          <div className="integration-safety"><span className="safety-check">✓</span><div><strong>Limites de segurança fixos</strong><p>Ordens, se autorizadas em uma implementação paper conectada, só podem usar <code>https://paper-api.alpaca.markets</code>. Dados são somente leitura. Ferramentas de modelo ficam desativadas.</p></div><span className="safe-chip">SEM DINHEIRO REAL</span></div>
          <div className="integration-footnote">Uma verificação bem-sucedida confirma acesso ao endpoint consultado. Só uma chamada autenticada confirma a integração real; chamadas de validação de modelo não provam a qualidade de respostas.</div>
        </section>}

        <footer className="page-footer"><span>PaperLab · ambiente de avaliação</span><span>Dados sintéticos identificados · nada aqui é recomendação</span><span>Timezone · America/Sao_Paulo</span></footer>
      </div>
    </main>
  </div>;
}

function DecisionTable({ rows, compact = false }: { rows: { id: number; cycle_id: string; snapshot_id: string; arm: string; candidate: string; action: string; outcome: string; reason_code: string; reason: string; filter_result: string | null; evidence_ids: string[]; created_at: string }[]; compact?: boolean; onOpen: () => void }) {
  const shown = compact ? rows.slice(0, 6) : rows;
  return <div className="table-scroll"><table className="decision-table"><thead><tr><th>VERSÃO</th><th>CICLO</th><th>CANDIDATO</th><th>FILTRO</th><th>RESULTADO</th><th>RASTREIO</th><th>HORÁRIO · SP</th></tr></thead><tbody>{shown.map((row) => <tr key={row.id}><td><span className={`table-arm ${row.arm.toLowerCase()}`}>{row.arm}</span></td><td className="mono">{row.cycle_id.slice(-9)}</td><td>{row.candidate}</td><td>{row.filter_result ?? "—"}</td><td><span className={`outcome outcome-${row.outcome}`}>{outcomePt(row.outcome)}</span></td><td><span className="trace-mini">{row.reason_code}</span></td><td>{atSaoPaulo(row.created_at)}</td></tr>)}</tbody></table>{!shown.length && <div className="empty-table">Ainda não há ciclos. Inicie a DEMO para gravar o primeiro.</div>}</div>;
}
function outcomePt(value: string) { return ({ filled: "Executada · DEMO", vetoed: "Vetada", abstained: "Abstenção", blocked: "Bloqueada", holding: "Posição mantida", no_position: "Sem posição", no_candidate: "Sem candidato" } as Record<string, string>)[value] ?? value; }

function IntegrationCard({ title, description, state, configured, button, onClick, disabled, accent }: { title: string; description: string; state?: { status: string; message: string; checked_at: string | null }; configured: string; button: string; onClick: () => void; disabled: boolean; accent: string }) {
  const status = state?.status ?? "pending";
  return <article className={`panel integration-card accent-${accent}`}><div className="integration-card-top"><div className="integration-icon">{accent === "green" ? "A" : accent === "blue" ? "◈" : "✳"}</div><span className={`integration-status status-${status}`}><i />{statusPt(status)}</span></div><h3>{title}</h3><p>{description}</p><div className="integration-config"><span>CONFIGURAÇÃO</span><strong>{configured}</strong></div><div className="integration-last"><span>ÚLTIMA VERIFICAÇÃO</span><span>{state?.checked_at ? atSaoPaulo(state.checked_at) : "Ainda não verificada"}</span></div><div className="integration-message">{state?.message ?? "Integração externa não executada."}</div><button className="secondary-button" onClick={onClick} disabled={disabled}>{button}</button></article>;
}
function statusPt(status: string) { return ({ pending: "Pendente", ready: "Conectada", blocked: "Bloqueada", unavailable: "Indisponível" } as Record<string, string>)[status] ?? status; }
