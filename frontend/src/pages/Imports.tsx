import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  confirmImport,
  getImport,
  getImports,
  previewImport,
} from "../api/imports";
import { ApiError } from "../api/client";
import { useAccount } from "../hooks/context";
import {
  Empty,
  ErrorState,
  Loading,
  PageHeading,
  Pagination,
} from "../components/ui";
import {
  dateLabel,
  importLabels,
  money,
  typeLabels,
} from "../utils/presentation";
import type { Decisions, ImportPreview } from "../types/contracts";

export function Imports() {
  const { accountId } = useAccount();
  const [offset, setOffset] = useState(0);
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState("");
  const uploadBusy = useRef(false);
  const input = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();
  const client = useQueryClient();
  const history = useQuery({
    queryKey: ["imports", accountId, offset],
    queryFn: ({ signal }) => getImports(accountId, offset, signal),
  });
  useEffect(() => {
    setOffset(0);
  }, [accountId]);
  const upload = useMutation({
    mutationFn: (selected: File) => previewImport(accountId, selected),
    onSuccess: (data) => {
      client.setQueryData(["import", data.import_batch_id], data);
      navigate(`/imports/${data.import_batch_id}`);
    },
    onSettled: () => {
      uploadBusy.current = false;
      setFile(null);
      if (input.current) input.current.value = "";
      void client.invalidateQueries({ queryKey: ["imports"] });
    },
  });
  return (
    <>
      <PageHeading
        title="Hesap özetleri"
        description="PDF’nizi yükleyin, kontrol edin ve işlemlerinize ekleyin."
      />
      <div className="import-intro">
        <section className="panel upload-panel">
          <div className="upload-symbol" aria-hidden="true">
            ↥
          </div>
          <h2>Yeni hesap özeti</h2>
          <p>Yapı Kredi TLcard · PDF</p>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (!file || !accountId || uploadBusy.current) return;
              uploadBusy.current = true;
              upload.mutate(file);
            }}
          >
            <label className="file-picker">
              PDF dosyası seç
              <input
                ref={input}
                type="file"
                accept="application/pdf,.pdf"
                disabled={upload.isPending}
                onChange={(e) => {
                  const selected = e.target.files?.[0];
                  setFileError("");
                  upload.reset();
                  if (
                    selected &&
                    (!selected.name.toLowerCase().endsWith(".pdf") ||
                      (selected.type && selected.type !== "application/pdf"))
                  ) {
                    setFile(null);
                    setFileError("Lütfen bir PDF dosyası seçin.");
                    return;
                  }
                  setFile(selected ?? null);
                }}
              />
            </label>
            {file && (
              <p role="status">
                PDF seçildi · {Math.ceil(file.size / 1024)} KB
              </p>
            )}
            {!accountId && (
              <p className="notice">
                Yüklemek için üstteki hesap listesinden bir hesap seçin.
              </p>
            )}
            {fileError && (
              <p role="alert" className="notice error">
                {fileError}
              </p>
            )}
            <button
              className="primary"
              disabled={!file || !accountId || upload.isPending}
            >
              {upload.isPending ? "Önizleme hazırlanıyor…" : "Yükle ve önizle"}
            </button>
          </form>
          {upload.isError && (
            <>
              <ErrorState error={upload.error} />
              {upload.error instanceof ApiError && upload.error.batchId && (
                <Link
                  to={`/imports/${upload.error.batchId}`}
                  className="button"
                >
                  Mevcut kaydı aç
                </Link>
              )}
            </>
          )}
          <p className="footnote">
            Varsayılan dosya sınırı 10 MiB’dir; sunucunun yapılandırılmış sınırı
            geçerlidir. CSV, XLSX ve diğer banka biçimleri henüz desteklenmiyor.
          </p>
        </section>
        <aside className="import-guide">
          <p className="eyebrow">KONTROL SİZDE</p>
          <h2>
            Üç adımda
            <br />
            daha net bir görünüm.
          </h2>
          <ol>
            <li>
              <b>01</b>
              <div>
                <strong>Hesap özetini seçin</strong>
                <p>Doğru hesabı ve desteklenen PDF’yi seçin.</p>
              </div>
            </li>
            <li>
              <b>02</b>
              <div>
                <strong>Önizlemeyi inceleyin</strong>
                <p>Tutar eşleşmesini ve olası tekrarları kontrol edin.</p>
              </div>
            </li>
            <li>
              <b>03</b>
              <div>
                <strong>Onaylayın</strong>
                <p>İşlemler yalnızca onayınızdan sonra analizlere girer.</p>
              </div>
            </li>
          </ol>
        </aside>
      </div>
      <section className="panel">
        <div className="panel-heading">
          <h2>Yükleme geçmişi</h2>
          <button
            onClick={() => void history.refetch()}
            disabled={history.isFetching}
          >
            Yenile
          </button>
        </div>
        {history.isPending ? (
          <Loading />
        ) : history.isError ? (
          <ErrorState
            error={history.error}
            retry={() => void history.refetch()}
          />
        ) : (
          <>
            {history.data.imports.length === 0 ? (
              <Empty action={false}>Henüz hesap özeti yüklemediniz.</Empty>
            ) : (
              <ul className="history-list">
                {history.data.imports.map((item) => (
                  <li key={item.id}>
                    <div>
                      <strong>
                        {item.institution_code === "YAPI_KREDI"
                          ? "Yapı Kredi"
                          : (item.institution_code ?? "Hesap özeti")}{" "}
                        · {item.statement_type ?? "PDF"}
                      </strong>
                      <p>
                        {item.statement_period ?? "Dönem belirtilmedi"} ·{" "}
                        {dateLabel(item.created_at)} · {item.total_rows} işlem
                      </p>
                    </div>
                    <span
                      className={`badge ${item.import_status === "COMPLETED" ? "success" : ""}`}
                    >
                      {importLabels[item.import_status]}
                    </span>
                    <Link className="button" to={`/imports/${item.id}`}>
                      Aç
                    </Link>
                  </li>
                ))}
              </ul>
            )}
            <Pagination
              offset={offset}
              limit={20}
              count={history.data.imports.length}
              hasMore={history.data.has_more}
              onChange={setOffset}
            />
          </>
        )}
      </section>
    </>
  );
}

