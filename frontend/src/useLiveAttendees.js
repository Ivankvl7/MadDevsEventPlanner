import { useEffect, useState } from "react";
import { api } from "./api.js";

const RETRY_MS = 3000;

// Экран организатора: снимок по HTTP, затем live-поток SSE (B8, R-14).
// EventSource сам переподключается только после обрыва; если сервер ответил ошибкой
// (например, nginx отдал 502, пока backend перезапускается), поток закрывается навсегда.
// Поэтому переподключаемся сами: заново проверяем доступ и открываем новый поток.
export function useLiveAttendees(eventId) {
  const [state, setState] = useState({ data: null, connection: "connecting", error: null });

  useEffect(() => {
    let source = null;
    let timer = null;
    let stopped = false;

    const retry = () => {
      source?.close();
      source = null;
      if (stopped) return;
      setState((s) => ({ ...s, connection: "reconnecting" }));
      timer = setTimeout(connect, RETRY_MS);
    };

    async function connect() {
      try {
        const data = await api("GET", `/api/events/${eventId}/attendees`);
        if (stopped) return;
        setState((s) => ({ ...s, data, error: null }));
      } catch (e) {
        if (stopped) return;
        // Нет доступа или события — переподключение не поможет.
        if (e.status === 401 || e.status === 403 || e.status === 404) {
          setState({ data: null, connection: "closed", error: e.message });
          return;
        }
        retry();
        return;
      }
      source = new EventSource(`/api/events/${eventId}/attendees/live`);
      source.onopen = () => setState((s) => ({ ...s, connection: "live" }));
      source.addEventListener("attendees", (e) => {
        setState((s) => ({ ...s, data: JSON.parse(e.data), connection: "live" }));
      });
      source.onerror = () => {
        if (source.readyState === EventSource.CLOSED) retry();
        else setState((s) => ({ ...s, connection: "reconnecting" }));
      };
    }

    connect();
    return () => {
      stopped = true;
      clearTimeout(timer);
      source?.close();
    };
  }, [eventId]);

  return state;
}
