import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import { Link, useSearchParams } from "react-router-dom";
import { askTutor, getConversation, listConversations, type Citation, type Message } from "../../api";
import { Badge, Button, Card, Spinner, inputClass, timeAgo } from "../../components/ui";

const SUGGESTIONS = ["Give me an overview of what my materials cover", "Explain the hardest concept with an example", "How am I doing so far? What should I focus on?", "Quiz me on one concept I'm weak at"];

function CitationList({ citations }: { citations: Citation[] }) {
  if (!citations?.length) return null;
  return (
    <div className="mt-2 flex flex-wrap gap-1">
      {citations.map((c) => (
        <span key={c.label} title={c.snippet} className="inline-flex items-center gap-1 rounded-md border border-slate-200 bg-white px-2 py-0.5 text-xs text-slate-600">
          <span className="font-semibold text-orange-600">{c.label}</span> {c.material_title} · p.{c.page}{c.page_end !== c.page ? `–${c.page_end}` : ""}
        </span>
      ))}
    </div>
  );
}

export default function TutorTab({ projectId }: { projectId: string }) {
  const [params] = useSearchParams();
  const [conversations, setConversations] = useState<any[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState(params.get("q") ?? "");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  // The question that failed, kept so the learner can retry without retyping it.
  const [lastFailed, setLastFailed] = useState<string | null>(null);
  const bottom = useRef<HTMLDivElement>(null);
  const abort = useRef<AbortController | null>(null);

  useEffect(() => {
    listConversations(projectId).then(setConversations).catch(() => {});
  }, [projectId]);
  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, status]);

  async function open(cid: string) {
    const data = await getConversation(projectId, cid);
    setConversationId(cid);
    setMessages(data.messages);
  }

  function newConversation() {
    setConversationId(null);
    setMessages([]);
    setError(null);
  }

  async function send(text?: string) {
    const message = (text ?? input).trim();
    if (!message || busy) return;
    setInput("");
    setBusy(true);
    setError(null);
    setLastFailed(null);
    setStatus("Searching your materials…");
    const userMsg: Message = { id: `u-${Date.now()}`, role: "user", content: message, citations: [], tool_calls: [], grounded: null, created_at: new Date().toISOString() };
    const draft: Message = { id: `a-${Date.now()}`, role: "assistant", content: "", citations: [], tool_calls: [], grounded: null, created_at: new Date().toISOString(), pending: true };
    setMessages((m) => [...m, userMsg, draft]);
    abort.current = new AbortController();
    try {
      await askTutor(projectId, { message, conversation_id: conversationId }, (event, data: any) => {
        if (event === "meta") {
          setConversationId(data.conversation_id);
          setStatus(data.has_evidence ? "Found relevant passages, composing answer…" : "No strong evidence found in your materials…");
        } else if (event === "tool") {
          setMessages((m) => m.map((x) => (x.id === draft.id ? { ...x, tool_calls: [...x.tool_calls, data] } : x)));
          setStatus(data.summary ?? `Used ${data.name}`);
        } else if (event === "delta") {
          setStatus(null);
          setMessages((m) => m.map((x) => (x.id === draft.id ? { ...x, content: x.content + data.text } : x)));
        } else if (event === "done") {
          setMessages((m) => m.map((x) => (x.id === draft.id ? { ...data.message, tool_calls: x.tool_calls, pending: false } : x)));
          listConversations(projectId).then(setConversations).catch(() => {});
        } else if (event === "error") {
          setError(data.message);
          setLastFailed(message);
          setMessages((m) => m.filter((x) => x.id !== draft.id && x.id !== userMsg.id));
        }
      }, abort.current.signal);
    } catch (err: any) {
      setError(err.message ?? "Your tutor is temporarily unavailable. Please try again in a moment.");
      setLastFailed(message);
      setMessages((m) => m.filter((x) => x.id !== draft.id && x.id !== userMsg.id));
    } finally {
      setBusy(false);
      setStatus(null);
    }
  }

  return (
    <div className="grid gap-4 lg:grid-cols-4">
      <Card className="lg:col-span-1" title="Conversations" action={<Button size="sm" variant="secondary" onClick={newConversation}>New</Button>}>
        {conversations.length === 0 ? <p className="text-sm text-slate-500">No conversations yet.</p> : (
          <ul className="space-y-1">
            {conversations.map((c) => (
              <li key={c.id}>
                <button onClick={() => open(c.id)} className={`w-full rounded-lg px-2 py-1.5 text-left text-sm hover:bg-slate-50 ${c.id === conversationId ? "bg-orange-50 text-orange-700" : ""}`}>
                  <div className="truncate">{c.title}</div>
                  <div className="text-xs text-slate-400">{c.message_count} messages · {timeAgo(c.updated_at)}</div>
                </button>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card className="flex min-h-[70vh] flex-col lg:col-span-3">
        <div className="flex-1 space-y-4 overflow-y-auto pr-1">
          {messages.length === 0 && (
            <div className="rounded-xl bg-slate-50 p-5 text-sm text-slate-600">
              <p className="font-medium text-slate-800">Your tutor answers from your materials and cites the pages it used.</p>
              <p className="mt-1">If something isn't covered, it will tell you instead of guessing. Try:</p>
              <div className="mt-3 flex flex-wrap gap-2">
                {SUGGESTIONS.map((s) => (
                  <button key={s} onClick={() => send(s)} className="rounded-full border border-slate-200 bg-white px-3 py-1 text-xs hover:border-orange-300">{s}</button>
                ))}
              </div>
            </div>
          )}
          {messages.map((m) => (
            <div key={m.id} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
              <div className={`max-w-[85%] rounded-2xl px-4 py-3 text-sm ${m.role === "user" ? "bg-orange-500 text-white" : "bg-slate-100 text-slate-800"}`}>
                {m.role === "assistant" && m.tool_calls?.length > 0 && (
                  <div className="mb-2 flex flex-wrap gap-1">
                    {m.tool_calls.map((t: any, i: number) => (
                      <Badge key={i} tone={t.status === "ok" ? "blue" : "red"}>⚙ {t.summary ?? t.name}{t.data?.quiz_session_id ? "" : ""}</Badge>
                    ))}
                  </div>
                )}
                {m.role === "assistant" ? (
                  <div className="prose prose-sm max-w-none prose-p:my-1 prose-li:my-0">
                    <ReactMarkdown>{m.content || (m.pending ? "…" : "")}</ReactMarkdown>
                  </div>
                ) : (
                  <p className="whitespace-pre-wrap">{m.content}</p>
                )}
                {m.role === "assistant" && !m.pending && (
                  <div className="mt-2 flex flex-wrap items-center gap-2">
                    {m.grounded === true && <Badge tone="green">Grounded in your materials</Badge>}
                    {m.grounded === false && <Badge tone="amber">Not supported by your materials</Badge>}
                    {m.tool_calls?.some((t: any) => t.data?.quiz_session_id) && <Link to={`/projects/${projectId}/quiz`} className="text-xs text-orange-600 underline">Open the quiz →</Link>}
                  </div>
                )}
                {m.role === "assistant" && <CitationList citations={m.citations} />}
              </div>
            </div>
          ))}
          {status && <Spinner label={status} />}
          {error && (
            <div role="alert" className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
              <p>{error}</p>
              {lastFailed && (
                <div className="mt-2 flex flex-wrap items-center gap-2">
                  <Button size="sm" variant="secondary" onClick={() => send(lastFailed)} disabled={busy}>
                    Try again
                  </Button>
                  <span className="truncate text-xs text-rose-500">“{lastFailed}”</span>
                </div>
              )}
            </div>
          )}
          <div ref={bottom} />
        </div>
        <form
          className="mt-4 flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            send();
          }}
        >
          <input className={inputClass} value={input} onChange={(e) => setInput(e.target.value)} placeholder="Ask about your materials, ask for an example, or say 'quiz me'…" disabled={busy} />
          <Button type="submit" disabled={busy || !input.trim()}>{busy ? "…" : "Send"}</Button>
        </form>
      </Card>
    </div>
  );
}
