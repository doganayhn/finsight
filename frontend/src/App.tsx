import { lazy, Suspense, useState } from "react";
import { BrowserRouter, NavLink, Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useBackendStatus } from "./hooks/useBackendStatus";
import { AuthProvider, useAuth } from "./hooks/auth";
import { AccountProvider } from "./hooks/context";
import { Loading } from "./components/ui";
import { Transactions } from "./pages/Transactions";
import { Imports, ImportDetail } from "./pages/Imports";
import { Login, Register } from "./pages/Auth";

const Overview = lazy(() => import("./pages/Overview").then((module) => ({ default: module.Overview })));
const Assistant = lazy(() => import("./pages/Assistant").then((module) => ({ default: module.Assistant })));

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: (failures, error) => failures < 1 && error instanceof TypeError,
      staleTime: 30000,
      refetchOnWindowFocus: false,
    },
    mutations: { retry: false },
  },
});

export function ProductShell() {
  const [menu, setMenu] = useState(false);
  const [logoutPending, setLogoutPending] = useState(false);
  const { status, retry } = useBackendStatus();
  const auth = useAuth();
  const navigate = useNavigate();
  const links = [
    { to: "/overview", label: "Genel bakış", icon: "◫" },
    { to: "/transactions", label: "İşlemler", icon: "⇄" },
    { to: "/imports", label: "Hesap özetleri", icon: "↥" },
    { to: "/assistant", label: "Asistan", icon: "✦" },
  ];
  async function logout() {
    if (logoutPending) return;
    setLogoutPending(true);
    try {
      await auth.logout();
    } catch {
      // AuthProvider always clears in-memory identity and query data locally.
    } finally {
      navigate("/login", { replace: true });
    }
  }
  return (
    <div className="app-shell">
      <a href="#main" className="skip-link">İçeriğe geç</a>
      <header className="mobile-header">
        <span className="brand"><b className="brand-mark">F</b>FinSight</span>
        <button aria-expanded={menu} aria-controls="primary-nav" onClick={() => setMenu(!menu)}>
          {menu ? "Menüyü kapat" : "Menü"}
        </button>
      </header>
      <aside className={`sidebar ${menu ? "is-open" : ""}`}>
        <NavLink className="brand desktop-brand" to="/overview">
          <b className="brand-mark">F</b>FinSight<span className="brand-period">.</span>
        </NavLink>
        <p className="nav-caption">ÇALIŞMA ALANI</p>
        <nav id="primary-nav" aria-label="Ana menü">
          {links.map((link) => (
            <NavLink key={link.to} to={link.to} onClick={() => setMenu(false)}>
              <span aria-hidden="true">{link.icon}</span>{link.label}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-note">
          <span aria-hidden="true">◎</span>
          <p>Verilerinize dayalı.<br />Daha net bir bakış.</p>
          <small>Yalnızca içe aktarılan işlemler.</small>
        </div>
        <div className="identity-card">
          <small>OTURUM</small>
          <span title={auth.user?.email}>{auth.user?.email}</span>
          <button className="text-button" onClick={() => void logout()} disabled={logoutPending}>
            {logoutPending ? "Çıkış yapılıyor…" : "Çıkış yap"}
          </button>
        </div>
        <footer className="health">
          <span className={`dot ${status === "Online" ? "" : "amber"}`} />
          <span role="status">
            {status === "Online" ? "Sunucu bağlı" : status === "Offline" ? "Sunucu çevrimdışı" : "Bağlantı kontrol ediliyor"}
          </span>
          <button className="text-button" onClick={retry} disabled={status === "Checking..."} aria-label="Bağlantıyı yeniden kontrol et">↻</button>
        </footer>
      </aside>
      <main id="main" className="workspace">
        <AccountProvider>
          <Suspense fallback={<Loading />}>
            <Routes>
              <Route path="/" element={<Navigate to="/overview" replace />} />
              <Route path="/overview" element={<Overview />} />
              <Route path="/transactions" element={<Transactions />} />
              <Route path="/imports" element={<Imports />} />
              <Route path="/imports/:id" element={<ImportDetail />} />
              <Route path="/assistant" element={<Assistant />} />
              <Route path="*" element={<section className="panel empty"><h1>Sayfa bulunamadı</h1><NavLink to="/overview">Genel bakışa dön</NavLink></section>} />
            </Routes>
          </Suspense>
        </AccountProvider>
        <footer className="workspace-footer">FinSight · Harcamalarınıza dair daha net bir resim.<span>Güvenli yerel oturum</span></footer>
      </main>
    </div>
  );
}

function ApplicationRoutes() {
  const auth = useAuth();
  const location = useLocation();
  if (auth.status === "checking") return <main className="auth-page"><Loading /></main>;
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route
        path="/*"
        element={
          auth.status === "authenticated" ? (
            <ProductShell />
          ) : (
            <Navigate to="/login" replace state={{ from: location.pathname }} />
          )
        }
      />
    </Routes>
  );
}

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider><ApplicationRoutes /></AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
