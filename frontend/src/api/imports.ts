import { queryString, request } from "./client";
import type {
  ImportPreview,
  ImportHistoryItem,
  Page,
  Decisions,
} from "../types/contracts";
export const getImports = (
  userId: string,
  accountId: string,
  offset: number,
  signal?: AbortSignal,
) =>
  request<Page & { imports: ImportHistoryItem[] }>(
    `/imports${queryString({ account_id: accountId, limit: 20, offset })}`,
    { userId, signal },
  );
export const getImport = (userId: string, id: string, signal?: AbortSignal) =>
  request<ImportPreview>(`/imports/${id}`, { userId, signal });
export function previewImport(userId: string, accountId: string, file: File) {
  const body = new FormData();
  body.set("account_id", accountId);
  body.set("file", file);
  return request<ImportPreview>("/imports/preview", {
    userId,
    method: "POST",
    body,
  });
}
export const confirmImport = (
  userId: string,
  id: string,
  decisions: Decisions,
) =>
  request<ImportPreview>(`/imports/${id}/confirm`, {
    userId,
    method: "POST",
    body: { decisions },
  });
