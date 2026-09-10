import type { AuthSession } from "../types/contracts";

const baseUrl = import.meta.env.VITE_API_BASE_URL?.replace(/\/+$/, "");
let accessToken: string | null = null;
let refreshPromise: Promise<AuthSession> | null = null;
let authLost: (() => void) | null = null;

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    public batchId?: string,
  ) {
    super(code);
  }
}

export function setAccessToken(token: string | null) {
  accessToken = token;
}

export function setAuthLostHandler(handler: (() => void) | null) {
  authLost = handler;
}

async function parseError(response: Response): Promise<ApiError> {
  const body = (await response.json().catch(() => null)) as {
    detail?: { code?: string; import_batch_id?: string };
  } | null;
  return new ApiError(
    response.status,
    body?.detail?.code ?? "request_failed",
    body?.detail?.import_batch_id,
  );
}

export function refreshSession(): Promise<AuthSession> {
  if (!baseUrl) return Promise.reject(new Error("API configuration missing"));
  if (!refreshPromise) {
    refreshPromise = fetch(`${baseUrl}/auth/refresh`, {
      method: "POST",
      headers: { Accept: "application/json" },
      credentials: "include",
      signal: AbortSignal.timeout(30000),
    })
      .then(async (response) => {
        if (!response.ok) throw await parseError(response);
        const session = (await response.json()) as AuthSession;
        setAccessToken(session.access_token);
        return session;
      })
      .catch((error) => {
        setAccessToken(null);
        throw error;
      })
      .finally(() => {
        refreshPromise = null;
      });
  }
  return refreshPromise;
}

export function errorMessage(error: unknown): string {
  if (!(error instanceof ApiError))
    return "Sunucuya ulaşılamadı. Bağlantınızı kontrol edip tekrar deneyin.";
  const messages: Record<string, string> = {
    invalid_credentials: "Email veya şifre hatalı.",
    registration_unavailable: "Bu email ile kayıt oluşturulamadı.",
    auth_rate_limited: "Çok fazla deneme yapıldı. Biraz sonra tekrar deneyin.",
    duplicate_resolution_required:
      "Olası tekrarlar değişti. Güncel önizlemede her tekrar için seçim yapın.",
    decision_for_non_duplicate_candidate:
      "Tekrar durumu değişti. Güncel önizlemeyi yeniden inceleyin.",
    file_already_imported_or_pending:
      "Bu dosya daha önce yüklendi. Mevcut kaydı açabilirsiniz.",
    classification_incompatible_with_type:
      "Bu işlem türü seçilen sınıflandırmayı desteklemiyor.",
    assistant_unavailable:
      "Asistan bu ortamda etkin değil. FinSight’ın diğer özelliklerini kullanabilirsiniz.",
    assistant_provider_timeout:
      "Asistan yanıtı zaman aşımına uğradı. Biraz sonra tekrar deneyin.",
    assistant_rate_limited: "Asistan şu anda yoğun. Biraz sonra tekrar deneyin.",
    assistant_invalid_timezone:
      "Saat dilimi doğrulanamadı. Tarayıcı ayarınızı kontrol edin.",
    assistant_tool_limit:
      "Bu soru tek bir güvenli asistan isteği için fazla karmaşık. Daha dar bir soru deneyin.",
    assistant_tool_required:
      "Finansal yanıt doğrulanmış bir FinSight aracına dayanmadı. Lütfen tekrar deneyin.",
  };
  return (
    messages[error.code] ??
    {
      401: "Oturumunuz sona erdi. Lütfen yeniden giriş yapın.",
      403: "Bu işlem için erişim sağlanamadı.",
      404: "Kayıt bulunamadı veya hesabınıza ait değil.",
      409: "Kayıt durumu değişti. Güncel veriyi yükleyip yeniden deneyin.",
      413: "Dosya, sunucunun izin verdiği boyutu aşıyor.",
      415: "Dosya desteklenmiyor. Yapı Kredi TLcard PDF hesap özeti seçin.",
      422: "Bilgiler doğrulanamadı. Seçimleri ve hesap özeti biçimini kontrol edin.",
    }[error.status] ??
    "İşlem tamamlanamadı. Lütfen tekrar deneyin."
  );
}

export type Params = Record<string, string | number | undefined>;
export function queryString(params: Params): string {
  const result = new URLSearchParams();
  for (const [key, value] of Object.entries(params))
    if (value !== undefined && value !== "") result.set(key, String(value));
  return result.size ? `?${result}` : "";
}

interface RequestOptions {
  signal?: AbortSignal;
  method?: string;
  body?: unknown;
  auth?: boolean;
  refreshOnUnauthorized?: boolean;
}

export async function request<T>(
  path: string,
  options: RequestOptions = {},
  retryAfterRefresh = true,
): Promise<T> {
  if (!baseUrl) throw new Error("API configuration missing");
  const headers: Record<string, string> = { Accept: "application/json" };
  if (options.auth !== false && accessToken) headers.Authorization = `Bearer ${accessToken}`;
  const multipart = options.body instanceof FormData;
  if (options.body && !multipart) headers["Content-Type"] = "application/json";
  const response = await fetch(`${baseUrl}${path}`, {
    method: options.method ?? "GET",
    headers,
    credentials: "include",
    signal: options.signal ?? AbortSignal.timeout(60000),
    body: multipart
      ? (options.body as FormData)
      : options.body
        ? JSON.stringify(options.body)
        : undefined,
  });
  if (
    response.status === 401 &&
    options.auth !== false &&
    options.refreshOnUnauthorized !== false &&
    retryAfterRefresh
  ) {
    try {
      await refreshSession();
      return await request<T>(path, options, false);
    } catch (error) {
      authLost?.();
      throw error;
    }
  }
  if (!response.ok) throw await parseError(response);
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const getJson = (path: string, signal: AbortSignal): Promise<unknown> =>
  request(path, { signal, auth: false, refreshOnUnauthorized: false });
