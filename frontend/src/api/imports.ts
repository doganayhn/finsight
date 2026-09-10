import { queryString, request } from "./client";
import type {
  ImportPreview,
  ImportHistoryItem,
  Page,
  Decisions,
} from "../types/contracts";
export const getImports = (
  accountId: string,
  offset: number,
  signal?: AbortSignal,
) =>
  request<Page & { imports: ImportHistoryItem[] }>(
    `/imports${queryString({ account_id: accountId, limit: 20, offset })}`,
    { signal },
  );
export const getImport = (id: string, signal?: AbortSignal) =>
  request<ImportPreview>(`/imports/${id}`, { signal });
export function previewImport(accountId: string, file: File) {
  const body = new FormData();
  body.set("account_id", accountId);
  body.set("file", file);
  return request<ImportPreview>("/imports/preview", {
    method: "POST",
    body,
  });
}
export const confirmImport = (
  id: string,
  decisions: Decisions,
) =>
  request<ImportPreview>(`/imports/${id}/confirm`, {
    method: "POST",
    body: { decisions },
  });
