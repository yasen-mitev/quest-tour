import type { ReactNode } from "react";
import { AppVersion } from "../../components/AppVersion";
import { adminApi } from "../api";

const LINKS = [
  { key: "dashboard", label: "Dashboard" },
  { key: "landmarks", label: "Landmarks" },
  { key: "games", label: "Games" },
  { key: "teams", label: "Teams" },
  { key: "photos", label: "Photos" },
  { key: "albums", label: "Albums" },
  { key: "feedback", label: "Feedback" },
];

type AdminLayoutProps = { active: string; children: ReactNode };

export function AdminLayout({ active, children }: AdminLayoutProps) {
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
          >
            {link.label}
          </a>
        ))}
        <button
          type="button"
          className="admin-nav__logout"
          onClick={handleLogout}
        >
          Logout
        </button>
        <AppVersion inverse />
      </nav>
      <main className="admin-main">{children}</main>
    </div>
  );
}
