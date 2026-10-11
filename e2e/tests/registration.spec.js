import { expect, test } from "@playwright/test";
import { bishkekInput, newUser } from "./helpers.js";

// F1–F5, B1–B4, G4: событие через форму, регистрация, лист ожидания, отказ, продвижение, письма.
test("регистрация, лист ожидания, отказ и продвижение очереди", async ({ browser }) => {
  const org = await newUser(browser, "org");
  const alice = await newUser(browser, "alice");
  const bob = await newUser(browser, "bob");

  // Организатор создаёт событие на одно место через форму.
  await org.page.goto("/events/new");
  await org.page.getByLabel("Название").fill("Митап E2E");
  await org.page.getByLabel("Описание").fill("Проверка очереди");
  await org.page.getByLabel("Дата и время начала").fill(bishkekInput(new Date(Date.now() + 2 * 3600_000)));
  await org.page.getByLabel("Лимит мест").fill("1");
  await org.page.getByRole("button", { name: "Создать" }).click();
  await expect(org.page.getByRole("heading", { name: "Митап E2E" })).toBeVisible();
  const eventUrl = new URL(org.page.url()).pathname;

  // Alice получает место; двойной клик не создаёт второй записи и второго письма (B2).
  await alice.page.goto(eventUrl);
  await alice.page.getByRole("button", { name: "Зарегистрироваться" }).dblclick();
  const aliceCode = (await alice.page.getByTestId("ticket-code").textContent()).trim();
  expect(aliceCode).toMatch(/^[A-Z2-9]{10}$/);

  // Bob попадает в лист ожидания (B3, F4).
  await bob.page.goto(eventUrl);
  await bob.page.getByRole("button", { name: "Зарегистрироваться" }).click();
  await expect(bob.page.getByText("Вы в листе ожидания, позиция 1")).toBeVisible();

  // Письмо с билетом у alice ровно одно и с её кодом (B1, G4).
  await alice.page.goto("/mail");
  const aliceMail = alice.page.locator(".card");
  await expect(aliceMail).toHaveCount(1);
  await expect(aliceMail.first()).toContainText(aliceCode);

  // Alice отказывается — место и письмо с билетом получает bob (F3, B4).
  await alice.page.goto(eventUrl);
  alice.page.once("dialog", (dialog) => dialog.accept());
  await alice.page.getByRole("button", { name: "Отказаться" }).click();
  await expect(alice.page.getByText("Вы отказались от участия")).toBeVisible();

  await bob.page.goto("/my");
  const bobCode = (await bob.page.getByTestId("ticket-code").textContent()).trim();
  expect(bobCode).not.toBe(aliceCode);
  await bob.page.goto("/mail");
  const promoted = bob.page.locator(".card", { hasText: "Место из листа ожидания" });
  await expect(promoted).toHaveCount(1);
  await expect(promoted).toContainText(bobCode);
});
