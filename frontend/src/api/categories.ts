import { request } from "./client";
import type { Category } from "../types/contracts";
export const getCategories = (userId: string, signal?: AbortSignal) =>
  request<Category[]>("/categories", { userId, signal });
