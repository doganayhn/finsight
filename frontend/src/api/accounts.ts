import { queryString, request } from "./client";
import type { Account, AccountCreate, Page } from "../types/contracts";
export const getAccounts = (offset: number, signal?: AbortSignal) =>
  request<Page & { accounts: Account[] }>(
    `/accounts${queryString({ limit: 50, offset })}`,
    { signal },
  );
export const createAccount = (body: AccountCreate) =>
  request<Account>("/accounts", { method: "POST", body });
