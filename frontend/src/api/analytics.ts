import { queryString, request } from "./client";
import type { Params } from "./client";
import type {
  Summary,
  CategoryAnalytics,
  MerchantAnalytics,
  Trend,
  Comparison,
  Projection,
} from "../types/contracts";
export interface AnalyticsResponses {
  summary: Summary;
  categories: CategoryAnalytics;
  merchants: MerchantAnalytics;
  trend: Trend;
  compare: Comparison;
  projection: Projection;
}
export function getAnalytics<K extends keyof AnalyticsResponses>(
  kind: K,
  params: Params,
  signal?: AbortSignal,
) {
  return request<AnalyticsResponses[K]>(
    `/analytics/${kind}${queryString(params)}`,
    { signal },
  );
}
