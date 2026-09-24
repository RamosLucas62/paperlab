"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

type TerminalData = {
  configuration: { market_configured: boolean; kuru_feed_configured: boolean; market_address_hint: string | null; symbol: string; chain_id: number; rpc_configured: boolean; jev_configured: boolean; jev_model: string; ai_call_budget_usd: string; ai_daily_budget_usd: string; jev_interval_seconds: number };
  control: { monitor_enabled: boolean; jev_enabled: boolean; simulation_enabled: boolean; status: string; last_error: string | null; last_block_number: number | null; last_sample_at: string | null; last_jev_at: string | null };
  market: { symbol: string; best_bid: string; best_ask: string; mid_price: string; spread_bps: string; block_number: number | null; observed_at: string } | null;
  samples: { at: string; mid_price: string; best_bid: string; best_ask: string; spread_bps: string }[];
  events: { at: string; side: string; price: string; size: string | null; tx_hash: string | null }[];
  jev_observations: { at: string; status: string; model: string; result: Record<string, { choice?: string; confidence?: string; probabilities?: Record<string, string> }> | null; message: string; cost_usd: string | null; cost_status: string; latency_ms: number }[];
  simulation: {
    enabled: boolean;
    mode: string;
    account: { starting_cash_usdc: string; cash_usdc: string; position_qty: string; average_entry_price: string; mark_price: string | null; marked_at: string | null; mark_stale: boolean; position_value_usdc: string | null; equity_usdc: string | null; realized_pnl_usdc: string; unrealized_pnl_usdc: string | null; total_pnl_usdc: string | null } | null;
    open_order: SimulationOrder | null;
    orders: SimulationOrder[];
    decisions: { stance: string; confidence: string | null; status: string; reason: string; at: string; order: SimulationOrder | null }[];
    assumptions: { order_notional_usdc: string; minimum_confidence: string; order_ttl_seconds: number; fill_rule: string; cost_rule: string; starting_cash_usdc: string };
  };
  safety: { orders_enabled: boolean; transaction_signing: boolean; mode: string };
};

type SimulationOrder = { side: string; status: string; quantity: string; limit_price: string; notional_usdc: string; confidence: string | null; at: string; expires_at: string; filled_at: string | null; fill_price: string | null; fill_quantity: string | null };

function price(value?: string | null) {
  if (value == null) return "—";
  return Number(value).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 6 });
}
function usdc(value: string) { return `${Number(value).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} USDC`; }
function signedUsdc(value: string) { const amount = Number(value); return `${amount > 0 ? "+" : ""}${amount.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} USDC`; }
function time(value?: string | null) {
  return value ? new Intl.DateTimeFormat("pt-BR", { timeZone: "America/Sao_Paulo", hour: "2-digit", minute: "2-digit", second: "2-digit" }).format(new Date(value)) : "—";
}
function statusLabel(status: string) {
  return ({ stopped: "Desconectado", starting: "Conectando", connected: "Feed ativo", error: "Atenção" } as Record<string, string>)[status] ?? status;
}

async function request<T>(path: string, csrf: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("X-CSRF-Token", csrf);
  if (init.body) headers.set("Content-Type", "application/json");
  const response = await fetch(path, { ...init, headers, credentials: "same-origin", cache: "no-store" });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail ?? `A solicitação falhou (HTTP ${response.status}).`);
  return body as T;
}

