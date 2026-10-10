import { useEffect, useState } from "react";
import { Link, useParams } from "react-router";
import { api } from "../api.js";
import { formatDateTime, formatTime } from "../format.js";
import { useLiveAttendees } from "../useLiveAttendees.js";

const CONNECTION = {
  connecting: "подключение…",
  live: "обновляется автоматически",
  reconnecting: "связь потеряна, переподключение…",
  closed: "не подключено",
};

// F7, B8: счётчики и списки обновляются без перезагрузки страницы.
export default function OrganizerPage() {
  const { id } = useParams();
  const [event, setEvent] = useState(null);
  const { data, connection, error } = useLiveAttendees(id);

  // Лимит мест мог измениться — снимок приходит и на это, перечитываем событие.
  useEffect(() => {
    api("GET", `/api/events/${id}`)
      .then(setEvent)
      .catch(() => {});
  }, [id, data]);

  return (
    <section>
      <h1>Экран организатора{event && `: ${event.title}`}</h1>
      {event && <p className="muted">{formatDateTime(event.starts_at)}</p>}
      <p className={`connection ${connection}`} data-testid="connection">
        ● {CONNECTION[connection]}
      </p>
      {error && <p className="error">{error}</p>}
      {data && (
        <>
          <div className="counters">
            <Counter label="Зарегистрировано" value={data.counts.confirmed} of={event?.capacity}
              testid="count-confirmed" />
            <Counter label="В листе ожидания" value={data.counts.waitlisted}
              testid="count-waitlisted" />
            <Counter label="Пришло" value={data.counts.checked_in} of={data.counts.confirmed}
              testid="count-checked-in" />
          </div>
          <div className="actions">
            <Link to={`/events/${id}/checkin`} className="button">
              Открыть чекин
            </Link>
            <Link to={`/events/${id}`}>К событию</Link>
          </div>

          <h2>Участники</h2>
          {data.confirmed.length === 0 ? (
            <p className="muted">Пока никто не записался.</p>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Имя</th>
                  <th>Email</th>
                  <th>Записан</th>
                  <th>Пришёл</th>
                </tr>
              </thead>
              <tbody>
                {data.confirmed.map((a) => (
                  <tr key={a.registration_id}>
                    <td>{a.name}</td>
                    <td>{a.email}</td>
                    <td>{formatDateTime(a.since)}</td>
                    <td>{a.checked_in_at ? `✓ ${formatTime(a.checked_in_at)}` : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          <h2>Лист ожидания</h2>
          {data.waitlist.length === 0 ? (
            <p className="muted">Очереди нет.</p>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>№</th>
                  <th>Имя</th>
                  <th>Email</th>
                  <th>В очереди с</th>
                </tr>
              </thead>
              <tbody>
                {data.waitlist.map((a) => (
                  <tr key={a.registration_id}>
                    <td>{a.position}</td>
                    <td>{a.name}</td>
                    <td>{a.email}</td>
                    <td>{formatDateTime(a.since)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </section>
  );
}

function Counter({ label, value, of, testid }) {
  return (
    <div className="counter">
      <div className="counter-value">
        <span data-testid={testid}>{value}</span>
        {of !== undefined && <span className="muted"> / {of}</span>}
      </div>
      <div className="muted">{label}</div>
    </div>
  );
}
