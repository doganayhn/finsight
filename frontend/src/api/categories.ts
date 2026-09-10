import { request } from "./client";
import type { Category } from "../types/contracts";
export const getCategories = (signal?: AbortSignal) =>
  request<Category[]>("/categories", { signal });
