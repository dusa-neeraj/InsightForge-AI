import { lazy, Suspense, useEffect, useRef, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { getChatHistory, getSqlSchema, sendChat } from "../api/client.js";
import DataTable from "../components/DataTable.jsx";
import Notice from "../components/Notice.jsx";
import { Badge, PageHeader, Spinner } from "../components/ui.jsx";
import { useAsync } from "../hooks/useAsync.js";

// Plotly is large, so it is only downloaded when an answer includes a chart
const PlotlyChart = lazy(() => import("../components/PlotlyChart.jsx"));

const MAX_LENGTH = 500;
const SOURCE_LABEL = { ai: "AI planner", rules: "Keyword planner" };
const STATUS_TITLE = { unsupported: "I can't answer that yet", error: "I couldn't run that" };

const storageKey = (datasetId) => `ada.chat.${datasetId}`;

function loadSession(datasetId) {
  try {
    return localStorage.getItem(storageKey(datasetId));
  } catch {
    return null;
  }
}

function saveSession(datasetId, sessionId) {
  try {
    if (sessionId) localStorage.setItem(storageKey(datasetId), sessionId);
    else localStorage.removeItem(storageKey(datasetId));
  } catch {
    // storage is blocked, the chat still works for this visit
  }
}

function starterQuestions(columns) {
  const isId = (name) => /(^|_)id$/.test(name);
  const text = (name) => name.replace(/_/g, " ");
  const number = columns.find((c) => c.kind === "numeric" && !isId(c.name));
  const category = columns.find((c) => c.kind === "categorical");
  const hasDate = columns.some((c) => c.kind === "date");
  const ideas = [];
  if (number && category) ideas.push(`Which ${text(category.name)} has the highest ${text(number.name)}?`);
  if (number && hasDate) ideas.push(`What is the monthly trend of ${text(number.name)}?`);
  if (number) ideas.push(`What is the average ${text(number.name)}?`);
  ideas.push("How many rows are there?");
  return ideas.slice(0, 4);
}

function UserBubble({ text }) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-sm bg-indigo-600 px-4 py-2 text-sm text-white">
        {text}
      </div>
    </div>
  );
}

