import { useCallback, useEffect, useState } from "react";
import { api } from "../api.js";
import { formatDateTime } from "../format.js";

const KIND = {
  ticket: "Билет",
  promoted: "Место из листа ожидания",
  waitlisted: "Лист ожидания",
  rescheduled: "Перенос",
  reminder: "Напоминание",
};

// G4: письма не уходят наружу — здесь видны письма, «отправленные» на ваш email.
export default function MailPage() {
  const [mail, setMail] = useState(null);
  const [error, setError] = useState(null);

  const load = useCallback(() => {
    api("GET", "/api/mail")
      .then((m) => {
        setMail(m);
        setError(null);
      })
      .catch((e) => setError(e.message));
  }, []);

  useEffect(load, [load]);

  return (
    <section>
      <div className="title-row">
        <h1>Почта (заглушка)</h1>
        <button type="button" className="secondary" onClick={load}>
          Обновить
        </button>
      </div>
      <p className="muted">
        Настоящие письма не отправляются. Здесь — письма на ваш email; «доставкой» занимается
        фоновый цикл backend.
      </p>
      {error && <p className="error">{error}</p>}
      {mail?.length === 0 && <p className="muted">Писем пока нет.</p>}
      <ul className="cards">
        {mail?.map((m) => (
          <li key={m.id} className="card mail">
            <div className="mail-head">
              <span className="badge">{KIND[m.kind] ?? m.kind}</span>
              <strong>{m.subject}</strong>
            </div>
            <div className="muted">
              Кому: {m.to_email} · создано {formatDateTime(m.created_at)} ·{" "}
              {m.sent_at ? `доставлено ${formatDateTime(m.sent_at)}` : "в очереди на отправку"}
            </div>
            <pre className="mail-body">{m.body}</pre>
          </li>
        ))}
      </ul>
    </section>
  );
}
