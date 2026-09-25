"use client";

import { useCallback, useEffect, useState } from "react";

type Arm = { cash_usdc: string; position_qty: string; equity_usdc: string | null; trades: number; execution_cost_usdc: string };
type Evaluation = { at: string; signal: string; reason: string; baseline_action: string; ai_choice: string | null; ai_confidence: string | null; ai_status: string; ai_action: string; latency_ms: number | null };
type Trade = { at: string; arm: string; side: string; quantity: string; price: string; cost_usdc: string };
type Order = { at: string; arm: string; side: string; status: string; price: string; quantity: string };
type PilotData = {
  run: { status: string; started_at: string; ends_at: string; finished_at: string | null; evaluation_count: number; model_cost_usdc: string; model_unknown_calls: number } | null;
  arms: { baseline: Arm; ai: Arm } | null;
  evaluations: Evaluation[]; trades: Trade[]; orders: Order[];
  rules: { decision_interval_seconds: number; fee_bps_each_fill: string; execution_uncertainty_bps_each_fill: string; gas_usdc_each_fill: string };
  feed: { status: string; error: string | null; sample_at: string | null; mid_price: string | null; ready: boolean; model_ready: boolean };
};

const money = (value: string | number | null | undefined) => value == null ? "—" : new Intl.NumberFormat("pt-BR", { style: "currency", currency: "USD" }).format(Number(value));
const date = (value: string | null | undefined) => value ? new Intl.DateTimeFormat("pt-BR", { timeZone: "America/Sao_Paulo", dateStyle: "short", timeStyle: "short" }).format(new Date(value)) : "—";
const number = (value: number, digits = 1) => value.toLocaleString("pt-BR", { maximumFractionDigits: digits, minimumFractionDigits: digits });
const label = (action: string | null | undefined) => action === "BUY" ? "Comprou" : action === "SELL" ? "Vendeu" : action === "HOLD" ? "Aguardou" : "—";
const aiStatus: Record<string, string> = { pending: "Analisando", ready: "Decisão recebida", data_blocked: "Dados insuficientes", no_candidate: "Sem oportunidade detectada", budget_blocked: "Limite de custo", low_confidence: "Confiança insuficiente", stale: "Preço mudou durante análise", ineligible: "Operação indisponível", failed: "Falha na consulta", cancelled: "Consulta cancelada", not_called: "Sem consulta" };

async function request<T>(path: string, csrf: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("X-CSRF-Token", csrf);
  if (init.body) headers.set("Content-Type", "application/json");
  const response = await fetch(path, { ...init, headers, credentials: "same-origin", cache: "no-store" });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail ?? `Erro ${response.status}.`);
  return body as T;
}

