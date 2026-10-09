import type { ReactNode } from "react";
import { AdminLayout } from "./components/AdminLayout";
import { AlbumsScreen } from "./screens/AlbumsScreen";
import { Dashboard } from "./screens/Dashboard";
import { FeedbackScreen } from "./screens/FeedbackScreen";
import { GamesScreen } from "./screens/GamesScreen";
import { LandmarksScreen } from "./screens/LandmarksScreen";
import { LoginScreen } from "./screens/LoginScreen";
import { PhotosScreen } from "./screens/PhotosScreen";
import { TeamsScreen } from "./screens/TeamsScreen";

function AdminNotFound() {
  return (
    <div className="admin-section">
      <h1 className="t-title">Admin page not found</h1>
      <p className="t-body">Please use the navigation menu.</p>
    </div>
  );
}

export function AdminApp({ path }: { path: string }) {
  const rest = path.replace(/^\/admin\/?/, "");
  const [section] = rest.split("/");

  let screen: ReactNode = <Dashboard />;
  switch (section) {
    case "":
    case "dashboard":
      screen = <Dashboard />;
      break;
    case "login":
      return <LoginScreen />;
    case "landmarks":
      screen = <LandmarksScreen subPath={rest} />;
      break;
    case "games":
      screen = <GamesScreen subPath={rest} />;
      break;
    case "teams":
      screen = <TeamsScreen subPath={rest} />;
      break;
    case "photos":
      screen = <PhotosScreen />;
      break;
    case "albums":
      screen = <AlbumsScreen />;
      break;
    case "feedback":
      screen = <FeedbackScreen />;
      break;
    default:
      screen = <AdminNotFound />;
  }

  return <AdminLayout active={section || "dashboard"}>{screen}</AdminLayout>;
}
