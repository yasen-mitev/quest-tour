import { useEffect, useState } from "react";
import { adminApi, HttpErrorWithBody, type AuthMethods } from "../api";

export function LoginScreen() {
  const [methods, setMethods] = useState<AuthMethods | null>(null);
  const [providerError, setProviderError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    adminApi
      .authProvider()
      .then((res) => {
        if (!cancelled) setMethods(res.methods);
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
      {methods?.password && <PasswordForm />}
      {methods?.entra && (
        // Full-page navigation: the server redirects to Microsoft and back to /admin.
        <a
          className={`qc-btn ${methods.password ? "qc-btn--secondary" : "qc-btn--primary"}`}
          href="/api/admin/auth/login"
        >
          Sign in with Microsoft
        </a>
      )}
      {methods?.dev && <MagicLinkForm />}
      {providerError && (
        <p className="qc-field__error">Could not load the sign-in options. Please reload the page.</p>
      )}
    </div>
  );
}

function PasswordForm() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await adminApi.passwordLogin(email, password);
      window.location.href = "/admin";
    } catch (err) {
      setError(
        err instanceof HttpErrorWithBody && err.status === 429
          ? "Too many attempts. Try again in a few minutes."
          : "Invalid email or password.",
      );
    }
  };

  return (
    <form onSubmit={submit}>
      <label className="qc-field">
        <span className="qc-field__label">Email</span>
        <input
          className="qc-input"
          type="email"
          value={email}
          required
          autoComplete="username"
          onChange={(e) => setEmail(e.target.value)}
        />
      </label>
      <label className="qc-field">
        <span className="qc-field__label">Password</span>
        <input
          className="qc-input"
          type="password"
          value={password}
          required
          autoComplete="current-password"
          onChange={(e) => setPassword(e.target.value)}
        />
      </label>
      <button className="qc-btn qc-btn--primary" type="submit">
        Sign in
      </button>
      {error && <p className="qc-field__error">{error}</p>}
    </form>
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
