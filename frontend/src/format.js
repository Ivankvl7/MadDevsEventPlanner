// R-13: время хранится в UTC, вводится и показывается в часовом поясе браузера.

const dateTime = new Intl.DateTimeFormat("ru-RU", { dateStyle: "long", timeStyle: "short" });
const time = new Intl.DateTimeFormat("ru-RU", { timeStyle: "short" });

export function formatDateTime(iso) {
  return dateTime.format(new Date(iso));
}

export function formatTime(iso) {
  return time.format(new Date(iso));
}

export function browserTimezone() {
  return Intl.DateTimeFormat().resolvedOptions().timeZone;
}

// Значение для <input type="datetime-local">: местное время браузера без секунд.
export function toLocalInput(iso) {
  const d = new Date(iso);
  const pad = (n) => String(n).padStart(2, "0");
  return (
    `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}` +
    `T${pad(d.getHours())}:${pad(d.getMinutes())}`
  );
}

// Обратно: браузер читает значение как местное время, на сервер уходит момент в UTC.
export function fromLocalInput(value) {
  return new Date(value).toISOString();
}

export function isPast(iso) {
  return new Date(iso) <= new Date();
}
