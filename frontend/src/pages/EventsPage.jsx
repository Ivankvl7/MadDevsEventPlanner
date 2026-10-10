import { useEffect, useState } from "react";
import { Link } from "react-router";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";
import { formatDateTime, isPast } from "../format.js";

export default function EventsPage() {
  const { user } = useAuth();
  const [events, setEvents] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    api("GET", "/api/events")
      .then(setEvents)
      .catch((e) => setError(e.message));
  }, []);

  return (
    <section>
      <div className="title-row">
        <h1>События</h1>
        {user && (
          <Link to="/events/new" className="button">
            Создать событие
          </Link>
        )}
      </div>
      {error && <p className="error">{error}</p>}
      {events === null && !error && <p className="muted">Загрузка…</p>}
      {events?.length === 0 && <p className="muted">Событий пока нет.</p>}
      <ul className="cards">
        {events?.map((ev) => (
          <li key={ev.id} className={isPast(ev.starts_at) ? "card past" : "card"}>
            <Link to={`/events/${ev.id}`} className="card-title">
              {ev.title}
            </Link>
            <div className="muted">
              {formatDateTime(ev.starts_at)}
              {isPast(ev.starts_at) && " · началось"}
            </div>
            <div className="muted">
              Мест: {ev.capacity} · Организатор: {ev.organizer.name}
              {user?.id === ev.organizer.id && <span className="badge">вы организатор</span>}
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
