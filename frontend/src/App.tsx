import { lazy, Suspense, useEffect, type ReactNode } from "react";
import { AlbumPage } from "./album/AlbumPage";
import { ConsentBanner } from "./components/ConsentBanner";
import { GameApp } from "./game/GameApp";
import { lastToken } from "./lib/storage";
import { LoadingScreen } from "./screens/LoadingScreen";
import { NotFoundScreen } from "./screens/NotFoundScreen";

const AdminApp = lazy(async () => {
  const { AdminApp } = await import("./admin/AdminApp");
  return { default: AdminApp };
});

export function App({ path = window.location.pathname }: { path?: string }) {
  useEffect(() => {                          // belt-and-braces for copy paths CSS can't reach (Ctrl+A, long-press menus)
    if (path.startsWith("/admin") || path.startsWith("/album")) return;   // the album is a keepsake: copying is fine
    const block = (e: Event) => {
      const target = e.target as HTMLElement | null;
      if (!target?.closest("input, textarea")) e.preventDefault();
    };
    for (const type of ["copy", "cut", "contextmenu", "selectstart"]) document.addEventListener(type, block);
    return () => { for (const type of ["copy", "cut", "contextmenu", "selectstart"]) document.removeEventListener(type, block); };
  }, [path]);

  if (path.startsWith("/admin")) {
    return (
      <>
        <ConsentBanner app="admin" />
        <Suspense fallback={<LoadingScreen offline={false} />}>
          <AdminApp path={path} />
        </Suspense>
      </>
    );
  }

  const match = /^\/play\/([^/]+)$/.exec(path);
  if (match) {
    const token = safeDecode(match[1]);
    return withConsent(token === null ? <NotFoundScreen /> : <GameApp token={token} />);
  }
  const album = /^\/album\/([^/]+)$/.exec(path);
  if (album) {
    const token = safeDecode(album[1]);
    return withConsent(token === null ? <NotFoundScreen /> : <AlbumPage token={token} />);
  }
  if (path === "/") return withConsent(<Home />);
  return withConsent(<NotFoundScreen />);
}

/** The consent banner (cookie notice) is the first element of every player, album and admin page,
 *  until the visitor answers it — see src/lib/consent.ts. */
function withConsent(screen: ReactNode): ReactNode {
  return (
    <>
      <ConsentBanner app="player" />
      {screen}
    </>
  );
}

function safeDecode(segment: string): string | null {
  try { return decodeURIComponent(segment); } catch { return null; }   // bad %-escape in a truncated link
}

function Home() {
  const token = lastToken();
  useEffect(() => { if (token) window.location.replace(`/play/${encodeURIComponent(token)}`); }, [token]);
  return token ? null : <NotFoundScreen title="Open your game link" />;
}
