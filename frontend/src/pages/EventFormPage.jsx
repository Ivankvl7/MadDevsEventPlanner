import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";
import { browserTimezone, fromLocalInput, toLocalInput } from "../format.js";

const EMPTY = { title: "", description: "", starts_at: "", capacity: 10 };

// Создание (/events/new) и редактирование (/events/:id/edit) события.
export default function EventFormPage() {
  const { id } = useParams();
  const isEdit = id !== undefined;
  const { user } = useAuth();
  const navigate = useNavigate();
  const [event, setEvent] = useState(null);
  const [form, setForm] = useState(EMPTY);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!isEdit) return;
    api("GET", `/api/events/${id}`)
      .then((ev) => {
        setEvent(ev);
        setForm({
          title: ev.title,
          description: ev.description,
          starts_at: toLocalInput(ev.starts_at),
          capacity: ev.capacity,
        });
      })
      .catch((e) => setError(e.message));
  }, [id, isEdit]);

  const set = (field) => (e) => setForm({ ...form, [field]: e.target.value });

  async function onSubmit(e) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const data = {
      title: form.title,
      description: form.description,
      capacity: Number(form.capacity),
    };
    // Поле времени без секунд: если его не трогали, дату не отправляем, иначе потерянные
    // секунды выглядели бы как перенос и участникам ушли бы письма.
    if (!isEdit || form.starts_at !== toLocalInput(event.starts_at)) {
      data.starts_at = fromLocalInput(form.starts_at);
    }
    try {
      const saved = isEdit
        ? await api("PATCH", `/api/events/${id}`, data)
        : await api("POST", "/api/events", { ...data, timezone: browserTimezone() });
      navigate(`/events/${saved.id}`);
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  }

  if (isEdit && !event) {
    return error ? <p className="error">{error}</p> : <p className="muted">Загрузка…</p>;
  }
  if (isEdit && event.organizer.id !== user.id) {
    return <p className="error">Изменять событие может только организатор.</p>;
  }

  return (
    <section className="narrow">
      <h1>{isEdit ? "Редактирование события" : "Новое событие"}</h1>
      <form onSubmit={onSubmit} className="form">
        <label>
          Название
          <input value={form.title} onChange={set("title")} required maxLength={200} />
        </label>
        <label>
          Описание
          <textarea value={form.description} onChange={set("description")} rows={5} />
        </label>
        <label>
          Дата и время начала
          <input
            type="datetime-local"
            value={form.starts_at}
            onChange={set("starts_at")}
            required
          />
          <small className="muted">
            По времени вашего браузера ({browserTimezone()}).
            {isEdit && " При переносе все участники получат письмо."}
          </small>
        </label>
        <label>
          Лимит мест
          <input
            type="number"
            min={1}
            value={form.capacity}
            onChange={set("capacity")}
            required
          />
          {isEdit && (
            <small className="muted">
              Если увеличить лимит, места получат первые из листа ожидания.
            </small>
          )}
        </label>
        {error && <p className="error">{error}</p>}
        <div className="actions">
          <button type="submit" disabled={busy}>
            {isEdit ? "Сохранить" : "Создать"}
          </button>
          <Link to={isEdit ? `/events/${id}` : "/"}>Отмена</Link>
        </div>
      </form>
    </section>
  );
}
