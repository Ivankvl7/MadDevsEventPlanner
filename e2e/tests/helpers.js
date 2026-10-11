// Общие шаги сценариев. Каждый пользователь — отдельный контекст браузера (свои cookie),
// как отдельный человек со своим браузером.

export const PASSWORD = "password123";

// Email уникален: тесты можно запускать повторно на той же базе.
const run = Date.now().toString(36);
let seq = 0;

export async function newUser(browser, name) {
  const email = `${name}-${run}-${++seq}@example.com`;
  const context = await browser.newContext();
  const response = await context.request.post("/api/auth/register", {
    data: { email, password: PASSWORD, name },
  });
  if (!response.ok()) throw new Error(`регистрация ${name}: ${response.status()}`);
  return { context, page: await context.newPage(), email, name };
}

// Ещё одна «вкладка» уже существующего пользователя на другом устройстве: свой вход.
export async function loginAgain(browser, user) {
  const context = await browser.newContext();
  const response = await context.request.post("/api/auth/login", {
    data: { email: user.email, password: PASSWORD },
  });
  if (!response.ok()) throw new Error(`вход ${user.name}: ${response.status()}`);
  return { ...user, context, page: await context.newPage() };
}

export async function createEventViaApi(user, { title, capacity, hoursFromNow = 2 }) {
  const startsAt = new Date(Date.now() + hoursFromNow * 3600_000).toISOString();
  const response = await user.context.request.post("/api/events", {
    data: { title, description: "", starts_at: startsAt, timezone: "Asia/Bishkek", capacity },
  });
  if (!response.ok()) throw new Error(`событие: ${response.status()}`);
  return (await response.json()).id;
}

export async function registerViaApi(user, eventId) {
  const response = await user.context.request.post(`/api/events/${eventId}/registration`);
  if (!response.ok()) throw new Error(`запись ${user.name}: ${response.status()}`);
  return response.json();
}

// Значение для <input type="datetime-local"> в поясе браузера (Asia/Bishkek, UTC+6, без
// перехода на летнее время).
export function bishkekInput(date) {
  const d = new Date(date.getTime() + 6 * 3600_000);
  return d.toISOString().slice(0, 16);
}
