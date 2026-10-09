import { Icon } from "../components/Icon";
import { LegalLinks } from "./LegalScreens";

const DEFAULT_TITLE = "Page not found";

export function NotFoundScreen({ title = DEFAULT_TITLE }: { title?: string }) {
  return (
    <div className="qs">
      <main className="qs-main qs-main--center">
        <div className="qs-sign qs-sign--grey"><Icon name="compass" /></div>
        <div className="qs-center-copy">
          <h1 className="t-title">{title}</h1>
          <p className="t-body">Please open the exact link you received from your host.</p>
        </div>
        {title === DEFAULT_TITLE && <p className="t-caption">Error 404</p>}
        <LegalLinks />
      </main>
    </div>
  );
}
