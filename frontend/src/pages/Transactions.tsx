import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getTransactions, correctTransaction } from "../api/transactions";
import { getCategories } from "../api/categories";
import { useDevelopment } from "../hooks/context";
import {
  Empty,
  ErrorState,
  Loading,
  PageHeading,
  Pagination,
  PeriodFields,
} from "../components/ui";
import {
  categoryLabel,
  dateLabel,
  money,
  monthPeriod,
  reviewLabels,
  typeLabels,
} from "../utils/presentation";
import type { Correction, Transaction } from "../types/contracts";

export function CorrectionDialog({
  transaction,
  onClose,
  onSaved,
}: {
  transaction: Transaction;
  onClose: () => void;
  onSaved?: () => void;
}) {
  const { userId } = useDevelopment();
  const dialog = useRef<HTMLDialogElement>(null);
  const busy = useRef(false);
  const client = useQueryClient();
  const [merchant, setMerchant] = useState(
    transaction.merchant_normalized ?? "",
  );
  const [category, setCategory] = useState(transaction.category?.id ?? "");
  const [persist, setPersist] = useState(false);
  const categories = useQuery({
    queryKey: ["categories", userId],
    queryFn: ({ signal }) => getCategories(userId, signal),
  });
  const mutation = useMutation({
    mutationFn: (body: Correction) =>
      correctTransaction(userId, transaction.id, body),
    onSuccess: async () => {
      await Promise.all([
        client.invalidateQueries({ queryKey: ["transactions", userId] }),
        client.invalidateQueries({ queryKey: ["analytics", userId] }),
      ]);
      onSaved?.();
      onClose();
    },
    onSettled: () => {
      busy.current = false;
    },
  });
  useEffect(() => {
    const node = dialog.current;
    node?.showModal();
    return () => node?.close();
  }, []);
  const merchantChanged =
    merchant.trim() !== (transaction.merchant_normalized ?? "") &&
    merchant.trim().length > 0;
  const categoryChanged =
    category !== "" && category !== transaction.category?.id;
  return (
    <dialog
      ref={dialog}
      onCancel={(e) => {
        if (mutation.isPending) e.preventDefault();
        else onClose();
      }}
      aria-labelledby="correction-title"
    >
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (busy.current) return;
          busy.current = true;
          mutation.mutate({
            ...(merchantChanged
              ? { preferred_merchant_name: merchant.trim() }
              : {}),
            ...(categoryChanged ? { category_id: category } : {}),
            persist_as_rule: persist,
          });
        }}
      >
        <div className="panel-heading">
          <h2 id="correction-title">Sınıflandırmayı düzelt</h2>
          <button
            type="button"
            onClick={onClose}
            disabled={mutation.isPending}
            aria-label="Düzeltmeyi kapat"
          >
            ×
          </button>
        </div>
        <p className="footnote">
          Yalnızca işletme adı ve kategori yorumunu düzenlersiniz.
        </p>
        <div className="raw-context">
          <span>Özgün açıklama · salt okunur</span>
          <p>{transaction.description_raw}</p>
          <strong>{money(transaction.amount, transaction.currency)}</strong>
        </div>
        <label>
          İşletme adı
          <input
            maxLength={255}
            value={merchant}
            onChange={(e) => setMerchant(e.target.value)}
            autoFocus
          />
        </label>
        <label>
          Kategori
          <select
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            disabled={!categories.data}
          >
            <option value="">Kategori seçin</option>
            {categories.data?.map((c) => (
              <option key={c.id} value={c.id}>
                {categoryLabel(c.code)}
              </option>
            ))}
          </select>
        </label>
        {categories.isError && (
          <ErrorState
            error={categories.error}
            retry={() => void categories.refetch()}
          />
        )}
        <label className="checkbox">
          <input
            type="checkbox"
            checked={persist}
            onChange={(e) => setPersist(e.target.checked)}
          />
          Bu tercihi gelecekte benzer işlemlerde kullan
        </label>
        <p className="footnote">
          Diğer geçmiş işlemler değişmez. Seçimin uygunluğunu sunucu doğrular.
        </p>
        {mutation.isError && <ErrorState error={mutation.error} />}
        <div className="dialog-actions">
          <button type="button" onClick={onClose} disabled={mutation.isPending}>
            Vazgeç
          </button>
          <button
            className="primary"
            disabled={
              mutation.isPending || (!merchantChanged && !categoryChanged)
            }
          >
            {mutation.isPending ? "Kaydediliyor…" : "Değişiklikleri kaydet"}
          </button>
        </div>
      </form>
    </dialog>
  );
}
export function Transactions() {
  const { userId, accountId } = useDevelopment();
  const [draft, setDraft] = useState(() => ({
    ...monthPeriod(new Date()),
    category_id: "",
    transaction_type: "",
    review_status: "",
    currency: "",
    merchant_query: "",
  }));
  const [filters, setFilters] = useState(draft);
  const [offset, setOffset] = useState(0);
  const [edited, setEdited] = useState<Transaction | null>(null);
  const [notice, setNotice] = useState("");
  // Account changes reset pagination and dismiss any old account's edit context.
  useEffect(() => {
    setOffset(0);
    setEdited(null);
  }, [accountId]);
  const categories = useQuery({
    queryKey: ["categories", userId],
    queryFn: ({ signal }) => getCategories(userId, signal),
  });
  const params = { ...filters, account_id: accountId, limit: 20, offset };
  const rows = useQuery({
    queryKey: ["transactions", userId, params],
    queryFn: ({ signal }) => getTransactions(userId, params, signal),
  });
  return (
    <>
      <PageHeading
        title="İşlemler"
        description="Her hareketin ayrıntısını görün, sınıflandırmaları düzenleyin."
      />
      <form
        className="panel transaction-filters"
        onSubmit={(e) => {
          e.preventDefault();
          setOffset(0);
          setFilters(draft);
        }}
      >
        <PeriodFields
          period={draft}
          onChange={(p) => setDraft({ ...draft, ...p })}
        />
        <div className="filter-grid">
          <label className="search">
            İşletme veya açıklama
            <input
              type="search"
              maxLength={100}
              placeholder="İşlem ara…"
              value={draft.merchant_query}
              onChange={(e) =>
                setDraft({ ...draft, merchant_query: e.target.value })
              }
            />
          </label>
          <label>
            Kategori
            <select
              value={draft.category_id}
              onChange={(e) =>
                setDraft({ ...draft, category_id: e.target.value })
              }
            >
              <option value="">Tüm kategoriler</option>
              {categories.data?.map((c) => (
                <option key={c.id} value={c.id}>
                  {categoryLabel(c.code)}
                </option>
              ))}
            </select>
          </label>
          <label>
            İşlem türü
            <select
              value={draft.transaction_type}
              onChange={(e) =>
                setDraft({ ...draft, transaction_type: e.target.value })
              }
            >
              <option value="">Tüm türler</option>
              {Object.entries(typeLabels).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </select>
          </label>
          <label>
            İnceleme durumu
            <select
              value={draft.review_status}
              onChange={(e) =>
                setDraft({ ...draft, review_status: e.target.value })
              }
            >
              <option value="">Tüm durumlar</option>
              {Object.entries(reviewLabels).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </select>
          </label>
          <label>
            Para birimi
            <input
              placeholder="Tümü"
              maxLength={3}
              pattern="[A-Z]{3}|"
              value={draft.currency}
              onChange={(e) =>
                setDraft({ ...draft, currency: e.target.value.toUpperCase() })
              }
            />
          </label>
          <button className="primary">Filtreleri uygula</button>
        </div>
        {categories.isError && (
          <ErrorState
            error={categories.error}
            retry={() => void categories.refetch()}
          />
        )}
      </form>
      {notice && (
        <p className="notice success" role="status">
          {notice}
        </p>
      )}
      {rows.isPending ? (
        <Loading />
      ) : rows.isError ? (
        <ErrorState error={rows.error} retry={() => void rows.refetch()} />
      ) : (
        <section className="panel transaction-panel">
          <div className="panel-heading">
            <h2>İşlem listesi</h2>
            <span className="badge">Sunucudan güncel kayıtlar</span>
          </div>
          {rows.data.transactions.length === 0 ? (
            <Empty>
              {filters.review_status === "NEEDS_REVIEW"
                ? "İncelenecek işlem yok."
                : "Bu filtrelerle işlem bulunamadı."}
            </Empty>
          ) : (
            <div className="transaction-list">
              <div className="transaction-row table-heading" aria-hidden="true">
                <span>TARİH</span>
                <span>İŞLEM / AÇIKLAMA</span>
                <span>KATEGORİ / DURUM</span>
                <span>TUTAR</span>
                <span />
              </div>
              {rows.data.transactions.map((row) => (
                <article className="transaction-row" key={row.id}>
                  <time dateTime={row.transaction_date}>
                    {dateLabel(row.transaction_date)}
                  </time>
                  <div className="transaction-description">
                    <strong>
                      {row.merchant_normalized ?? "Bilinmeyen işletme"}
                    </strong>
                    <p>{row.description_raw}</p>
                    <small>
                      {typeLabels[row.transaction_type]}
                      {row.installment_count
                        ? ` · Taksit ${row.installment_index ?? "—"}/${row.installment_count}`
                        : ""}
                    </small>
                  </div>
                  <div>
                    <span className="category-tag">
                      {categoryLabel(row.category?.code ?? "OTHER")}
                    </span>
                    <small
                      className={
                        row.review_status === "NEEDS_REVIEW"
                          ? "review-needed"
                          : "muted"
                      }
                    >
                      {reviewLabels[row.review_status]}
                    </small>
                  </div>
                  <div className="transaction-amount">
                    <strong
                      className={row.amount.startsWith("-") ? "" : "positive"}
                    >
                      {money(row.amount, row.currency)}
                    </strong>
                    <small>
                      {row.amount.startsWith("-")
                        ? "Çıkış"
                        : row.amount === "0.00"
                          ? "Sıfır tutar"
                          : "Giriş"}
                    </small>
                  </div>
                  <button
                    aria-label={`${row.merchant_normalized ?? "İşlem"} sınıflandırmasını düzelt`}
                    onClick={() => {
                      setNotice("");
                      setEdited(row);
                    }}
                  >
                    Düzelt
                  </button>
                </article>
              ))}
            </div>
          )}
          <Pagination
            offset={offset}
            limit={20}
            count={rows.data.transactions.length}
            hasMore={rows.data.has_more}
            onChange={setOffset}
            busy={rows.isFetching}
          />
        </section>
      )}
      {edited && (
        <CorrectionDialog
          key={edited.id}
          transaction={edited}
          onClose={() => {
            setEdited(null);
          }}
          onSaved={() => {
            setNotice("İşlem listesi sunucudan güncellendi.");
          }}
        />
      )}
    </>
  );
}
