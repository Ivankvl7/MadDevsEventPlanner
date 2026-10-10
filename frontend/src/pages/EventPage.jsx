import { useEffect, useState } from "react";
import { Link, useLocation, useParams } from "react-router";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";
import { formatDateTime, isPast } from "../format.js";
import { RegistrationStatus } from "./MyTicketsPage.jsx";

// Карточка события: описание, своя регистрация, для организатора — ссылки на его экраны.
export default function EventPage() {
  const { id } = useParams();
  const { user } = useAuth();
  const location = useLocation();
  const [event, setEvent] = useState(null);
  const [registration, setRegistration] = useState(undefined);
  const [error, setError] = useState(null);
  const [actionError, setActionError] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api("GET", `/api/events/${id}`)
      .then(setEvent)
      .catch((e) => setError(e.message));
  }, [id]);

  useEffect(() => {
    if (!user) return;
    api("GET", `/api/events/${id}/registration`)
      .then(setRegistration)
      .catch((e) => (e.status === 404 ? setRegistration(null) : setActionError(e.message)));
  }, [id, user]);

  async function act(method, confirmText) {
    if (confirmText && !window.confirm(confirmText)) return;
    setBusy(true);
    setActionError(null);
    try {
      setRegistration(await api(method, `/api/events/${id}/registration`));
    } catch (e) {
      setActionError(e.message);
    } finally {
      setBusy(false);
    }
  }

  if (error) return <p className="error">{error}</p>;
  if (!event) return <p className="muted">Загрузка…</p>;

  const started = isPast(event.starts_at);
  const isOrganizer = user?.id === event.organizer.id;
  const active = registration && registration.status !== "cancelled";

  return (
    <section>
      <h1>{event.title}</h1>
      <p className="muted">
        {formatDateTime(event.starts_at)}
        {started && " · событие началось"} · Мест: {event.capacity} · Организатор:{" "}
        {event.organizer.name}
      </p>
      {event.description && <p className="description">{event.description}</p>}

      {isOrganizer && (
        <div className="panel">
          <strong>Вы организатор.</strong>
          <div className="actions">
            <Link to={`/events/${id}/organizer`} className="button">
              Экран организатора
            </Link>
            <Link to={`/events/${id}/checkin`} className="button">
              Чекин
            </Link>
            <Link to={`/events/${id}/edit`}>Редактировать</Link>
          </div>
        </div>
      )}

      <div className="panel">
        <h2>Участие</h2>
        {user === null && (
          <p>
            <Link to={`/login?next=${encodeURIComponent(location.pathname)}`}>Войдите</Link>,
            чтобы зарегистрироваться.
          </p>
        )}
        {user && registration !== undefined && (
          <>
            {registration && <RegistrationStatus registration={registration} />}
            {!active && !started && (
              <button type="button" disabled={busy} onClick={() => act("POST")}>
                Зарегистрироваться
              </button>
            )}
            {!active && started && <p className="muted">Регистрация закрыта: событие началось.</p>}
            {active && !started && (
              <button
                type="button"
                className="secondary"
                disabled={busy}
                onClick={() => act("DELETE", "Отказаться от участия?")}
              >
                Отказаться
              </button>
            )}
          </>
        )}
        {actionError && <p className="error">{actionError}</p>}
      </div>
    </section>
  );
}