export default function PilotV2({ csrf }: { csrf: string }) {
  const [data, setData] = useState<PilotData | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [now, setNow] = useState(0);
  const refresh = useCallback(async () => {
    const next = await request<PilotData>("/api/pilot-v2", csrf);
    setData(next); setNow(Date.now()); setError("");
  }, [csrf]);
  useEffect(() => {
    void refresh().catch((err) => setError(err instanceof Error ? err.message : "Não foi possível carregar o piloto."));
    const timer = window.setInterval(() => void refresh().catch((err) => setError(err instanceof Error ? err.message : "Não foi possível atualizar o piloto.")), 5000);
    return () => window.clearInterval(timer);
  }, [refresh]);
  async function control(action: "start" | "pause" | "resume") {
    setBusy(true); setError("");
    try {
      await request("/api/pilot-v2/control", csrf, { method: "POST", body: JSON.stringify({ action }) });
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível alterar o piloto.");
      void refresh().catch(() => {});
    } finally { setBusy(false); }
  }

  const run = data?.run;
  const ai = data?.arms?.ai;
  const baseline = data?.arms?.baseline;
  const latest = data?.evaluations[0];
  const openOrders = data?.orders.filter((order) => order.status === "open") ?? [];
  const feedFresh = Boolean(data?.feed.sample_at && now - new Date(data.feed.sample_at).getTime() < 30_000);
  const elapsed = run && now ? Math.max(0, Math.min(5, (now - new Date(run.started_at).getTime()) / 86_400_000)) : 0;
  const progress = Math.min(100, elapsed / 5 * 100);
  const aiEquity = ai?.equity_usdc == null ? null : Number(ai.equity_usdc);
  const baselineEquity = baseline?.equity_usdc == null ? null : Number(baseline.equity_usdc);
  const difference = aiEquity == null || baselineEquity == null ? null : aiEquity - baselineEquity;
  const running = run?.status === "running";
  const canStart = Boolean(data?.feed.ready && data?.feed.model_ready);

  return <section className="v2" aria-label="Piloto de negociação virtual">
    <div className="v2-heading"><div><span className="v2-kicker">PILOTO DE 5 DIAS · MON/USDC</span><h1>O robô de IA consegue superar uma regra simples?</h1><p>O bot lê o livro da Kuru, consulta o Jev e simula operações com US$ 1.000. Nenhum dinheiro real é movimentado.</p></div><span className={`v2-pill ${running && feedFresh ? "live" : ""}`}>{!run ? "Ainda não iniciado" : run.status === "finished" ? "Concluído" : run.status === "awaiting_close" || now > new Date(run.ends_at).getTime() ? "Aguardando cotação final" : running ? "Em andamento" : "Pausado"}</span></div>

    {error && <div className="v2-alert" role="alert">{error}</div>}
    {data?.feed.error && <div className="v2-alert" role="status">Conexão com o mercado: {data.feed.error}</div>}
    {data && !canStart && <div className="v2-alert">Falta configurar o mercado Kuru ou a chave e o modelo Jev no servidor.</div>}

    <div className="v2-control"><div><strong>{feedFresh ? "Mercado conectado" : "Aguardando cotação recente"}</strong><span>Última cotação: {date(data?.feed.sample_at)} · Preço MON/USDC: {data?.feed.mid_price ? Number(data.feed.mid_price).toFixed(6) : "—"} · Decisão a cada {data?.rules.decision_interval_seconds ?? 5}s enquanto houver feed e orçamento</span></div>{run?.status !== "finished" && <button className={`pilot-button ${running ? "secondary" : "primary"}`} disabled={busy || (!running && !canStart)} onClick={() => control(running ? "pause" : run ? "resume" : "start")}>{busy ? "Aguarde…" : running ? "Pausar teste" : run ? "Retomar teste" : "Iniciar novo teste"}</button>}</div>

    <div className="v2-goal"><div><span>META QUE ESTAMOS INVESTIGANDO</span><strong>US$ 1.000 → US$ 10.000</strong><small>em 90 dias</small></div><p>Em cinco dias observamos se o robô encontra oportunidades e se o saldo virtual melhora após custos estimados. O resultado de cinco dias não demonstra que a meta de 90 dias é alcançável. A régua matemática para o 5º dia seria {money(1000 * Math.pow(10, 5 / 90))}.</p></div>

    <div className="v2-progress"><div><span>{run ? `Início ${date(run.started_at)} · fim ${date(run.ends_at)}` : "O prazo começa quando o novo teste for iniciado."}</span><strong>{number(elapsed)} de 5 dias</strong></div><div className="v2-track"><span style={{ width: `${progress}%` }} /></div></div>

    <div className="v2-cards"><article className="v2-card feature"><span>COM JEV</span><strong>{money(ai?.equity_usdc)}</strong><p>{aiEquity == null ? "Aguardando cotação para avaliar a posição." : `${aiEquity >= 1000 ? "+" : ""}${money(aiEquity - 1000)} desde o início`}</p><small>{ai?.trades ?? 0} preenchimentos virtuais · posição {Number(ai?.position_qty ?? 0).toLocaleString("pt-BR", { maximumFractionDigits: 2 })} MON</small></article><article className="v2-card"><span>REGRA SEM IA</span><strong>{money(baseline?.equity_usdc)}</strong><p>Mesmo mercado e mesmo capital inicial.</p><small>{baseline?.trades ?? 0} preenchimentos virtuais</small></article><article className="v2-card"><span>DIFERENÇA DO JEV</span><strong className={difference != null && difference < 0 ? "negative" : ""}>{difference == null ? "—" : `${difference > 0 ? "+" : ""}${money(difference)}`}</strong><p>Diferença entre as duas carteiras virtuais.</p><small>Custos do modelo entram na carteira com Jev.</small></article></div>

    <div className="v2-columns"><article className="v2-panel"><span className="v2-kicker">ÚLTIMA LEITURA</span><h2>O que o Jev decidiu?</h2><div className="v2-decision"><strong>{label(latest?.ai_choice) || "—"}</strong><span>{latest ? aiStatus[latest.ai_status] ?? latest.ai_status : "Aguardando primeira análise"}</span></div><p>{latest?.reason ?? "O teste ainda não tem uma leitura do livro de ofertas."}</p><div className="v2-facts"><div><span>Confiança</span><strong>{latest?.ai_confidence ? `${number(Number(latest.ai_confidence) * 100, 0)}%` : "—"}</strong></div><div><span>Tempo da resposta</span><strong>{latest?.latency_ms == null ? "—" : `${latest.latency_ms} ms`}</strong></div><div><span>Ordem criada</span><strong>{label(latest?.ai_action)}</strong></div><div><span>Análises feitas</span><strong>{run?.evaluation_count ?? 0}</strong></div></div><small>Uma decisão de compra ou venda pode ser bloqueada por confiança, posição, preço antigo ou limite de custo.</small></article><article className="v2-panel"><span className="v2-kicker">ORDENS VIRTUAIS</span><h2>O que aconteceu depois?</h2><div className="v2-facts"><div><span>Pendentes agora</span><strong>{openOrders.length}</strong></div><div><span>Preenchimentos Jev</span><strong>{ai?.trades ?? 0}</strong></div><div><span>Custo estimado das operações</span><strong>{money(ai?.execution_cost_usdc)}</strong></div><div><span>OpenRouter informado</span><strong>{money(run?.model_cost_usdc)}</strong></div></div><p>{data?.trades.length ? "As últimas operações virtuais aparecem abaixo." : "Ainda não houve ordem virtual preenchida. Isso pode acontecer mesmo com o mercado ativo."}</p>{Boolean(run?.model_unknown_calls) && <small>{run?.model_unknown_calls} chamadas sem custo informado pelo provedor; o saldo pode superestimar o resultado.</small>}</article></div>

    <details className="v2-history"><summary>Ver decisões e operações recentes</summary><div className="v2-history-content"><h3>Operações virtuais</h3>{data?.trades.length ? <div className="v2-table-wrap"><table><thead><tr><th>Horário</th><th>Carteira</th><th>Ação</th><th>Preço</th><th>Custo estimado</th></tr></thead><tbody>{data.trades.map((trade, index) => <tr key={`${trade.at}-${index}`}><td>{date(trade.at)}</td><td>{trade.arm === "ai" ? "Jev" : "Regra"}</td><td>{label(trade.side)}</td><td>{Number(trade.price).toFixed(6)}</td><td>{money(trade.cost_usdc)}</td></tr>)}</tbody></table></div> : <p>Nenhuma operação preenchida.</p>}<h3>Leituras do livro</h3>{data?.evaluations.length ? <div className="v2-table-wrap"><table><thead><tr><th>Horário</th><th>Regra</th><th>Jev</th><th>Situação</th><th>Tempo</th></tr></thead><tbody>{data.evaluations.map((item, index) => <tr key={`${item.at}-${index}`}><td>{date(item.at)}</td><td>{label(item.baseline_action)}</td><td>{label(item.ai_choice)}</td><td>{aiStatus[item.ai_status] ?? item.ai_status}</td><td>{item.latency_ms == null ? "—" : `${item.latency_ms} ms`}</td></tr>)}</tbody></table></div> : <p>Nenhuma leitura ainda.</p>}</div></details>

    <div className="v2-method"><strong>Como a simulação funciona</strong><p>O bot observa o topo do livro da Kuru e o movimento recente a cada poucos segundos; consulta o Jev quando encontra uma oportunidade ou quando já possui posição virtual. Se uma ordem virtual limitada for tocada por uma cotação posterior, registra um preenchimento. A conta inclui uma hipótese de {data?.rules.fee_bps_each_fill ?? 10} bps de taxa, {data?.rules.execution_uncertainty_bps_each_fill ?? 5} bps de incerteza na execução e {money(data?.rules.gas_usdc_each_fill ?? 0.02)} por preenchimento. Não mede a posição na fila, profundidade suficiente para US$ 1.000 nem impacto no preço; por isso o resultado ainda pode ser otimista. Não há carteira conectada ou envio de transações.</p></div>
  </section>;
}
