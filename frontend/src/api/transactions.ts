import { queryString, request } from "./client";
import type { Params } from "./client";
import type {
  TransactionPage,
  Correction,
  CorrectionResult,
} from "../types/contracts";
export const getTransactions = (
  userId: string,
  params: Params,
  signal?: AbortSignal,
) =>
  request<TransactionPage>(`/transactions${queryString(params)}`, {
    userId,
    signal,
  });
export const correctTransaction = (
  userId: string,
  id: string,
  body: Correction,
) =>
  request<CorrectionResult>(`/transactions/${id}/classification`, {
    userId,
    method: "PATCH",
    body,
  });
