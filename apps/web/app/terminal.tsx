"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

type Order = { side: string; status: string; quantity: string; limit_price: string; notional_usdc: string; at: string; filled_at: string | null; fill_price: string | null };
type Pilot = { started_at: string; ends_at: string; finished_at: string | null; status: "running" | "paused" | "awaiting_close" | "finished"; decision_count: number; filled_order_count: number; ai_cost_reported_usd: string | null; ai_cost_unknown_count: number; final_equity_usdc: string | null; days: number; goal_days: number; goal_equity_usdc: string };
type TerminalData = {
  configuration: { market_configured: boolean; kuru_feed_configured: boolean; symbol: string; chain_id: number; jev_configured: boolean; jev_model: string; ai_daily_budget_usd: string; jev_interval_seconds: number };
  control: { monitor_enabled: boolean; jev_enabled: boolean; simulation_enabled: boolean; status: string; last_error: string | null; last_sample_at: string | null; last_block_number: number | null };
  market: { mid_price: string; best_bid: string; best_ask: string; observed_at: string } | null;
  samples: { at: string; mid_price: string }[];
  jev_observations: { at: string; status: string; result: Record<string, { choice?: string; confidence?: string }> | null; cost_usd: string | null; cost_status: string }[];
  simulation: {
    enabled: boolean;
    pilot: Pilot | null;
    account: { starting_cash_usdc: string; cash_usdc: string; position_qty: string; equity_usdc: string | null; total_pnl_usdc: string | null; mark_stale: boolean } | null;
    open_order: Order | null;
    orders: Order[];
    decisions: { stance: string; status: string; reason: string; at: string; order: Order | null }[];
    assumptions: { order_notional_usdc: string; minimum_confidence: string; fill_rule: string; cost_rule: string };
  };
};

const usd = (value?: string | number | null) => value == null ? "—" : new Intl.NumberFormat("pt-BR", { style: "currency", currency: "USD" }).format(Number(value));
const decimal = (value?: string | number | null, digits = 2) => value == null ? "—" : Number(value).toLocaleString("pt-BR", { minimumFractionDigits: digits, maximumFractionDigits: digits });
const date = (value?: string | null) => value ? new Intl.DateTimeFormat("pt-BR", { timeZone: "America/Sao_Paulo", dateStyle: "short", timeStyle: "short" }).format(new Date(value)) : "—";
const clock = (value?: string | null) => value ? new Intl.DateTimeFormat("pt-BR", { timeZone: "America/Sao_Paulo", hour: "2-digit", minute: "2-digit" }).format(new Date(value)) : "—";

async function request<T>(path: string, csrf: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("X-CSRF-Token", csrf);
  if (init.body) headers.set("Content-Type", "application/json");
  const response = await fetch(path, { ...init, headers, credentials: "same-origin", cache: "no-store" });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail ?? `A solicitação falhou (HTTP ${response.status}).`);
  return body as T;
}

function MarketChart({ samples }: { samples: TerminalData["samples"] }) {
  const path = useMemo(() => {
    const values = samples.map((sample) => Number(sample.mid_price)).filter(Number.isFinite);
    if (!values.length) return "";
    const low = Math.min(...values), high = Math.max(...values);
    const pad = (high - low) * 0.15 || high * 0.001 || 0.001;
    return values.map((value, index) => `${index ? "L" : "M"}${values.length === 1 ? 500 : 16 + index * 968 / (values.length - 1)},${230 - (value - low + pad) * 210 / (high - low + pad * 2)}`).join(" ");
  }, [samples]);
  return <div className="pilot-chart-wrap">{path ? <svg viewBox="0 0 1000 250" role="img" aria-label="Preço recente observado na Kuru" preserveAspectRatio="none"><line x1="0" y1="125" x2="1000" y2="125" /><path d={path} /></svg> : <p>Aguardando as primeiras cotações do mercado.</p>}</div>;
}

