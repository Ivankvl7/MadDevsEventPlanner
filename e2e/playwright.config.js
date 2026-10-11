import { defineConfig, devices } from "@playwright/test";

// Тесты идут против уже запущенного приложения (по умолчанию — docker compose, порт 8080).
export default defineConfig({
  testDir: "./tests",
  timeout: 60_000,
  expect: { timeout: 10_000 },
  workers: 1,
  reporter: "list",
  use: {
    baseURL: process.env.E2E_BASE_URL || "http://localhost:8080",
    // Пояс браузера фиксирован: от него зависят поля даты (R-13).
    timezoneId: "Asia/Bishkek",
    locale: "ru-RU",
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
