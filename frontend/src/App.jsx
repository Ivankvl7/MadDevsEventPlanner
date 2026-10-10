import { Link, NavLink, Route, Routes, useNavigate } from "react-router";
import { RequireAuth, useAuth } from "./auth.jsx";
import AuthPage from "./pages/AuthPage.jsx";
import CheckinPage from "./pages/CheckinPage.jsx";
import EventFormPage from "./pages/EventFormPage.jsx";
import EventPage from "./pages/EventPage.jsx";
import EventsPage from "./pages/EventsPage.jsx";
import MailPage from "./pages/MailPage.jsx";
import MyTicketsPage from "./pages/MyTicketsPage.jsx";
import OrganizerPage from "./pages/OrganizerPage.jsx";

function Header() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  async function onLogout() {
    await logout();
    navigate("/");
  }

  return (
    <header className="header">
      <Link to="/" className="brand">
        EventPlanner
      </Link>
      <nav>
        <NavLink to="/" end>
          События
        </NavLink>
        <NavLink to="/my">Мои билеты</NavLink>
        <NavLink to="/mail">Почта (заглушка)</NavLink>
      </nav>
      <div className="user">
        {user ? (
          <>
            <span title={user.email}>{user.name}</span>
            <button type="button" className="link" onClick={onLogout}>
              Выйти
            </button>
          </>
        ) : user === null ? (
          <NavLink to="/login">Войти</NavLink>
        ) : null}
      </div>
    </header>
  );
}

const auth = (page) => <RequireAuth>{page}</RequireAuth>;

export default function App() {
  return (
    <>
      <Header />
      <main className="main">
        <Routes>
          <Route path="/" element={<EventsPage />} />
          <Route path="/login" element={<AuthPage mode="login" />} />
          <Route path="/register" element={<AuthPage mode="register" />} />
          <Route path="/events/new" element={auth(<EventFormPage />)} />
          <Route path="/events/:id" element={<EventPage />} />
          <Route path="/events/:id/edit" element={auth(<EventFormPage />)} />
          <Route path="/events/:id/organizer" element={auth(<OrganizerPage />)} />
          <Route path="/events/:id/checkin" element={auth(<CheckinPage />)} />
          <Route path="/my" element={auth(<MyTicketsPage />)} />
          <Route path="/mail" element={auth(<MailPage />)} />
          <Route path="*" element={<p>Страница не найдена. <Link to="/">К событиям</Link></p>} />
        </Routes>
      </main>
    </>
  );
}
