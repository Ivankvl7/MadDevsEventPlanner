import { useEffect, useState } from "react";
import { Link } from "react-router";
import { api } from "../api.js";
import { formatDateTime } from "../format.js";

// Статус своей записи: билет с кодом, позиция в очереди или отказ.
export function RegistrationStatus({ registration }) {
  if (registration.status === "confirmed") {
    return (
      <div className="ticket">
        <div>Место подтверждено. Код билета:</div>
        <div className="code" data-testid="ticket-code">
          {registration.ticket_code}
        </div>
      </div>
    );
  }
  if (registration.status === "waitlisted") {
    return (
      <p>
        Вы в листе ожидания, позиция <strong>{registration.waitlist_position}</strong>. Когда место
        освободится, придёт письмо с билетом.
      </p>
    );
  }
  return <p className="muted">Вы отказались от участия.</p>;
}

export default function MyTicketsPage() {
  const [items, setItems] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    api("GET", "/api/me/registrations")
      .then(setItems)
      .catch((e) => setError(e.message));
  }, []);

  return (
    <section>
      <h1>Мои билеты</h1>
      {error && <p className="error">{error}</p>}
      {items === null && !error && <p className="muted">Загрузка…</p>}
      {items?.length === 0 && (
        <p className="muted">
          Вы ещё никуда не записаны. <Link to="/">К событиям</Link>
        </p>
      )}
      <ul className="cards">
        {items?.map((r) => (
          <li key={r.id} className={r.status === "cancelled" ? "card past" : "card"}>
            <Link to={`/events/${r.event.id}`} className="card-title">
              {r.event.title}
            </Link>
            <div className="muted">{formatDateTime(r.event.starts_at)}</div>
            <RegistrationStatus registration={r} />
          </li>
        ))}
      </ul>
    </section>
  );
}