function MarketChart({ samples, symbol }: { samples: TerminalData["samples"]; symbol: string }) {
  const chart = useMemo(() => {
    if (!samples.length) return null;
    const values = samples.map((sample) => Number(sample.mid_price)).filter(Number.isFinite);
    if (!values.length) return null;
    const minValue = Math.min(...values), maxValue = Math.max(...values);
    const padding = (maxValue - minValue) * 0.12 || Math.max(maxValue * 0.001, 0.000001);
    const min = minValue - padding, max = maxValue + padding;
    const points = values.map((value, index) => {
      const x = values.length < 2 ? 40 : 12 + index * 976 / (values.length - 1);
      const y = 272 - ((value - min) / (max - min)) * 244;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    });
    return { path: points.map((point, index) => `${index ? "L" : "M"}${point}`).join(" "), first: values[0], last: values.at(-1)!, min, max };
  }, [samples]);
  return <div className="terminal-chart-wrap">
    {chart ? <>
      <svg className="terminal-chart" viewBox="0 0 1000 300" role="img" aria-label={`Preço médio observado de ${symbol}`} preserveAspectRatio="none">
        {[0, 1, 2, 3].map((row) => <line key={row} x1="0" x2="1000" y1={28 + row * 72} y2={28 + row * 72} />)}
        <path d={chart.path} />
      </svg>
      <div className="terminal-chart-ends"><span>{price(String(chart.min))}</span><span>{price(String(chart.max))}</span></div>
      <div className="terminal-chart-caption"><span>{time(samples[0]?.at)}</span><span>amostras recebidas da Kuru</span><span>{time(samples.at(-1)?.at)}</span></div>
    </> : <div className="terminal-chart-empty"><span>◌</span><strong>Aguardando dados do mercado</strong><small>Inicie o monitor para receber o livro da Kuru.</small></div>}
  </div>;
}

