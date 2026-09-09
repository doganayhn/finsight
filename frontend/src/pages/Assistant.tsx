import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { useQuery } from "@tanstack/react-query";
import { getAssistantStatus, sendAssistantMessage } from "../api/assistant";
import { errorMessage } from "../api/client";
import { useDevelopment, uuidValid } from "../hooks/context";
import type { AssistantHistoryMessage } from "../types/contracts";

interface Message extends AssistantHistoryMessage {
  tools?: { name: string; label: string }[];
}

const starters = [
  "Bu ay ne kadar harcadım?",
  "En çok hangi kategoriye harcadım?",
  "Son altı ay harcamam nasıl değişti?",
  "Bu hızla ay sonunda ne kadar harcarım?",
];

function timezone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "Europe/Istanbul";
  } catch {
    return "Europe/Istanbul";
  }
}

export function Assistant() {
  const { userId, accountId, accountName } = useDevelopment();
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abort = useRef<AbortController | null>(null);
  const scopeKey = `${userId}:${accountId}`;
  const previousScope = useRef(scopeKey);
  const status = useQuery({
    queryKey: ["assistant-status"],
    queryFn: ({ signal }) => getAssistantStatus(signal),
    staleTime: 60000,
  });

  useEffect(() => {
    if (previousScope.current !== scopeKey) {
      abort.current?.abort();
      setMessages([]);
      setDraft("");
      setPending(false);
      setError(null);
      previousScope.current = scopeKey;
    }
  }, [scopeKey]);
  useEffect(() => () => abort.current?.abort(), []);

  async function submit(message: string) {
    const content = message.trim();
    if (!content || pending || !status.data?.enabled || !uuidValid(userId)) return;
    const history = messages.slice(-10).map(({ role, content: text }) => ({
      role,
      content: text,
    }));
    const controller = new AbortController();
    abort.current = controller;
    setMessages((current) => [...current, { role: "user", content }]);
    setDraft("");
    setPending(true);
    setError(null);
    try {
      const response = await sendAssistantMessage(
        userId,
        {
          message: content,
          history,
          account_id: accountId || null,
          client_timezone: timezone(),
        },
        controller.signal,
      );
      if (!controller.signal.aborted)
        setMessages((current) => [
          ...current,
          { role: "assistant", content: response.answer, tools: response.used_tools },
        ]);
    } catch (caught) {
      if (!controller.signal.aborted) setError(errorMessage(caught));
    } finally {
      if (!controller.signal.aborted) setPending(false);
    }
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    void submit(draft);
  }

  return (
    <section className="assistant-page">
      <header className="page-heading assistant-heading">
        <div>
          <p className="eyebrow">FINSIGHT ASİSTAN</p>
          <h1>Harcamalarınızı sorun.</h1>
          <p>Yanıtlar, FinSight’ın deterministik analiz araçlarına dayanır.</p>
        </div>
        <div className="assistant-scope" aria-label="Asistan hesap kapsamı">
          <small>HESAP KAPSAMI</small>
          <strong>{accountId ? accountName ?? "Seçili hesap" : "Tüm hesaplar"}</strong>
        </div>
      </header>

      <div className="assistant-layout">
        <div className="panel assistant-chat">
          {status.isLoading && <p role="status">Asistan kullanılabilirliği kontrol ediliyor…</p>}
          {status.isError && (
            <div className="notice" role="alert">
              Asistan durumuna ulaşılamadı. FinSight’ın diğer özelliklerini kullanmaya devam edebilirsiniz.
            </div>
          )}
          {status.data && !status.data.enabled && (
            <div className="notice" role="status">
              Asistan bu yerel ortamda etkin değil. Backend için GROQ_API_KEY yapılandırıldığında kullanılabilir.
            </div>
          )}
          {messages.length === 0 && status.data?.enabled && (
            <div className="assistant-welcome">
              <h2>Ne öğrenmek istersiniz?</h2>
              <p>Bir başlangıç sorusu seçin veya kendi sorunuzu yazın.</p>
              <div className="starter-grid">
                {starters.map((starter) => (
                  <button key={starter} type="button" onClick={() => void submit(starter)}>
                    {starter}
                  </button>
                ))}
              </div>
            </div>
          )}
          <ol className="assistant-messages" aria-live="polite">
            {messages.map((message, index) => (
              <li className={message.role} key={`${message.role}-${index}`}>
                <small>{message.role === "user" ? "Siz" : "FinSight"}</small>
                <p>{message.content}</p>
                {!!message.tools?.length && (
                  <div className="tool-labels" aria-label="Kullanılan FinSight araçları">
                    {message.tools.map((tool) => (
                      <span key={`${tool.name}-${index}`}>{tool.label}</span>
                    ))}
                  </div>
                )}
              </li>
            ))}
            {pending && (
              <li className="assistant pending" role="status">
                <small>FinSight</small><p>FinSight verilerinizi inceliyor…</p>
              </li>
            )}
          </ol>
          {error && <div className="notice error" role="alert">{error}</div>}
          <form className="assistant-composer" onSubmit={onSubmit}>
            <label htmlFor="assistant-message">Sorunuz</label>
            <textarea
              id="assistant-message"
              rows={3}
              maxLength={4000}
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              placeholder="Örneğin: Geçen aya göre harcamam arttı mı?"
              disabled={pending || !status.data?.enabled}
            />
            <div>
              <small>{draft.length}/4000</small>
              <button className="primary" disabled={!draft.trim() || pending || !status.data?.enabled}>
                {pending ? "Yanıtlanıyor…" : "Gönder"}
              </button>
            </div>
          </form>
        </div>
        <aside className="assistant-disclosure">
          <p className="section-caption">GİZLİLİK VE KAPSAM</p>
          <h2>Kontrol FinSight’ta.</h2>
          <p>Asistana yazdığınız mesaj ve FinSight araçlarının seçtiği sınırlı, türetilmiş finansal veriler yanıt oluşturmak için Groq’a gönderilebilir.</p>
          <p>Ham hesap özeti PDF’leri, çıkarılmış PDF metni ve hesap kimlik bilgileri Groq’a gönderilmez.</p>
          <p>Yanıtlar yalnızca içe aktarılan işlemleri kapsar; güncel banka bakiyesini göstermez.</p>
          <small>Sohbet bu sekmenin belleğinde tutulur ve yenilemede silinir.</small>
        </aside>
      </div>
    </section>
  );
}
