import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";
import { formatTime } from "../format.js";

// F6: ввод кода вместо сканера. Результат — участник или понятная причина отказа.
export default function CheckinPage() {
  const { id } = useParams();
  const { user } = useAuth();
  const [event, setEvent] = useState(null);
  const [loadError, setLoadError] = useState(null);
  const [code, setCode] = useState("");
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const input = useRef(null);

  useEffect(() => {
    api("GET", `/api/events/${id}`)
      .then(setEvent)
      .catch((e) => setLoadError(e.message));
  }, [id]);

  async function onSubmit(e) {
    e.preventDefault();
    setBusy(true);
    try {
      const ok = await api("POST", `/api/events/${id}/checkin`, { code });
      setResult({ ok: true, ...ok });
      setCode("");
    } catch (err) {
      setResult({ ok: false, message: err.message });
    } finally {
      setBusy(false);
      input.current?.focus();
    }
  }

  if (loadError) return <p className="error">{loadError}</p>;
  if (!event) return <p className="muted">Загрузка…</p>;
  if (event.organizer.id !== user.id) {
    return <p className="error">Чекин доступен только организатору события.</p>;
  }

  return (
    <section className="narrow">
      <h1>Чекин: {event.title}</h1>
      <form onSubmit={onSubmit} className="form">
        <label>
          Код билета
          <input
            ref={input}
            value={code}
            onChange={(e) => setCode(e.target.value)}
            required
            autoFocus
            autoComplete="off"
            className="code-input"
          />
        </label>
        <button type="submit" disabled={busy}>
          Отметить
        </button>
      </form>
      {result?.ok && (
        <div className="result ok" data-testid="checkin-result">
          <strong>Проходите: {result.name}</strong>
          <div>{result.email}</div>
          <div className="muted">
            {result.event_title} · отмечен в {formatTime(result.checked_in_at)}
          </div>
        </div>
      )}
      {result && !result.ok && (
        <div className="result fail" data-testid="checkin-result">
          <strong>Не пропускать:</strong> {result.message}
        </div>
      )}
      <p>
        <Link to={`/events/${id}/organizer`}>Экран организатора</Link>
      </p>
    </section>
  );
}