export default function MarketTerminal({ csrf, onMessage }: { csrf: string; onMessage: (message: string) => void }) {
  const [data, setData] = useState<TerminalData | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    const next = await request<TerminalData>("/api/terminal", csrf);
    setData(next);
    setError("");
  }, [csrf]);

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const next = await request<TerminalData>("/api/terminal", csrf);
        if (active) { setData(next); setError(""); }
      } catch (err) {
        if (active) setError(err instanceof Error ? err.message : "Não foi possível carregar o terminal.");
      } finally { if (active) setLoading(false); }
    };
    void load();
    const interval = window.setInterval(() => { void load(); }, 5000);
    return () => { active = false; window.clearInterval(interval); };
  }, [csrf]);

  async function control(action: "start_monitor" | "stop_monitor" | "enable_jev" | "disable_jev" | "enable_simulation" | "disable_simulation") {
    setBusy(true); setError("");
    try {
      await request("/api/terminal/control", csrf, { method: "POST", body: JSON.stringify({ action }) });
      await refresh();
      onMessage(action === "start_monitor" ? "Monitor solicitado. Aguardando conexão com Monad e Kuru." : action === "stop_monitor" ? "Monitor parado; Jev e DRY RUN desativados." : action === "enable_jev" ? "Jev habilitado para classificações observacionais dentro do limite de custo." : action === "disable_jev" ? "Jev e DRY RUN desativados; ordens simuladas pendentes canceladas." : action === "enable_simulation" ? "DRY RUN ativado. Ordens e preenchimentos serão apenas simulados." : "DRY RUN parado; ordens simuladas pendentes canceladas.");
    } catch (err) { setError(err instanceof Error ? err.message : "A ação não foi concluída."); }
    finally { setBusy(false); }
  }

  const current = data?.market;
  const lastJev = data?.jev_observations[0];
  const stance = lastJev?.status === "ready" ? lastJev.result?.stance : undefined;
  const chainId = data?.configuration.chain_id;
  const network = networkLabel(chainId);
  return <section className="terminal-view" aria-label="Terminal JEV">
    <div className="terminal-safety-banner"><span className="terminal-live-dot" /><div><strong>FEED REAL · EXECUÇÃO SOMENTE EM DRY RUN</strong><span>Livro e trades vêm da {network}. Ordens, fills e posição são fictícios; não há carteira, assinatura ou envio de transações.</span></div><span className="terminal-mode-chip">SEM CARTEIRA</span></div>
    {error && <div className="terminal-error" role="alert">{error}</div>}

    <div className="terminal-heading">
      <div><div className="terminal-kicker">PAPERLAB <span>·</span> {network.toUpperCase()} <span>·</span> {data?.configuration.symbol ?? "MON/USDC"}</div><h2>Terminal JEV</h2><p>Acompanhe o livro de ofertas e as classificações de mercado em um ambiente de sombra.</p></div>
      <div className="terminal-actions">
        {data?.control.monitor_enabled ? <button className="terminal-button secondary" onClick={() => control("stop_monitor")} disabled={busy}>■ Parar monitor</button> : <button className="terminal-button primary" onClick={() => control("start_monitor")} disabled={busy || !data?.configuration.market_configured || !data?.configuration.kuru_feed_configured}>▶ Iniciar monitor</button>}
        {data?.control.jev_enabled ? <button className="terminal-button secondary" onClick={() => control("disable_jev")} disabled={busy}>Desativar Jev</button> : <button className="terminal-button outline" onClick={() => control("enable_jev")} disabled={busy || !data?.configuration.jev_configured || !data?.control.monitor_enabled}>Ativar Jev</button>}
        {data?.control.simulation_enabled ? <button className="terminal-button simulation-stop" onClick={() => control("disable_simulation")} disabled={busy}>Parar DRY RUN</button> : <button className="terminal-button simulation-start" onClick={() => control("enable_simulation")} disabled={busy || !data?.control.monitor_enabled || !data?.control.jev_enabled || !current}>Ativar DRY RUN</button>}
      </div>
    </div>

    <div className="terminal-status-line"><span className={`terminal-status status-${data?.control.status ?? "stopped"}`}><i />{statusLabel(data?.control.status ?? "stopped")}</span><span className="terminal-status-separator" /><span>Último bloco <strong>{data?.control.last_block_number?.toLocaleString("en-US") ?? "—"}</strong></span><span className="terminal-status-separator" /><span>Atualizado <strong>{time(data?.control.last_sample_at)}</strong></span><span className="terminal-status-spacer" /><span className="terminal-market-hint">Mercado {data?.configuration.market_address_hint ?? "não configurado"}</span></div>

    {!data?.configuration.market_configured && <div className="terminal-setup-note"><strong>Falta informar o mercado Kuru.</strong><span>Adicione <code>KURU_MARKET_ADDRESS</code> no EasyPanel. Para observação somente leitura na Monad Mainnet, o par MON/USDC verificado é <code>0x065c9d28e428a0db40191a54d33d5b7c71a9c394</code>. Endereços não são intercambiáveis entre redes. Depois salve e reimplante <code>api</code> e <code>bot</code>.</span></div>}
    {!data?.configuration.kuru_feed_configured && <div className="terminal-setup-note"><strong>Feed Kuru de Testnet indisponível.</strong><span>O RPC da Monad Testnet está configurado, mas o SDK atual da Kuru não documenta um feed WSS ativo para essa rede; o host antigo é legado e não está validado. O monitor fica bloqueado para evitar conectar a uma fonte incorreta. Para ver dados Kuru agora, a alternativa é selecionar Monad Mainnet em modo somente leitura, sem carteira nem envio de transações.</span></div>}
    {data?.control.last_error && <div className="terminal-error" role="status">{data.control.last_error}</div>}

    <div className="terminal-stats-grid">
      <article className="terminal-stat-card"><span>PREÇO MÉDIO · {current?.symbol ?? data?.configuration.symbol ?? "MON/USDC"}</span><strong>{price(current?.mid_price)}</strong><small>bid {price(current?.best_bid)} <b>·</b> ask {price(current?.best_ask)}</small></article>
      <article className="terminal-stat-card"><span>REDE · BLOCO</span><strong>{network}</strong><small>{data?.control.last_block_number?.toLocaleString("en-US") ?? "aguardando RPC"}</small></article>
      <article className="terminal-stat-card"><span>LEITURA JEV · SOMBRA</span><strong>{stance ? stanceLabel(stance.choice) : "—"}</strong><small>{stance?.confidence ? `${percent(stance.confidence)} de confiança reportada` : data?.control.jev_enabled ? "aguardando próxima leitura" : "Jev desativado"}</small></article>
    </div>

    <div className="terminal-main-grid">
      <article className="terminal-panel terminal-chart-panel"><div className="terminal-panel-heading"><div><span className="terminal-kicker">MERCADO · SOMENTE LEITURA</span><h3>{data?.configuration.symbol ?? "MON/USDC"}</h3></div><div className="terminal-price-tag"><small>MID</small><strong>{price(current?.mid_price)}</strong></div></div><MarketChart samples={data?.samples ?? []} symbol={data?.configuration.symbol ?? "MON/USDC"} /><div className="terminal-panel-foot"><span><i className="terminal-cyan-dot" /> preço médio observado</span><span>{data?.samples.length ?? 0} amostras na janela visível</span></div></article>

      <article className="terminal-panel terminal-jev-panel"><div className="terminal-panel-heading"><div><span className="terminal-kicker">OPENROUTER · {data?.configuration.jev_model ?? "JEV"}</span><h3>Observações do Jev</h3></div><span className={data?.configuration.jev_configured ? "terminal-config-ok" : "terminal-config-pending"}>{data?.configuration.jev_configured ? "CONFIGURADO" : "CHAVE PENDENTE"}</span></div>
        <div className={`terminal-stance-card ${stance ? `stance-${stance.choice}` : "stance-empty"}`}><div><span>POSTURA OBSERVACIONAL</span><strong>{stance ? stanceLabel(stance.choice) : "AGUARDANDO JEV"}</strong></div><small>{stance?.confidence ? `${percent(stance.confidence)} confiança reportada` : "Sem ordem, posição ou recomendação."}</small>{stance?.probabilities && <div className="terminal-stance-probabilities">{Object.entries(stance.probabilities).map(([key, value]) => <span key={key}>{stanceLabel(key)} <b>{percent(value)}</b></span>)}</div>}</div>
        <div className="terminal-jev-summary"><strong>{data?.control.jev_enabled ? "Jev observando" : "Aguardando ativação"}</strong><p>{data?.control.jev_enabled ? `Uma leitura de sombra a cada ${data?.configuration.jev_interval_seconds ?? 120} segundos, sujeita ao orçamento diário. O rótulo nunca aciona uma ordem.` : "As chamadas são opcionais e podem ter custo. Ative após configurar OPENROUTER_API_KEY no servidor."}</p></div>
        <div className="terminal-jev-list">{data?.jev_observations.slice(0, 5).map((item, index) => <div className="terminal-jev-row" key={`${item.at}-${index}`}><span className={`terminal-jev-indicator ${item.status}`} /><div><strong>{item.status === "ready" ? "Leitura de sombra registrada" : item.status === "budget_blocked" ? "Limite de custo atingido" : "Chamada sem resultado"}</strong><small>{time(item.at)} · {item.latency_ms} ms{item.cost_usd ? ` · US$ ${item.cost_usd}` : item.cost_status === "unknown" ? " · custo não informado pelo provedor" : ""}</small>{item.result && <div className="terminal-jev-choices">{Object.entries(item.result).map(([key, value]) => <span key={key}>{jevLabel(key)} <b>{choiceLabel(value.choice)}</b>{value.confidence ? ` · ${percent(value.confidence)}` : ""}</span>)}</div>}<p>{item.message}</p></div></div>)}{!data?.jev_observations.length && <div className="terminal-empty-note">Nenhuma leitura ainda. O Jev não roda automaticamente.</div>}</div>
        <div className="terminal-budget-row"><span>Teto por chamada</span><strong>US$ {data?.configuration.ai_call_budget_usd ?? "0.10"}</strong><span>Teto diário</span><strong>US$ {data?.configuration.ai_daily_budget_usd ?? "2.00"}</strong></div>
      </article>
    </div>

    <TerminalSimulationPanel simulation={data?.simulation} enabled={Boolean(data?.control.simulation_enabled)} />

    <article className="terminal-panel terminal-tape-panel"><div className="terminal-panel-heading"><div><span className="terminal-kicker">EVENTOS DO FEED KURU</span><h3>Negociações recentes · mercado real</h3></div><span className="terminal-tape-count">{data?.events.length ?? 0} eventos</span></div><div className="terminal-tape-scroll"><table className="terminal-tape"><thead><tr><th>HORÁRIO · SP</th><th>LADO AGRESSOR</th><th>PREÇO</th><th>IDENTIFICADOR</th></tr></thead><tbody>{data?.events.map((item, index) => <tr key={`${item.at}-${index}`}><td>{time(item.at)}</td><td><span className={`terminal-side ${item.side === "BUY" ? "buy" : "sell"}`}>{item.side}</span></td><td>{price(item.price)}</td><td className="terminal-hash">{txHash(item.tx_hash) ? <a href={txExplorerUrl(item.tx_hash!, chainId)} target="_blank" rel="noreferrer">{`${item.tx_hash!.slice(0, 9)}…${item.tx_hash!.slice(-5)}`}</a> : "—"}</td></tr>)}</tbody></table>{!data?.events.length && <div className="terminal-empty-note">{loading ? "Carregando eventos…" : "A fita será preenchida quando o feed Kuru publicar negociações."}</div>}</div></article>

    <div className="terminal-bottom-note"><span>ⓘ</span><p>BUY/SELL na fita é o lado agressor do mercado real e nunca aciona o simulador. Somente classificações Jev válidas, aprovadas por filtros determinísticos, podem gerar ordem local de DRY RUN. Não há carteira nem execução real; taxas e slippage ficam fora do P&L bruto.</p></div>
  </section>;
}

