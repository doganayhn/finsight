import { queryString, request } from "./client";
import type { Account, Page } from "../types/contracts";
export const getAccounts = (
  userId: string,
  offset: number,
  signal?: AbortSignal,
) =>
  request<Page & { accounts: Account[] }>(
    `/accounts${queryString({ limit: 50, offset })}`,
    { userId, signal },
  );
