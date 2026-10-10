// Обращения к backend. Сессия — HttpOnly-cookie, браузер передаёт её сам (тот же origin).

export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

// FastAPI отдаёт detail строкой (наши ошибки) или списком (ошибки валидации Pydantic).
function errorMessage(detail, status) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail.length) {
    return detail.map((e) => String(e.msg).replace(/^Value error, /, "")).join("; ");
  }
  return `Ошибка сервера (${status})`;
}

export async function api(method, url, body) {
  let response;
  try {
    response = await fetch(url, {
      method,
      headers: body === undefined ? {} : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, "Сервер недоступен, попробуйте ещё раз");
  }
  if (response.status === 204) return null;
  const data = await response.json().catch(() => null);
  if (!response.ok) throw new ApiError(response.status, errorMessage(data?.detail, response.status));
  return data;
}