function TerminalSimulationPanel({ simulation, enabled }: {
  simulation: TerminalData["simulation"] | undefined;
  enabled: boolean;
}) {
  const account = simulation?.account;
  const pnl = account?.total_pnl_usdc;
  const pnlClass = pnl == null ? "" : Number(pnl) > 0 ? "positive" : Number(pnl) < 0 ? "negative" : "neutral";
  return <section className="terminal-panel terminal-simulation-panel" aria-label="Simulador de ordens DRY RUN">
    <div className="terminal-panel-heading terminal-simulation-heading">
      <div><span className="terminal-kicker">PAPER EXECUTION · SEM TRANSAÇÃO</span><h3>Simulador de ordens</h3><p>O feed é real; saldo, posições, ordens e fills são fictícios.</p></div>
      <span className={`terminal-simulation-badge ${enabled ? "active" : "inactive"}`}>{enabled ? "DRY RUN ATIVO" : "DRY RUN DESATIVADO"}</span>
    </div>

    <div className="terminal-simulation-metrics">
      <article><span>PATRIMÔNIO FICTÍCIO</span><strong>{account?.equity_usdc == null ? "—" : usdc(account.equity_usdc)}</strong><small>caixa + posição marcada pelo mid</small></article>
      <article><span>P&L BRUTO</span><strong className={pnlClass}>{pnl == null ? "—" : signedUsdc(pnl)}</strong><small>realizado {account ? signedUsdc(account.realized_pnl_usdc) : "—"} · aberto {account?.unrealized_pnl_usdc == null ? "—" : signedUsdc(account.unrealized_pnl_usdc)}</small></article>
      <article><span>CAIXA SIMULADO</span><strong>{account ? usdc(account.cash_usdc) : "—"}</strong><small>saldo inicial {simulation ? usdc(simulation.assumptions.starting_cash_usdc) : "—"}</small></article>
      <article><span>POSIÇÃO {account?.position_qty && Number(account.position_qty) > 0 ? "· ABERTA" : "· ZERADA"}</span><strong>{account ? `${Number(account.position_qty).toLocaleString("pt-BR", { maximumFractionDigits: 6 })} MON` : "—"}</strong><small>{account && Number(account.position_qty) > 0 ? `entrada ${price(account.average_entry_price)} · marca ${price(account.mark_price)}${account.mark_stale ? " · cotação antiga" : ""}` : "sem exposição comprada"}</small></article>
    </div>

    <div className="terminal-simulation-lower">
      <div className="terminal-open-order">
        <div className="terminal-mini-heading"><span className="terminal-kicker">ORDEM SIMULADA</span><span className={`terminal-order-state ${simulation?.open_order ? "open" : "idle"}`}>{simulation?.open_order ? "PENDENTE" : "SEM ORDEM PENDENTE"}</span></div>
        {simulation?.open_order ? <div className="terminal-open-order-detail"><strong className={`terminal-side ${simulation.open_order.side.toLowerCase()}`}>{simulation.open_order.side}</strong><span>{Number(simulation.open_order.quantity).toLocaleString("pt-BR", { maximumFractionDigits: 6 })} MON</span><span>limite {price(simulation.open_order.limit_price)}</span><span>{usdc(simulation.open_order.notional_usdc)}</span><small>expira {time(simulation.open_order.expires_at)}</small></div> : <p>{enabled ? "Aguardando classificação Jev válida com confiança suficiente." : "Ative depois de iniciar o monitor e o Jev."}</p>}
        <div className="terminal-simulation-assumptions"><span>Ordem <b>{simulation ? usdc(simulation.assumptions.order_notional_usdc) : "—"}</b></span><span>Confiança mínima <b>{simulation ? percent(simulation.assumptions.minimum_confidence) : "—"}</b></span><span>Validade <b>{simulation?.assumptions.order_ttl_seconds ?? "—"} s</b></span></div>
      </div>
      <div className="terminal-simulation-method"><span className="terminal-kicker">REGRA DE PREENCHIMENTO</span><p>{simulation?.assumptions.fill_rule ?? "Ordem limite estimada a partir de cotações reais posteriores."}</p><p className="cost-warning">{simulation?.assumptions.cost_rule ?? "Taxas e slippage não modelados; P&L bruto."}</p></div>
    </div>

    <div className="terminal-simulation-history"><div className="terminal-mini-heading"><div><span className="terminal-kicker">TRILHA DE DECISÕES</span><h4>Classificações e ordens virtuais</h4></div><span className="terminal-tape-count">{simulation?.decisions.length ?? 0} registros</span></div>
      <div className="terminal-tape-scroll"><table className="terminal-tape"><thead><tr><th>HORÁRIO · SP</th><th>JEV</th><th>FILTRO</th><th>ORDEM / PREENCHIMENTO</th></tr></thead><tbody>{simulation?.decisions.map((item, index) => <tr key={`${item.at}-${index}`}><td>{time(item.at)}</td><td><span className={`terminal-side ${item.stance.toLowerCase()}`}>{item.stance}</span>{item.confidence && <small className="terminal-confidence">{percent(item.confidence)}</small>}</td><td><span className={`terminal-decision-state ${item.status}`}>{decisionLabel(item.status)}</span><small className="terminal-decision-reason">{item.reason}</small></td><td>{item.order ? <><span className={`terminal-side ${item.order.side.toLowerCase()}`}>{item.order.status === "filled" ? "PREENCHIDA" : orderLabel(item.order.status)}</span><small className="terminal-decision-reason">{item.order.status === "filled" ? `${Number(item.order.fill_quantity ?? item.order.quantity).toLocaleString("pt-BR", { maximumFractionDigits: 6 })} MON @ ${price(item.order.fill_price)}` : `${item.order.side} ${Number(item.order.quantity).toLocaleString("pt-BR", { maximumFractionDigits: 6 })} MON @ ${price(item.order.limit_price)}`}</small></> : <span className="terminal-muted">—</span>}</td></tr>)}</tbody></table>{!simulation?.decisions.length && <div className="terminal-empty-note">As avaliações aparecem quando o Jev registrar uma classificação. HOLD, erro e dados fracos não criam ordens.</div>}</div>
    </div>
  </section>;
}

