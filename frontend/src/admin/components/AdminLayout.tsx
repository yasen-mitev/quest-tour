import { useEffect, useState, type ReactNode } from "react";
import { AppVersion } from "../../components/AppVersion";
import { useConsent } from "../../lib/consent";
import { adminApi } from "../api";

const LINKS = [
  { key: "dashboard", label: "Dashboard" },
  { key: "requests", label: "Requests" },
  { key: "landmarks", label: "Landmarks" },
  { key: "games", label: "Games" },
  { key: "teams", label: "Teams" },
  { key: "photos", label: "Photos" },
  { key: "albums", label: "Albums" },
  { key: "feedback", label: "Feedback" },
  { key: "administrators", label: "Administrators" },
];

/** Dispatched on `window` when a game request is decided, so the pending badge recounts. */
export const REQUESTS_CHANGED = "questtour:admin-requests-changed";

type AdminLayoutProps = { active: string; children: ReactNode };

/** The number of pending game requests (D6: the length of the pending list); null until known. */
function usePendingRequests(): number | null {
  const [count, setCount] = useState<number | null>(null);
  useEffect(() => {
    let cancelled = false;
    const load = () => {
      adminApi
        .gameRequests("pending")
        .then((rows) => {
          if (!cancelled) setCount(rows.length);
        })
        .catch(() => {
          // The badge is optional: without a count the link shows plain.
        });
    };
    load();
    window.addEventListener(REQUESTS_CHANGED, load);
    return () => {
      cancelled = true;
      window.removeEventListener(REQUESTS_CHANGED, load);
    };
  }, []);
  return count;
}

export function AdminLayout({ active, children }: AdminLayoutProps) {
  const { reopen } = useConsent();
  const pending = usePendingRequests();
  const handleLogout = async () => {
    try {
      await adminApi.logout();
    } finally {
      window.location.href = "/admin/login";
    }
  };

  return (
    <div className="admin-shell">
      <nav className="admin-nav" aria-label="Admin navigation">
        {LINKS.map((link) => (
          <a
            key={link.key}
            href={`/admin/${link.key}`}
            className={link.key === active ? "active" : ""}
            aria-label={
              link.key === "requests" && pending ? `${link.label} (${pending} pending)` : undefined
            }
          >
            {link.label}
            {link.key === "requests" && pending ? (
              <span className="admin-nav__badge" aria-hidden="true">
                {pending}
              </span>
            ) : null}
          </a>
        ))}
        <button
          type="button"
          className="admin-nav__logout"
          onClick={handleLogout}
        >
          Logout
        </button>
        <div className="admin-nav__legal">
          <a href="/privacy?from=admin">Privacy</a>
          <a href="/terms?from=admin">Terms</a>
          <a href="/contact?from=admin">Contact</a>
          <button type="button" className="admin-nav__cookies" onClick={reopen}>Cookies</button>
        </div>
        <AppVersion inverse />
      </nav>
      <main className="admin-main">{children}</main>
    </div>
  );
}