export default function MarketTerminal({ csrf, onMessage }: { csrf: string; onMessage: (message: string) => void }) {
  const [data, setData] = useState<TerminalData | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [now, setNow] = useState<number | null>(null);
  const refresh = useCallback(async () => {
    const next = await request<TerminalData>("/api/terminal", csrf);
    setData(next); setError(""); setNow(Date.now());
  }, [csrf]);
  useEffect(() => {
    void refresh().catch((err) => setError(err instanceof Error ? err.message : "Não foi possível carregar o piloto."));
    const timer = window.setInterval(() => void refresh().catch((err) => setError(err instanceof Error ? err.message : "Não foi possível atualizar o piloto.")), 5000);
    return () => window.clearInterval(timer);
  }, [refresh]);
  async function control(action: "start_pilot" | "pause_pilot") {
    setBusy(true); setError("");
    try {
      await request("/api/terminal/control", csrf, { method: "POST", body: JSON.stringify({ action }) });
      await refresh();
      onMessage(action === "start_pilot" ? "Piloto solicitado. O prazo começa na primeira cotação válida da Kuru." : "Piloto pausado. O prazo de cinco dias continua correndo; as ordens pendentes foram canceladas.");
    } catch (err) { setError(err instanceof Error ? err.message : "A ação não foi concluída."); }
    finally { setBusy(false); }
  }

  const account = data?.simulation.account;
  const pilot = data?.simulation.pilot;
  const initial = Number(account?.starting_cash_usdc ?? 1000);
  const equity = account?.equity_usdc == null ? null : Number(account.equity_usdc);
  const pnl = account?.total_pnl_usdc == null ? null : Number(account.total_pnl_usdc);
  const returnPct = pnl == null ? null : pnl / initial * 100;
  const elapsed = pilot && now ? Math.max(0, Math.min(pilot.days, (now - new Date(pilot.started_at).getTime()) / 86_400_000)) : 0;
  const daysLeft = pilot && now ? Math.max(0, (new Date(pilot.ends_at).getTime() - now) / 86_400_000) : null;
  const paceEquity = initial * Math.pow(Number(pilot?.goal_equity_usdc ?? 10000) / initial, Number(pilot?.days ?? 5) / Number(pilot?.goal_days ?? 90));
  const feedFresh = data?.control.last_sample_at && now ? now - new Date(data.control.last_sample_at).getTime() < 30_000 : false;
  const running = Boolean(data?.control.simulation_enabled && data?.control.jev_enabled && data?.control.monitor_enabled);
  const ready = Boolean(data?.configuration.market_configured && data?.configuration.kuru_feed_configured && data?.configuration.jev_configured);
  const latestDecision = data?.simulation.decisions[0];
  const lastJev = data?.jev_observations[0];
  const network = data?.configuration.chain_id === 143 ? "Monad Mainnet" : data?.configuration.chain_id === 10143 ? "Monad Testnet" : "Monad";
  const stateLabel = !pilot ? "Ainda não iniciado" : pilot.status === "finished" ? "Concluído" : pilot.status === "awaiting_close" ? "Aguardando cotação final" : running ? "Em andamento" : "Pausado";

  return <section className="pilot-view" aria-label="Piloto de cinco dias">
    <div className="pilot-intro">
      <div><span className="pilot-eyebrow">EXPERIMENTO · CAPITAL VIRTUAL</span><h1>Um robô de IA vale um teste real?</h1><p>Observe por cinco dias como ele decide e como uma carteira simulada de {usd(initial)} evolui no mercado MON/USDC.</p></div>
      <span className="pilot-status"><i className={running && feedFresh ? "live" : ""} />{stateLabel}</span>
    </div>

    <div className="pilot-goal-strip"><div><span>META DE LONGO PRAZO</span><strong>{usd(initial)} → {usd(pilot?.goal_equity_usdc ?? 10000)}</strong><small>em 90 dias · hipótese a avaliar</small></div><p>Em cinco dias, medimos comportamento, operações e resultado virtual. Esse período não confirma que o desempenho continuaria por 90 dias.</p></div>
    <div className="pilot-verdict"><strong>{!pilot ? "Avaliação ainda não iniciada" : pilot.status === "finished" ? "Cinco dias concluídos; evidência ainda limitada" : (pilot.filled_order_count === 0 ? "Ainda não há operações para avaliar" : "Piloto em observação")}</strong><span>{!pilot ? "Inicie o piloto para registrar decisões e resultado virtual." : pilot.status === "finished" ? "Antes de considerar dinheiro real, ainda é preciso testar exposição compatível com US$ 1.000, custos de execução e um período maior." : pilot.filled_order_count === 0 ? "O robô pode optar por não operar quando os filtros rejeitam os sinais. Isso também é um resultado do teste." : "Acompanhe saldo, perdas e motivos das decisões até o encerramento do quinto dia."}</span></div>

    {error && <div className="pilot-error" role="alert">{error}</div>}
    {data?.control.last_error && <div className="pilot-error" role="status">Conexão: {data.control.last_error}</div>}
    {!ready && data && <div className="pilot-setup"><strong>Configuração incompleta</strong><span>Confira no EasyPanel o endereço do mercado Kuru, o feed WSS e a chave/modelo OpenRouter. O piloto começa após esses dados estarem disponíveis.</span></div>}

    <div className="pilot-action-row">
      <div><strong>{pilot ? `Início ${date(pilot.started_at)} · término previsto ${date(pilot.ends_at)}` : "O relógio começa com a primeira cotação válida."}</strong><span>{feedFresh ? `Feed Kuru ativo · última cotação ${clock(data?.control.last_sample_at)}` : "Feed sem cotação recente"} · {network} · somente leitura</span></div>
      {pilot?.status !== "finished" && (running ? <button className="pilot-button secondary" disabled={busy} onClick={() => control("pause_pilot")}>Pausar piloto</button> : <button className="pilot-button primary" disabled={busy || !ready} onClick={() => control("start_pilot")}>{pilot?.status === "awaiting_close" ? "Obter cotação final" : pilot ? "Retomar piloto" : "Iniciar piloto de 5 dias"}</button>)}
    </div>

    <section className="pilot-scoreboard" aria-label="Resultado do piloto">
      <article className="pilot-lead-metric"><span>CARTEIRA VIRTUAL AGORA</span><strong>{usd(equity)}</strong><small>{account?.mark_stale && Number(account.position_qty) > 0 && pilot?.status !== "finished" ? "Sem cotação recente para marcar a posição" : "Caixa + posição a preço observado · bruto"}</small></article>
      <article><span>GANHO OU PERDA</span><strong className={pnl == null ? "" : pnl < 0 ? "down" : pnl > 0 ? "up" : ""}>{pnl == null ? "—" : `${pnl > 0 ? "+" : ""}${usd(pnl)}`}</strong><small>{returnPct == null ? "Aguardando início" : `${returnPct > 0 ? "+" : ""}${decimal(returnPct)}% sobre ${usd(initial)}`}</small></article>
      <article><span>TEMPO DO PILOTO</span><strong>{pilot ? `${decimal(elapsed, 1)} / ${pilot.days} dias` : "0 / 5 dias"}</strong><small>{pilot?.status === "finished" ? `Fechado ${date(pilot.finished_at)}` : daysLeft == null ? "Aguardando primeira cotação" : `${decimal(daysLeft, 1)} dias até o fim`}</small></article>
      <article><span>ORDENS PREENCHIDAS</span><strong>{pilot?.filled_order_count ?? 0}</strong><small>{pilot?.decision_count ?? 0} decisões avaliadas · {data?.simulation.open_order ? "1 ordem pendente" : "sem ordem pendente"}</small></article>
    </section>

    <section className="pilot-progress" aria-label="Progresso dos cinco dias"><div className="pilot-progress-head"><strong>Janela de observação</strong><span>{pilot ? `${decimal(elapsed / pilot.days * 100, 0)}% do período` : "Ainda não iniciada"}</span></div><div className="pilot-progress-track"><span style={{ width: `${pilot ? Math.min(100, elapsed / pilot.days * 100) : 0}%` }} /></div><div className="pilot-progress-foot"><span>Dia 0 · {pilot ? date(pilot.started_at) : "—"}</span><span>Dia 5 · {pilot ? date(pilot.ends_at) : "—"}</span></div></section>

    <div className="pilot-two-col">
      <article className="pilot-card"><div className="pilot-card-head"><div><span className="pilot-eyebrow">CONTEXTO DA META</span><h2>Qual seria o ritmo necessário?</h2></div><strong>{usd(paceEquity)}</strong></div><p>Para transformar {usd(initial)} em {usd(pilot?.goal_equity_usdc ?? 10000)} em 90 dias com crescimento uniforme, o saldo precisaria chegar perto de {usd(paceEquity)} após cinco dias. É só uma régua matemática, não uma previsão.</p><div className="pilot-compare"><span>Resultado observado</span><strong>{usd(equity)}</strong><span>Régua após 5 dias</span><strong>{usd(paceEquity)}</strong></div><small>Mesmo superar essa régua por cinco dias não comprova a meta de 90 dias.</small></article>
      <article className="pilot-card"><div className="pilot-card-head"><div><span className="pilot-eyebrow">ÚLTIMA DECISÃO</span><h2>O que o robô fez?</h2></div><strong>{latestDecision ? latestDecision.status === "queued" ? "Ordem virtual" : latestDecision.status === "hold" ? "Aguardou" : "Não operou" : "Aguardando"}</strong></div><p>{latestDecision?.reason ?? "Aguardando a primeira análise do Jev. O robô só cria ordem virtual quando todos os filtros aprovam a leitura."}</p><div className="pilot-compare"><span>Última análise</span><strong>{clock(latestDecision?.at)}</strong><span>Modelo</span><strong>{data?.configuration.jev_model ?? "—"}</strong></div><small>{lastJev?.status === "ready" ? "Classificação recebida da OpenRouter." : running ? "Aguardando ou reavaliando dados." : "O modelo roda apenas enquanto o piloto está ativo."}</small></article>
    </div>

    <section className="pilot-card pilot-market"><div className="pilot-card-head"><div><span className="pilot-eyebrow">DADOS REAIS · CARTEIRA VIRTUAL</span><h2>Mercado MON/USDC</h2></div><strong>{data?.market ? decimal(data.market.mid_price, 6) : "—"}</strong></div><MarketChart samples={data?.samples ?? []} /><div className="pilot-chart-foot"><span>Preço de mercado observado; o gráfico não representa o patrimônio.</span><span>{data?.samples.length ?? 0} amostras recentes</span></div></section>

    <section className="pilot-card pilot-reality"><span className="pilot-eyebrow">O QUE ESTE PILOTO AINDA NÃO MEDE</span><h2>Como ler o resultado</h2><div className="pilot-reality-grid"><p><strong>US$ 10 por ordem</strong>O simulador atual usa apenas {usd(data?.simulation.assumptions.order_notional_usdc ?? 10)} por entrada. Com essa exposição, o teste não representa uma estratégia que utiliza todo o capital de {usd(initial)}.</p><p><strong>Retorno bruto</strong>Taxas, gas, slippage, fila do livro e impacto no preço não estão incluídos. O resultado real pode ser menor.</p><p><strong>Cinco dias de amostra</strong>{pilot?.filled_order_count ? `${pilot.filled_order_count} preenchimentos virtuais registrados.` : "Nenhum preenchimento virtual até agora."} Poucas operações não sustentam uma conclusão sobre três meses.</p><p><strong>Custo do modelo</strong>{pilot?.ai_cost_reported_usd ? `${usd(pilot.ai_cost_reported_usd)} reportados pela OpenRouter.` : "Ainda sem custo reportado."}{pilot?.ai_cost_unknown_count ? ` ${pilot.ai_cost_unknown_count} chamadas têm custo desconhecido.` : ""}</p></div></section>

    <details className="pilot-details"><summary>Ver decisões, ordens e detalhes do método</summary><div className="pilot-details-content"><h2>Decisões recentes</h2>{data?.simulation.decisions.length ? <div className="pilot-table-scroll"><table><thead><tr><th>Horário</th><th>Leitura</th><th>Resultado</th><th>Motivo</th></tr></thead><tbody>{data.simulation.decisions.map((item, index) => <tr key={`${item.at}-${index}`}><td>{date(item.at)}</td><td>{item.stance}</td><td>{item.order ? `${item.order.side} · ${item.order.status}` : item.status}</td><td>{item.reason}</td></tr>)}</tbody></table></div> : <p>Ainda não há decisões neste piloto.</p>}<h2>Regras atuais</h2><p>Confiança mínima de {decimal(Number(data?.simulation.assumptions.minimum_confidence ?? 0.8) * 100, 0)}%. {data?.simulation.assumptions.fill_rule}</p><p>{data?.simulation.assumptions.cost_rule}</p><p>Caixa virtual: {usd(account?.cash_usdc)} · posição: {decimal(account?.position_qty ?? 0, 4)} MON. Não há carteira conectada, assinatura ou envio de transações.</p></div></details>
  </section>;
}