function percent(value?: string) { return value == null ? "—" : `${(Number(value) * 100).toFixed(0)}%`; }
function stanceLabel(choice?: string) { return ({ buy: "BUY", sell: "SELL", hold: "HOLD" } as Record<string, string>)[choice ?? ""] ?? choice?.toUpperCase() ?? "—"; }
function txHash(value?: string | null) { return value && /^0x[a-fA-F0-9]{64}$/.test(value) ? value : null; }
function networkLabel(chainId?: number) { return chainId === 10143 ? "Monad Testnet" : chainId === 143 ? "Monad Mainnet · somente leitura" : chainId ? `Chain ${chainId}` : "aguardando RPC"; }
function txExplorerUrl(hash: string, chainId?: number) { return `${chainId === 10143 ? "https://testnet.monadscan.com" : "https://monadscan.com"}/tx/${hash}`; }
function jevLabel(key: string) { return ({ stance: "Postura", relevance: "Relevância", risk: "Risco", sufficiency: "Dados" } as Record<string, string>)[key] ?? key; }
function choiceLabel(choice?: string) { return ({ buy: "BUY", sell: "SELL", hold: "HOLD", relevant: "relevante", not_relevant: "não relevante", risk_event: "risco", no_risk_event: "sem risco sinalizado", sufficient: "suficientes", insufficient_or_ambiguous: "insuficientes" } as Record<string, string>)[choice ?? ""] ?? choice ?? "—"; }
function decisionLabel(status: string) { return ({ queued: "ORDEM CRIADA", hold: "SEM SINAL", abstain: "ABSTENÇÃO", blocked: "BLOQUEADO" } as Record<string, string>)[status] ?? status.toUpperCase(); }
function orderLabel(status: string) { return ({ open: "PENDENTE", filled: "PREENCHIDA", cancelled: "CANCELADA", expired: "EXPIRADA" } as Record<string, string>)[status] ?? status.toUpperCase(); }
