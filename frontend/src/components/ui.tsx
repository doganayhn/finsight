import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { errorMessage } from "../api/client";
import type { Period } from "../types/contracts";
import { monthPeriod } from "../utils/presentation";

export function ErrorState({
  error,
  retry,
}: {
  error: unknown;
  retry?: () => void;
}) {
  return (
    <div className="notice error" role="alert">
      <p>{errorMessage(error)}</p>
      {retry && (
        <button type="button" onClick={retry}>
          Tekrar dene
        </button>
      )}
    </div>
  );
}
export function Loading() {
  return (
    <div className="skeletons" role="status" aria-label="Veriler yükleniyor">
      <div />
      <div />
      <div />
      <span className="sr-only">Veriler yükleniyor…</span>
    </div>
  );
}
export function Empty({
  children,
  action = true,
}: {
  children: ReactNode;
  action?: boolean;
}) {
  return (
    <div className="empty">
      <span className="empty-symbol" aria-hidden="true">
        ↗
      </span>
      <h3>{children}</h3>
      <p>Farklı bir dönem seçebilir veya hesap özeti yükleyebilirsiniz.</p>
      {action && (
        <Link className="button primary" to="/imports">
          Hesap özeti yükle
        </Link>
      )}
    </div>
  );
}
export function PageHeading({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children?: ReactNode;
}) {
  return (
    <header className="page-heading">
      <div>
        <p className="eyebrow">HARCAMALARINIZI ANLAYIN</p>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {children}
    </header>
  );
}
export function Pagination({
  offset,
  limit,
  count,
  hasMore,
  onChange,
  busy = false,
}: {
  offset: number;
  limit: number;
  count: number;
  hasMore: boolean;
  onChange: (value: number) => void;
  busy?: boolean;
}) {
  return (
    <nav className="pagination" aria-label="Sayfalama">
      <span>{count ? `${offset + 1}–${offset + count} kayıt` : "0 kayıt"}</span>
      <div>
        <button
          disabled={busy || offset === 0}
          onClick={() => onChange(Math.max(0, offset - limit))}
        >
          Önceki
        </button>
        <button
          disabled={busy || !hasMore}
          onClick={() => onChange(offset + limit)}
        >
          Sonraki
        </button>
      </div>
    </nav>
  );
}
export function PeriodFields({
  period,
  onChange,
  today = new Date(),
}: {
  period: Period;
  onChange: (period: Period) => void;
  today?: Date;
}) {
  const current = monthPeriod(today);
  const previous = monthPeriod(today, -1);
  const matches = (other: Period) =>
    period.start_date === other.start_date &&
    period.end_date === other.end_date;
  return (
    <div className="period-fields">
      <label>
        Dönem
        <select
          aria-label="Dönem kısayolu"
          value={matches(current) ? "0" : matches(previous) ? "-1" : "custom"}
          onChange={(e) => {
            if (e.target.value !== "custom")
              onChange(monthPeriod(today, Number(e.target.value)));
          }}
        >
          <option value="custom">Özel tarih aralığı</option>
          <option value="0">Bu ay</option>
          <option value="-1">Geçen ay</option>
        </select>
      </label>
      <label>
        Başlangıç
        <input
          required
          type="date"
          min="1900-01-01"
          max="2100-12-31"
          value={period.start_date}
          onChange={(e) => onChange({ ...period, start_date: e.target.value })}
        />
      </label>
      <label>
        Bitiş
        <input
          required
          type="date"
          min={period.start_date || "1900-01-01"}
          max="2100-12-31"
          value={period.end_date}
          onChange={(e) => onChange({ ...period, end_date: e.target.value })}
        />
      </label>
    </div>
  );
}
