import { useEffect, useState } from "react";
import { adminApi } from "../api";

type Provider = "entra" | "dev";

export function LoginScreen() {
  const [provider, setProvider] = useState<Provider | null>(null);
  const [providerError, setProviderError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    adminApi
      .authProvider()
      .then((res) => {
        if (!cancelled) setProvider(res.provider);
      })
      .catch(() => {
        if (!cancelled) setProviderError(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="admin-login">
      <h1 className="t-title">Admin sign-in</h1>
      {provider === "entra" && (
        // Full-page navigation: the server redirects to Microsoft and back to /admin.
        <a className="qc-btn qc-btn--primary" href="/api/admin/auth/login">
          Sign in with Microsoft
        </a>
      )}
      {provider === "dev" && <MagicLinkForm />}
      {providerError && (
        <p className="qc-field__error">Could not load the sign-in options. Please reload the page.</p>
      )}
    </div>
  );
}

function MagicLinkForm() {
  const [email, setEmail] = useState("");
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setUrl(null);
    try {
      const res = await adminApi.requestMagicLink(email);
      setUrl(res.url);
    } catch {
      setError("Could not request magic link. Is this email on the allowlist?");
    }
  };

  return (
    <>
      <form onSubmit={submit}>
        <label className="qc-field">
          <span className="qc-field__label">Email</span>
          <input
            className="qc-input"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </label>
        <button className="qc-btn qc-btn--primary" type="submit">
          Request magic link
        </button>
      </form>
      {url && (
        <div className="admin-magic-link">
          <p className="t-caption">Development-only link:</p>
          <a className="t-body" href={url}>
            {url}
          </a>
        </div>
      )}
      {error && <p className="qc-field__error">{error}</p>}
    </>
  );
}
