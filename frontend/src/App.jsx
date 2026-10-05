import { useEffect, useState } from "react";

// Этап 0: каркас. Показывает, что frontend видит backend, а backend — базу данных.
export default function App() {
  const [health, setHealth] = useState({ state: "loading" });

  useEffect(() => {
    fetch("/api/health")
      .then(async (r) => setHealth({ state: r.ok ? "ok" : "error", body: await r.json() }))
      .catch((e) => setHealth({ state: "error", body: { message: String(e) } }));
  }, []);

  return (
    <main style={{ fontFamily: "system-ui, sans-serif", padding: 24 }}>
      <h1>EventPlanner</h1>
      <p>
        Статус backend:{" "}
        <strong data-testid="health-state">
          {health.state === "loading" ? "проверяю…" : health.state === "ok" ? "работает" : "недоступен"}
        </strong>
      </p>
      {health.body && <pre>{JSON.stringify(health.body)}</pre>}
    </main>
  );
}
