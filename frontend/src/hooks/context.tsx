import { createContext, useContext, useState } from "react";
import type { ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { getAccounts } from "../api/accounts";
import { ErrorState, Pagination } from "../components/ui";

interface Context {
  userId: string;
  accountId: string;
  accountName: string | null;
  setAccountId: (id: string) => void;
}
const DevelopmentContext = createContext<Context | null>(null);
export const uuidValid = (value: string) =>
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value);
function initialId() {
  try {
    return (
      sessionStorage.getItem("finsight.devUserId") ??
      import.meta.env.VITE_DEV_USER_ID ??
      ""
    );
  } catch {
    return import.meta.env.VITE_DEV_USER_ID ?? "";
  }
}
export function DevelopmentProvider({ children }: { children: ReactNode }) {
  const [userId, setUserId] = useState(initialId);
  const [draft, setDraft] = useState(userId);
  const [accountId, setAccountId] = useState("");
  const [offset, setOffset] = useState(0);
  const [open, setOpen] = useState(!uuidValid(userId));
  const client = useQueryClient();
  const accounts = useQuery({
    queryKey: ["accounts", userId, offset],
    queryFn: ({ signal }) => getAccounts(userId, offset, signal),
    enabled: uuidValid(userId),
  });
  function changeIdentity() {
    void client.cancelQueries();
    client.clear();
    setUserId(draft.trim());
    setAccountId("");
    setOffset(0);
    setOpen(false);
    try {
      sessionStorage.setItem("finsight.devUserId", draft.trim());
    } catch {
      /* Optional development convenience only. */
    }
  }
  const accountName =
    accounts.data?.accounts.find((account) => account.id === accountId)?.display_name ?? null;
  return (
    <DevelopmentContext.Provider value={{ userId, accountId, accountName, setAccountId }}>
      <section className="context-bar" aria-label="Geliştirme bağlamı">
        <div className="context-label">
          <span className="dot amber" />
          Yerel geliştirme
          <button
            className="text-button"
            onClick={() => setOpen(!open)}
            aria-expanded={open}
          >
            Bağlamı değiştir
          </button>
        </div>
        {uuidValid(userId) && (
          <label className="account-select">
            Hesap
            <select
              value={accountId}
              onChange={(e) => setAccountId(e.target.value)}
            >
              <option value="">Tüm hesaplar</option>
              {accounts.data?.accounts.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.display_name} · {a.currency}
                  {a.is_active ? "" : " · Pasif"}
                </option>
              ))}
            </select>
          </label>
        )}
        {open && (
          <form
            className="context-form"
            onSubmit={(e) => {
              e.preventDefault();
              changeIdentity();
            }}
          >
            <p>
              Bu bağlam kimlik doğrulama değildir. Yalnızca yerel geliştirme
              için mevcut bir kullanıcı UUID’si kullanın.
            </p>
            <label>
              Geliştirme kullanıcı UUID’si
              <input
                autoComplete="off"
                required
                pattern="[0-9a-fA-F-]{36}"
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
              />
            </label>
            <button className="primary" disabled={!uuidValid(draft.trim())}>
              Bağlamı kullan
            </button>
          </form>
        )}
        {accounts.isError && (
          <ErrorState
            error={accounts.error}
            retry={() => void accounts.refetch()}
          />
        )}
        {accounts.isSuccess && accounts.data.accounts.length === 0 && (
          <p className="notice">
            Bu bağlamda hesap yok. README’deki yerel hesap kurulumunu
            tamamlayın.
          </p>
        )}
        {(offset > 0 || accounts.data?.has_more) && accounts.data && (
          <Pagination
            offset={offset}
            limit={50}
            count={accounts.data.accounts.length}
            hasMore={accounts.data.has_more}
            onChange={(value) => {
              setOffset(value);
              setAccountId("");
            }}
          />
        )}
      </section>
      {uuidValid(userId) ? (
        <div key={userId}>{children}</div>
      ) : (
        <div className="panel empty">
          <h2>FinSight’a hoş geldiniz</h2>
          <p>Hesaplarınızı görmek için geliştirme bağlamını yukarıdan seçin.</p>
        </div>
      )}
    </DevelopmentContext.Provider>
  );
}
export function useDevelopment() {
  const context = useContext(DevelopmentContext);
  if (!context) throw new Error("Development context missing");
  return context;
}
