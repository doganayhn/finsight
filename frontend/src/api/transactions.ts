import { queryString, request } from "./client";
import type { Params } from "./client";
import type {
  TransactionPage,
  Correction,
  CorrectionResult,
} from "../types/contracts";
export const getTransactions = (
  params: Params,
  signal?: AbortSignal,
) =>
  request<TransactionPage>(`/transactions${queryString(params)}`, {
    signal,
  });
export const correctTransaction = (
  id: string,
  body: Correction,
) =>
  request<CorrectionResult>(`/transactions/${id}/classification`, {
    method: "PATCH",
    body,
  });
