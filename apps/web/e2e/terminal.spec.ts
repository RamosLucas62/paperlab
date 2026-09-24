import { expect, test } from "@playwright/test";

test("terminal displays a shadow Jev posture without creating an order", async ({ page }) => {
  const password = process.env.ADMIN_PASSWORD;
  test.skip(!password, "Set temporary administrator credentials before running Playwright.");

  await page.route("**/api/terminal", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({
      configuration: {
        market_configured: true, market_address_hint: "0x1234…abcd", symbol: "MON/USDC", chain_id: 10143,
        rpc_configured: true, jev_configured: true, jev_model: "typesafe/jev-1.13",
        ai_call_budget_usd: "0.10", ai_daily_budget_usd: "2.00", jev_interval_seconds: 120,
      },
      control: {
        monitor_enabled: true, jev_enabled: true, status: "connected", last_error: null,
        last_block_number: 101, last_sample_at: "2026-09-24T13:00:00Z", last_jev_at: "2026-09-24T13:00:00Z",
      },
      market: { symbol: "MON/USDC", best_bid: "0.024", best_ask: "0.025", mid_price: "0.0245", spread_bps: "408", block_number: 101, observed_at: "2026-09-24T13:00:00Z" },
      samples: [{ at: "2026-09-24T13:00:00Z", mid_price: "0.0245", best_bid: "0.024", best_ask: "0.025", spread_bps: "408" }],
      events: [],
      jev_observations: [{
        at: "2026-09-24T13:00:00Z", status: "ready", model: "typesafe/jev-1.13",
        result: {
          stance: { choice: "hold", confidence: "0.72", probabilities: { buy: "0.10", sell: "0.18", hold: "0.72" } },
          relevance: { choice: "relevant", confidence: "0.98" },
          risk: { choice: "no_risk_event", confidence: "0.90" },
          sufficiency: { choice: "sufficient", confidence: "0.95" },
        },
        message: "Postura BUY/SELL/HOLD somente observacional; não é ordem nem recomendação.",
        cost_usd: "0.002", cost_status: "reported", latency_ms: 81,
      }],
      safety: { orders_enabled: false, transaction_signing: false, mode: "read_only_shadow" },
    }),
  }));

  await page.goto("/");
  await page.getByLabel("Usuário").fill(process.env.ADMIN_USERNAME ?? "admin");
  await page.getByLabel("Senha").fill(password!);
  await page.getByRole("button", { name: "Entrar" }).click();

  await expect(page.getByText("POSTURA OBSERVACIONAL")).toBeVisible();
  await expect(page.getByText("HOLD", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("72% confiança reportada")).toBeVisible();
  await expect(page.getByText("O PaperLab não assina transações", { exact: false })).toBeVisible();
});
