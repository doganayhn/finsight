import { useState } from "react";
import type { FormEvent } from "react";
import { Link, Navigate, useLocation } from "react-router-dom";
import { errorMessage } from "../api/client";
import { useAuth } from "../hooks/auth";

export function Login() { return <AuthForm mode="login" />; }
export function Register() { return <AuthForm mode="register" />; }

function AuthForm({ mode }: { mode: "login" | "register" }) {
  const auth = useAuth();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (auth.status === "authenticated") {
    const target = (location.state as { from?: string } | null)?.from ?? "/overview";
    return <Navigate to={target} replace />;
  }
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (mode === "register" && password !== confirmation) {
      setError("Şifreler eşleşmiyor.");
      return;
    }
    setPending(true);
    setError(null);
    try { await auth[mode](email, password); }
    catch (caught) { setError(errorMessage(caught)); }
    finally { setPending(false); }
  }
  return (
    <main className="auth-page">
      <section className="auth-card">
        <Link className="brand auth-brand" to="/overview"><b className="brand-mark">F</b>FinSight<span className="brand-period">.</span></Link>
        <p className="eyebrow">HARCAMALARINIZI ANLAYIN</p>
        <h1>{mode === "login" ? "Tekrar hoş geldiniz" : "FinSight’a başlayın"}</h1>
        <p>{mode === "login" ? "Finansal görünümünüze güvenle devam edin." : "Yalnızca email ve güçlü bir parola yeterli."}</p>
        {error && <div className="notice error" role="alert">{error}</div>}
        <form onSubmit={submit} aria-busy={pending}>
          <label>Email<input type="email" required autoComplete="email" maxLength={320} value={email} onChange={(e) => setEmail(e.target.value)} /></label>
          <label>Şifre<input type="password" required minLength={12} maxLength={128} autoComplete={mode === "login" ? "current-password" : "new-password"} value={password} onChange={(e) => setPassword(e.target.value)} /></label>
          {mode === "register" && <>
            <small>En az 12 karakter; uzun bir parola cümlesi kullanabilirsiniz.</small>
            <label>Şifreyi doğrula<input type="password" required minLength={12} maxLength={128} autoComplete="new-password" value={confirmation} onChange={(e) => setConfirmation(e.target.value)} /></label>
          </>}
          <button className="primary" disabled={pending}>{pending ? "Lütfen bekleyin…" : mode === "login" ? "Giriş yap" : "Hesap oluştur"}</button>
          <span className="sr-only" role="status" aria-live="polite">
            {pending ? "İstek işleniyor" : ""}
          </span>
        </form>
        <p className="auth-switch">
          {mode === "login" ? "Hesabınız yok mu? " : "Zaten hesabınız var mı? "}
          <Link to={mode === "login" ? "/register" : "/login"}>{mode === "login" ? "Kayıt olun" : "Giriş yapın"}</Link>
        </p>
      </section>
    </main>
  );
}
