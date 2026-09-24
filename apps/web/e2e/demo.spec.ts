import { expect, test } from "@playwright/test";

test("the main screen focuses on the five-day virtual pilot", async ({ page }) => {
  const password = process.env.ADMIN_PASSWORD;
  test.skip(!password, "Set ADMIN_PASSWORD from the local .env before running Playwright.");

  await page.goto("/");
  await page.getByLabel("Usuário").fill(process.env.ADMIN_USERNAME ?? "admin");
  await page.getByLabel("Senha").fill(password!);
  await page.getByRole("button", { name: "Entrar" }).click();

  await expect(page.getByRole("heading", { name: "Um robô de IA vale um teste real?" })).toBeVisible();
  await expect(page.getByText("CARTEIRA VIRTUAL AGORA")).toBeVisible();
  await expect(page.getByText("META DE LONGO PRAZO")).toBeVisible();
  await expect(page.getByRole("button", { name: "Visão geral" })).toHaveCount(0);
});
