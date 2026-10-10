import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";
import { useAuth } from "../auth.jsx";

export default function AuthPage({ mode }) {
  const isLogin = mode === "login";
  const { login, register } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const next = params.get("next") || "/";
  const [form, setForm] = useState({ email: "", password: "", name: "" });
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const set = (field) => (e) => setForm({ ...form, [field]: e.target.value });

  async function onSubmit(e) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (isLogin) await login(form.email, form.password);
      else await register(form.email, form.password, form.name);
      navigate(next, { replace: true });
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  }

  const other = isLogin ? "/register" : "/login";
  return (
    <section className="narrow">
      <h1>{isLogin ? "Вход" : "Регистрация"}</h1>
      <form onSubmit={onSubmit} className="form">
        {!isLogin && (
          <label>
            Имя
            <input value={form.name} onChange={set("name")} required maxLength={100} />
          </label>
        )}
        <label>
          Email
          <input type="email" value={form.email} onChange={set("email")} required />
        </label>
        <label>
          Пароль
          <input
            type="password"
            value={form.password}
            onChange={set("password")}
            required
            minLength={isLogin ? undefined : 8}
            autoComplete={isLogin ? "current-password" : "new-password"}
          />
          {!isLogin && <small className="muted">Не короче 8 символов</small>}
        </label>
        {error && <p className="error">{error}</p>}
        <button type="submit" disabled={busy}>
          {isLogin ? "Войти" : "Создать аккаунт"}
        </button>
      </form>
      <p>
        {isLogin ? "Нет аккаунта? " : "Уже есть аккаунт? "}
        <Link to={`${other}?next=${encodeURIComponent(next)}`}>
          {isLogin ? "Зарегистрироваться" : "Войти"}
        </Link>
      </p>
    </section>
  );
}