function AssistantBubble({ message, onAsk }) {
  if (message.error) {
    return (
      <div className="max-w-[92%]">
        <Notice tone="red" title="Request failed">
          {message.error}
        </Notice>
      </div>
    );
  }
  const { reply } = message;
  const result = reply.result;
  const failed = reply.status !== "ok";
  const showTable =
    result && result.kind !== "scalar" && result.columns?.length > 0 && result.rows?.length > 0;

  return (
    <div className="max-w-[92%] space-y-3">
      <div
        className={`rounded-2xl rounded-bl-sm border px-4 py-3 ${
          failed ? "border-amber-200 bg-amber-50" : "border-slate-200 bg-white shadow-sm"
        }`}
      >
        {failed && (
          <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-amber-700">
            {STATUS_TITLE[reply.status] || "Problem"}
          </p>
        )}
        <p className="whitespace-pre-wrap text-sm leading-6 text-slate-800">{reply.answer}</p>
      </div>

      {result?.chart && (
        <div className="rounded-xl border border-slate-200 bg-white p-3">
          <Suspense fallback={<Spinner label="Loading chart..." />}>
            <PlotlyChart figure={result.chart.figure} label={result.chart.title} height={300} />
          </Suspense>
        </div>
      )}

      {showTable && (
        <div className="overflow-hidden rounded-xl border border-slate-200 bg-white">
          <DataTable columns={result.columns} rows={result.rows} maxRows={10} height="max-h-64" />
        </div>
      )}

      {(reply.method?.length > 0 || reply.note) && (
        <details className="rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm">
          <summary className="cursor-pointer text-xs font-medium text-indigo-600">
            How this was calculated
          </summary>
          {reply.method?.length > 0 && (
            <ol className="mt-2 list-decimal space-y-1 pl-5 text-slate-700">
              {reply.method.map((step, i) => (
                <li key={i}>{step}</li>
              ))}
            </ol>
          )}
          <div className="mt-2 flex flex-wrap items-center gap-2">
            {reply.source && <Badge>{SOURCE_LABEL[reply.source]}</Badge>}
            {reply.note && <span className="text-xs text-slate-500">{reply.note}</span>}
          </div>
        </details>
      )}

      {reply.suggestions?.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {reply.suggestions.map((text) => (
            <button
              key={text}
              onClick={() => onAsk(text)}
              className="rounded-full border border-slate-200 bg-white px-3 py-1 text-xs text-slate-700 hover:border-indigo-300 hover:bg-indigo-50"
            >
              {text}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function Typing() {
  return (
    <div className="flex gap-1 px-2 py-3" role="status" aria-label="Thinking">
      {[0, 150, 300].map((delay) => (
        <span
          key={delay}
          className="h-2 w-2 animate-bounce rounded-full bg-slate-300"
          style={{ animationDelay: `${delay}ms` }}
        />
      ))}
    </div>
  );
}

function Conversation({ datasetId }) {
  const location = useLocation();
  const navigate = useNavigate();
  const schema = useAsync(() => getSqlSchema(datasetId), [datasetId]);
  const [messages, setMessages] = useState([]);
  const [sessionId, setSessionId] = useState(() => loadSession(datasetId));
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const endRef = useRef(null);
  const initialQuestion = useRef(location.state?.question);

  async function send(question) {
    const text = question.trim();
    if (!text || sending) return;
    setInput("");
    setMessages((current) => [...current, { role: "user", text }]);
    setSending(true);
    try {
      const reply = await sendChat(datasetId, text, sessionId);
      setSessionId(reply.session_id);
      saveSession(datasetId, reply.session_id);
      setMessages((current) => [...current, { role: "assistant", reply }]);
    } catch (err) {
      setMessages((current) => [...current, { role: "assistant", error: err.message }]);
    } finally {
      setSending(false);
    }
  }

  // Bring back the earlier conversation after a refresh
  useEffect(() => {
    if (initialQuestion.current || !sessionId) return undefined;
    let cancelled = false;
    getChatHistory(datasetId, sessionId)
      .then((data) => {
        if (cancelled) return;
        const restored = data.turns.flatMap((turn) => [
          { role: "user", text: turn.question },
          {
            role: "assistant",
            reply: {
              answer: turn.answer,
              status: turn.status,
              method: [],
              suggestions: [],
              result: null,
              source: null,
              note: null,
            },
          },
        ]);
        setMessages((current) => (current.length ? current : restored));
      })
      .catch(() => saveSession(datasetId, null)); // the saved session no longer exists
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // A question sent from the Insights page ("Questions to explore")
  useEffect(() => {
    const question = initialQuestion.current;
    if (!question) return;
    initialQuestion.current = null;
    navigate(location.pathname, { replace: true, state: null });
    send(question);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, sending]);

  function reset() {
    setMessages([]);
    setSessionId(null);
    saveSession(datasetId, null);
  }

  const starters = schema.data ? starterQuestions(schema.data.columns) : [];

  return (
    <div className="flex h-[calc(100dvh-9rem)] min-h-[440px] flex-col">
      <PageHeader
        title="Ask your data"
        subtitle="Ask in plain English. Every answer is calculated from your data."
        actions={
          messages.length > 0 && (
            <button
              onClick={reset}
              className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 hover:bg-slate-50"
            >
              New conversation
            </button>
          )
        }
      />

      <div className="flex-1 space-y-4 overflow-y-auto rounded-2xl border border-slate-200 bg-slate-50 p-4">
        {messages.length === 0 && !sending && (
          <div className="py-8 text-center">
            <p className="text-sm text-slate-500">Try one of these, or type your own question.</p>
            <div className="mt-4 flex flex-wrap justify-center gap-2">
              {starters.map((text) => (
                <button
                  key={text}
                  onClick={() => send(text)}
                  className="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-sm text-slate-700 hover:border-indigo-300 hover:bg-indigo-50"
                >
                  {text}
                </button>
              ))}
            </div>
          </div>
        )}
        {messages.map((message, i) =>
          message.role === "user" ? (
            <UserBubble key={i} text={message.text} />
          ) : (
            <AssistantBubble key={i} message={message} onAsk={send} />
          )
        )}
        {sending && <Typing />}
        <div ref={endRef} />
      </div>

      <div className="mt-3 flex items-end gap-2">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value.slice(0, MAX_LENGTH))}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              send(input);
            }
          }}
          rows={1}
          placeholder="Ask a question about your data..."
          className="max-h-32 min-h-[44px] flex-1 resize-none rounded-xl border border-slate-300 bg-white px-3 py-2.5 text-sm"
        />
        <button
          onClick={() => send(input)}
          disabled={sending || !input.trim()}
          className="rounded-xl bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          Send
        </button>
      </div>
      <p className="mt-1 text-right text-xs text-slate-400">
        {input.length}/{MAX_LENGTH}
      </p>
    </div>
  );
}

// The key makes React start a fresh conversation when you switch datasets
export default function Chat() {
  const { datasetId } = useParams();
  return <Conversation key={datasetId} datasetId={datasetId} />;
}