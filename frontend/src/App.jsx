import { useEffect, useState } from "react";
import "./App.css";

const API_URL = "http://localhost:8000/api/events";

const TIER_LABELS = {
  scheduled: "Scheduled",
  busking_spot: "Busking spot",
  open_rehearsal: "Open rehearsal",
};

function formatDate(event) {
  if (!event.date) return "No schedule — drop by";
  const date = new Date(`${event.date}T${event.start_time ?? "00:00:00"}`);
  const dateStr = date.toLocaleDateString(undefined, {
    weekday: "short",
    month: "short",
    day: "numeric",
    year: "numeric",
  });
  if (!event.start_time) return dateStr;
  const timeStr = date.toLocaleTimeString(undefined, {
    hour: "numeric",
    minute: "2-digit",
  });
  return `${dateStr} — ${timeStr}`;
}

function EventCard({ event }) {
  return (
    <div className={`event-card tier-${event.tier}`}>
      <div className="event-card-header">
        <span className={`tier-badge tier-badge-${event.tier}`}>
          {TIER_LABELS[event.tier] ?? event.tier}
        </span>
        <span className={`price-badge price-badge-${event.price_type}`}>
          {event.price_type === "free"
            ? "Free"
            : event.price_type === "paid"
            ? event.price_amount
              ? `Paid — ${event.price_amount}`
              : "Paid"
            : "Price unknown"}
        </span>
      </div>
      <h3 className="event-title">{event.title}</h3>
      <div className="event-meta">{formatDate(event)}</div>
      <div className="event-venue">
        {event.venue_name}
        {event.address ? ` · ${event.address}` : ""}
      </div>
      {event.description && (
        <p className="event-description">{event.description}</p>
      )}
      {event.link && (
        <a
          className="event-link"
          href={event.link}
          target="_blank"
          rel="noopener noreferrer"
        >
          More info →
        </a>
      )}
    </div>
  );
}

function App() {
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [tierFilter, setTierFilter] = useState("all");

  useEffect(() => {
    fetch(API_URL)
      .then((res) => {
        if (!res.ok) throw new Error(`API returned ${res.status}`);
        return res.json();
      })
      .then((data) => {
        setEvents(data.events ?? []);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }, []);

  const filtered =
    tierFilter === "all" ? events : events.filter((e) => e.tier === tierFilter);

  // Scheduled events sorted by date; busking spots (no date) trail at the end.
  const sorted = [...filtered].sort((a, b) => {
    if (!a.date && !b.date) return a.title.localeCompare(b.title);
    if (!a.date) return 1;
    if (!b.date) return -1;
    return `${a.date}${a.start_time ?? ""}`.localeCompare(
      `${b.date}${b.start_time ?? ""}`
    );
  });

  return (
    <div className="app">
      <header className="app-header">
        <h1>Montreal Classical Concert Finder</h1>
        <p className="subtitle">
          Scheduled concerts, free recitals, and known busking spots — all in
          one place.
        </p>
      </header>

      <div className="filters">
        {["all", "scheduled", "busking_spot", "open_rehearsal"].map((tier) => (
          <button
            key={tier}
            className={tierFilter === tier ? "filter-btn active" : "filter-btn"}
            onClick={() => setTierFilter(tier)}
          >
            {tier === "all" ? "All" : TIER_LABELS[tier]}
          </button>
        ))}
      </div>

      {loading && <p className="status">Loading events…</p>}
      {error && (
        <p className="status error">
          Couldn't reach the API — is the backend running? ({error})
        </p>
      )}
      {!loading && !error && sorted.length === 0 && (
        <p className="status">No events found for this filter.</p>
      )}

      <div className="event-list">
        {sorted.map((event) => (
          <EventCard key={event.id} event={event} />
        ))}
      </div>
    </div>
  );
}

export default App;