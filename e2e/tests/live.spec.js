import { expect, test } from "@playwright/test";
import { createEventViaApi, loginAgain, newUser, registerViaApi } from "./helpers.js";

// B8, G5, F6, F7: экран организатора открыт в одном браузере, чекин — в другом,
// регистрация — у третьего пользователя. Счётчики меняются без перезагрузки страницы.
test("счётчики экрана организатора обновляются live", async ({ browser }) => {
  const org = await newUser(browser, "org");
  const eventId = await createEventViaApi(org, { title: "Live E2E", capacity: 5 });
  const alice = await newUser(browser, "alice");
  const bob = await newUser(browser, "bob");
  const aliceCode = (await registerViaApi(alice, eventId)).ticket_code;
  await registerViaApi(bob, eventId);

  const screen = org.page;
  await screen.goto(`/events/${eventId}/organizer`);
  await expect(screen.getByTestId("connection")).toHaveText(/обновляется автоматически/);
  await expect(screen.getByTestId("count-confirmed")).toHaveText("2");
  await expect(screen.getByTestId("count-checked-in")).toHaveText("0");
  // Метка в окне пропадёт, если страница перезагрузится.
  await screen.evaluate(() => (window.noReload = true));

  // Чекин делает второй «контролёр» — тот же организатор в другом браузере.
  const door = await loginAgain(browser, org);
  await door.page.goto(`/events/${eventId}/checkin`);
  await door.page.getByLabel("Код билета").fill(aliceCode.toLowerCase());
  await door.page.getByRole("button", { name: "Отметить" }).click();
  await expect(door.page.getByTestId("checkin-result")).toContainText("Проходите: alice");

  await expect(screen.getByTestId("count-checked-in")).toHaveText("1");
  await expect(screen.locator("tr", { hasText: alice.email })).toContainText("✓");

  // Повторный чекин того же билета отклоняется (B7).
  await door.page.getByLabel("Код билета").fill(aliceCode);
  await door.page.getByRole("button", { name: "Отметить" }).click();
  await expect(door.page.getByTestId("checkin-result")).toContainText("Билет уже отмечен в");

  // Новый участник записывается через интерфейс — счётчик «зарегистрировано» растёт.
  const carol = await newUser(browser, "carol");
  await carol.page.goto(`/events/${eventId}`);
  await carol.page.getByRole("button", { name: "Зарегистрироваться" }).click();
  await expect(carol.page.getByTestId("ticket-code")).toBeVisible();
  await expect(screen.getByTestId("count-confirmed")).toHaveText("3");
  await expect(screen.getByTestId("count-checked-in")).toHaveText("1");

  expect(await screen.evaluate(() => window.noReload)).toBe(true);

  // Участнику экран организатора и чекин недоступны (F8).
  await carol.page.goto(`/events/${eventId}/organizer`);
  await expect(carol.page.getByText("Список участников доступен организатору")).toBeVisible();
  await carol.page.goto(`/events/${eventId}/checkin`);
  await expect(carol.page.getByText("Чекин доступен только организатору события")).toBeVisible();
});
