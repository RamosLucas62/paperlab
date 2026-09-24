import { expect, test } from "@playwright/test";

test("admin can start, pause and export a reproducible DEMO cycle", async ({ page }) => {
  const password = process.env.ADMIN_PASSWORD;
  test.skip(!password, "Set ADMIN_PASSWORD from the local .env before running Playwright.");

  await page.goto("/");
  await page.getByLabel("Usuário").fill(process.env.ADMIN_USERNAME ?? "admin");
  await page.getByLabel("Senha").fill(password!);
  await page.getByRole("button", { name: "Entrar" }).click();

  await expect(page.getByRole("heading", { name: "Terminal JEV" })).toBeVisible();
  await page.getByRole("button", { name: "Visão geral" }).click();
  await expect(page.getByText("DEMONSTRAÇÃO — dados e decisões sintéticos")).toBeVisible();
  await page.getByRole("button", { name: "Experimentos", exact: false }).click();
  await page.getByLabel("Nome do experimento").fill(`Playwright ${Date.now()}`);
  await page.getByRole("button", { name: "＋ Criar experimento" }).click();
  await expect(page.getByText("Novo experimento DEMO criado", { exact: false })).toBeVisible();

  await page.getByRole("button", { name: "Visão geral" }).click();
  await page.getByRole("button", { name: "Iniciar demonstração" }).click();
  await expect(page.getByText("Demonstração iniciada", { exact: false })).toBeVisible();
  await page.getByRole("button", { name: "Decisões e ordens" }).click();
  const baseTrace = page.locator("details.decision-detail").filter({ has: page.locator("summary .table-arm.a") }).first();
  await baseTrace.locator("summary").click();
  await expect(baseTrace.getByText("Cruzamento de alta confirmado", { exact: false })).toBeVisible();

  await page.getByRole("button", { name: "Visão geral" }).click();
  await page.getByRole("button", { name: "Pausar entradas" }).click();
  await expect(page.getByText("Novas entradas pausadas", { exact: false })).toBeVisible();
  await page.getByRole("button", { name: "Experimentos", exact: false }).click();
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Exportar JSON" }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toMatch(/paperlab-.*\.json/);
});
