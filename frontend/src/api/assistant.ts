import { request } from "./client";
import type {
  AssistantHistoryMessage,
  AssistantResponse,
  AssistantStatus,
} from "../types/contracts";

export const getAssistantStatus = (signal?: AbortSignal) =>
  request<AssistantStatus>("/assistant/status", { signal });

export const sendAssistantMessage = (
  userId: string,
  payload: {
    message: string;
    history: AssistantHistoryMessage[];
    account_id: string | null;
    client_timezone: string;
  },
  signal: AbortSignal,
) =>
  request<AssistantResponse>("/assistant/chat", {
    userId,
    signal,
    method: "POST",
    body: payload,
  });
