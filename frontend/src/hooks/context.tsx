import { createContext, useContext, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createAccount, getAccounts } from "../api/accounts";
import { ErrorState, Loading, Pagination } from "../components/ui";
import type { AccountType } from "../types/contracts";

interface AccountContextValue {
  accountId: string;
  accountName: string | null;
  setAccountId: (id: string) => void;
}
const AccountContext = createContext<AccountContextValue | null>(null);

export function AccountProvider({ children }: { children: ReactNode }) {
  const [accountId, setAccountId] = useState("");
  const [offset, setOffset] = useState(0);
  const client = useQueryClient();
  const accounts = useQuery({
    queryKey: ["accounts", offset],
    queryFn: ({ signal }) => getAccounts(offset, signal),
  });
  const accountName =
    accounts.data?.accounts.find((account) => account.id === accountId)?.display_name ?? null;

  if (accounts.isLoading) return <Loading />;
  if (accounts.isError)
    return <ErrorState error={accounts.error} retry={() => void accounts.refetch()} />;
  if (accounts.data?.accounts.length === 0 && offset === 0) {
    return (
      <AccountOnboarding
        onCreated={(id) => {
          setAccountId(id);
          void client.invalidateQueries({ queryKey: ["accounts"] });
        }}
      />
    );
  }
  return (
    <AccountContext.Provider value={{ accountId, accountName, setAccountId }}>
      <section className="context-bar" aria-label="Hesap seçimi">
        <div className="context-label"><span className="dot" /> FinSight hesabınız</div>
        <label className="account-select">
          Hesap
          <select value={accountId} onChange={(event) => setAccountId(event.target.value)}>
            <option value="">Tüm hesaplar</option>
            {accounts.data?.accounts.map((account) => (
              <option key={account.id} value={account.id}>
                {account.display_name} · {account.currency}{account.is_active ? "" : " · Pasif"}
              </option>
            ))}
          </select>
        </label>
        {(offset > 0 || accounts.data?.has_more) && accounts.data && (
          <Pagination
            offset={offset}
            limit={50}
            count={accounts.data.accounts.length}
            hasMore={accounts.data.has_more}
            onChange={(value) => { setOffset(value); setAccountId(""); }}
          />
        )}
      </section>
      {children}
    </AccountContext.Provider>
  );
}

function AccountOnboarding({ onCreated }: { onCreated: (id: string) => void }) {
  const [displayName, setDisplayName] = useState("Yapı Kredi TLcard");
  const [institution, setInstitution] = useState("YAPI_KREDI");
  const [accountType, setAccountType] = useState<AccountType>("DEBIT_CARD");
  const [currency, setCurrency] = useState("TRY");
  const mutation = useMutation({
    mutationFn: () => createAccount({
      display_name: displayName,
      institution_code: institution || null,
      account_type: accountType,
      currency,
    }),
    onSuccess: (account) => onCreated(account.id),
  });
  function submit(event: FormEvent) {
    event.preventDefault();
    mutation.mutate();
  }
  return (
    <section className="onboarding-card panel">
      <p className="eyebrow">BAŞLANGIÇ</p>
      <h1>İlk hesabını ekle</h1>
      <p>
        Hesap özetlerini ilişkilendirmek için yerel bir FinSight hesabı oluşturun. Bu işlem
        FinSight’ı bankanıza bağlamaz; banka kullanıcı adı veya şifresi istemez.
      </p>
      {mutation.isError && <ErrorState error={mutation.error} />}
      <form onSubmit={submit} aria-busy={mutation.isPending}>
        <label>Hesap adı<input required maxLength={200} value={displayName} onChange={(e) => setDisplayName(e.target.value)} /></label>
        <label>Kurum kodu<input maxLength={100} pattern="[A-Z][A-Z0-9_]*" value={institution} onChange={(e) => setInstitution(e.target.value.toUpperCase())} /></label>
        <label>
          Hesap türü
          <select value={accountType} onChange={(e) => setAccountType(e.target.value as AccountType)}>
            <option value="DEBIT_CARD">Banka kartı</option><option value="CREDIT_CARD">Kredi kartı</option>
            <option value="CHECKING">Vadesiz hesap</option><option value="SAVINGS">Birikim hesabı</option>
            <option value="CASH">Nakit</option><option value="OTHER">Diğer</option>
          </select>
        </label>
        <label>Para birimi<input required minLength={3} maxLength={3} pattern="[A-Z]{3}" value={currency} onChange={(e) => setCurrency(e.target.value.toUpperCase())} /></label>
        <button className="primary" disabled={mutation.isPending}>{mutation.isPending ? "Oluşturuluyor…" : "Hesabı oluştur"}</button>
      </form>
    </section>
  );
}

export function useAccount() {
  const context = useContext(AccountContext);
  if (!context) throw new Error("Account context missing");
  return context;
}