export function PreviewContent({
  data,
  decisions,
  onDecision,
  onConfirm,
  pending,
}: {
  data: ImportPreview;
  decisions: Decisions;
  onDecision: (id: string, value: "import" | "skip") => void;
  onConfirm: () => void;
  pending: boolean;
}) {
  const duplicates = data.transactions.filter(
    (t) => t.duplicate_matches.length > 0,
  );
  const unresolved = duplicates.filter((t) => !decisions[t.id]).length;
  const canConfirm =
    data.status === "AWAITING_CONFIRMATION" &&
    data.validation_status === "PASSED";
  return (
    <>
      <section className="panel">
        <div className="panel-heading">
          <h2>
            {data.status === "COMPLETED"
              ? "İçe aktarma tamamlandı"
              : "Hesap özeti kontrolü"}
          </h2>
          <span
            className={`badge ${data.validation_status === "PASSED" ? "success" : "warning"}`}
          >
            {importLabels[data.status]}
          </span>
        </div>
        <p>
          {data.institution_code === "YAPI_KREDI"
            ? "Yapı Kredi"
            : (data.institution_code ?? "Kurum belirtilmedi")}{" "}
          · {data.statement_type ?? "Hesap özeti"} ·{" "}
          {data.statement_period ?? "Dönem belirtilmedi"} ·{" "}
          {data.currency ?? "—"}
        </p>
        <div className="reconciliation">
          <div>
            <span>Özette bildirilen</span>
            <strong>{money(data.reported_total, data.currency)}</strong>
          </div>
          <div>
            <span>Okunan toplam</span>
            <strong>{money(data.parsed_total, data.currency)}</strong>
          </div>
          <div>
            <span>Doğrulama</span>
            <strong>
              {data.validation_status === "PASSED"
                ? "✓ Eşleşti"
                : "Doğrulanamadı"}
            </strong>
          </div>
          <div>
            <span>İşlem sayısı</span>
            <strong>{data.counts.total_rows}</strong>
          </div>
        </div>
        {data.status === "COMPLETED" && (
          <div className="completion" role="status">
            <h3>{data.counts.imported_rows} işlem eklendi</h3>
            <p>{data.counts.skipped_duplicate_rows} olası tekrar atlandı.</p>
            <Link className="button primary" to="/overview">
              Genel bakışa git
            </Link>
            <Link className="button" to="/transactions">
              İşlemleri gör
            </Link>
          </div>
        )}
        {data.validation_status !== "PASSED" && (
          <p className="notice error" role="alert">
            Hesap özeti doğrulanamadı. Bu kayıt onaylanamaz; desteklenen dosyayı
            kontrol ederek yeniden yükleyin.
          </p>
        )}
      </section>
      {data.status !== "COMPLETED" && data.transactions.length > 0 && (
        <section className="panel">
          <div className="panel-heading">
            <h2>İşlem önizlemesi</h2>
            <span className="badge">Henüz analizlere dahil değil</span>
          </div>
          {duplicates.length > 0 && (
            <p className="notice warning">
              {duplicates.length} olası tekrar var. Her biri için “İçe aktar”
              veya “Atla” seçin. Normal işlemler otomatik eklenir.
            </p>
          )}
          <ul className="candidate-list">
            {data.transactions.map((t) => (
              <li
                key={t.id}
                className={t.duplicate_matches.length ? "duplicate" : ""}
              >
                <div>
                  <time>{dateLabel(t.transaction_date)}</time>
                  <strong>{t.merchant_raw ?? t.description_raw}</strong>
                  <p>{t.description_raw}</p>
                  <small>{typeLabels[t.transaction_type]}</small>
                </div>
                <strong>{money(t.amount, t.currency)}</strong>
                {t.duplicate_matches.length ? (
                  <fieldset disabled={pending}>
                    <legend>Olası tekrar · seçim gerekli</legend>
                    <label>
                      <input
                        type="radio"
                        name={t.id}
                        checked={decisions[t.id] === "import"}
                        onChange={() => onDecision(t.id, "import")}
                      />
                      İçe aktar
                    </label>
                    <label>
                      <input
                        type="radio"
                        name={t.id}
                        checked={decisions[t.id] === "skip"}
                        onChange={() => onDecision(t.id, "skip")}
                      />
                      Atla
                    </label>
                  </fieldset>
                ) : (
                  <span className="badge">Otomatik eklenecek</span>
                )}
              </li>
            ))}
          </ul>
          {canConfirm && (
            <div className="confirm-bar">
              <p>
                {unresolved
                  ? `${unresolved} olası tekrar için seçim bekleniyor.`
                  : "İşlemler onayınızla hesabınıza eklenecek."}
              </p>
              <button
                className="primary"
                disabled={pending || unresolved > 0}
                onClick={onConfirm}
              >
                {pending ? "Onaylanıyor…" : "İçe aktarmayı onayla"}
              </button>
            </div>
          )}
        </section>
      )}
    </>
  );
}
export function ImportDetail() {
  const { id = "" } = useParams();
  useAccount();
  const client = useQueryClient();
  const [decisions, setDecisions] = useState<Decisions>({});
  const [message, setMessage] = useState("");
  const busy = useRef(false);
  const preview = useQuery({
    queryKey: ["import", id],
    queryFn: ({ signal }) => getImport(id, signal),
    staleTime: 0,
  });
  useEffect(() => {
    setDecisions({});
    setMessage("");
  }, [id]);
  const confirm = useMutation({
    mutationFn: (selected: Decisions) => confirmImport(id, selected),
    onSuccess: async (data) => {
      client.setQueryData(["import", id], data);
      await Promise.all(
        ["analytics", "transactions", "imports"].map((key) =>
          client.invalidateQueries({ queryKey: [key] }),
        ),
      );
    },
    onError: async (error) => {
      if (
        error instanceof ApiError &&
        [
          "duplicate_resolution_required",
          "decision_for_non_duplicate_candidate",
        ].includes(error.code)
      ) {
        setDecisions({});
        setMessage(
          "Tekrar durumu güncellendi. Lütfen seçimlerinizi yeniden yapın.",
        );
        await preview.refetch();
      }
    },
    onSettled: () => {
      busy.current = false;
    },
  });
  function submit() {
    if (busy.current || !preview.data) return;
    busy.current = true;
    const current = Object.fromEntries(
      preview.data.transactions
        .filter((t) => t.duplicate_matches.length > 0 && decisions[t.id])
        .map((t) => [t.id, decisions[t.id]]),
    );
    confirm.mutate(current);
  }
  return (
    <>
      <PageHeading
        title="Hesap özeti önizlemesi"
        description="Tutarları ve tekrarları kontrol ederek güvenle devam edin."
      >
        <Link to="/imports" className="button">
          ← Hesap özetleri
        </Link>
      </PageHeading>
      {message && (
        <p className="notice warning" role="status">
          {message}
        </p>
      )}
      {confirm.isError && <ErrorState error={confirm.error} />}
      {preview.isPending ? (
        <Loading />
      ) : preview.isError ? (
        <ErrorState
          error={preview.error}
          retry={() => void preview.refetch()}
        />
      ) : (
        <PreviewContent
          data={preview.data}
          decisions={decisions}
          onDecision={(key, value) =>
            setDecisions({ ...decisions, [key]: value })
          }
          onConfirm={submit}
          pending={confirm.isPending || preview.isFetching}
        />
      )}
    </>
  );
}
