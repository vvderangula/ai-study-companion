import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { abandonQuiz, answerQuiz, getQuizSession, listQuizSessions, startQuiz, type Question } from "../../api";
import { Badge, Button, Card, ErrorBox, Progress, Spinner, inputClass, pct, timeAgo } from "../../components/ui";

const DIFF_TONE: Record<string, "green" | "amber" | "red"> = { easy: "green", medium: "amber", hard: "red" };

export default function QuizTab({ projectId, dashboard }: { projectId: string; dashboard: any }) {
  const [sessions, setSessions] = useState<any[]>([]);
  const [session, setSession] = useState<any | null>(null);
  const [question, setQuestion] = useState<Question | null>(null);
  const [result, setResult] = useState<any | null>(null);
  const [answer, setAnswer] = useState("");
  const [choice, setChoice] = useState<number | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [count, setCount] = useState(5);
  const [focus, setFocus] = useState<string>("");
  const [summary, setSummary] = useState<any | null>(null);

  const loadSessions = () => listQuizSessions(projectId).then(setSessions).catch(() => {});
  useEffect(() => {
    loadSessions();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  useEffect(() => {
    const active = sessions.find((s) => s.status === "active");
    if (active && !session) resume(active.id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessions]);

  async function resume(sid: string) {
    setBusy("Loading quiz…");
    try {
      const data = await getQuizSession(projectId, sid);
      setSession(data.session);
      setQuestion(data.question);
      setResult(null);
      setSummary(null);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(null);
    }
  }

  async function start() {
    setBusy("Preparing your first question…");
    setError(null);
    try {
      const data = await startQuiz(projectId, { question_count: count, focus_concept_id: focus || null });
      setSession(data.session);
      setQuestion(data.question);
      setResult(null);
      setSummary(null);
      loadSessions();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(null);
    }
  }

  async function submit() {
    if (!question || !session) return;
    const value = question.kind === "mcq" ? String(choice) : answer.trim();
    if ((question.kind === "mcq" && choice === null) || !value) return;
    setBusy(question.kind === "open" ? "Evaluating your answer…" : "Checking…");
    setError(null);
    try {
      const res = await answerQuiz(projectId, session.id, { question_id: question.id, answer: value });
      setResult(res);
      setSession(res.session);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(null);
    }
  }

  async function next() {
    if (!result) return;
    if (result.completed) {
      const data = await getQuizSession(projectId, session.id);
      setSummary(data);
      setSession(null);
      setQuestion(null);
      setResult(null);
      loadSessions();
      return;
    }
    if (result.next_question) {
      setQuestion(result.next_question);
    } else {
      setBusy("Generating next question…");
      const data = await getQuizSession(projectId, session.id);
      setQuestion(data.question);
      setBusy(null);
    }
    setResult(null);
    setAnswer("");
    setChoice(null);
  }

  async function quit() {
    if (!session) return;
    await abandonQuiz(projectId, session.id);
    setSession(null);
    setQuestion(null);
    setResult(null);
    loadSessions();
  }

  const concepts = dashboard.concepts ?? [];

  // ---------------- summary view
  if (summary) {
    const s = summary.session;
    return (
      <div className="space-y-6">
        <Card title="Quiz complete">
          <div className="grid gap-4 sm:grid-cols-3">
            <div className="rounded-xl bg-slate-50 p-4"><div className="text-xs text-slate-500">Score</div><div className="text-3xl font-semibold">{pct(s.score)}</div></div>
            <div className="rounded-xl bg-slate-50 p-4"><div className="text-xs text-slate-500">Correct</div><div className="text-3xl font-semibold">{s.correct}/{s.answered}</div></div>
            <div className="rounded-xl bg-slate-50 p-4"><div className="text-xs text-slate-500">Mastery updated</div><div className="text-3xl font-semibold">{new Set(summary.questions.map((q: any) => q.concept_id)).size} concepts</div></div>
          </div>
          <ul className="mt-4 divide-y divide-slate-100">
            {summary.questions.map((q: any) => (
              <li key={q.id} className="py-3 text-sm">
                <div className="flex items-start justify-between gap-2">
                  <div><Badge tone={q.is_correct ? "green" : "red"}>{q.is_correct ? "Correct" : "Incorrect"}</Badge> <span className="ml-1 text-xs text-slate-500">{q.concept_name} · {q.difficulty}</span></div>
                  <span className="text-xs text-slate-500">{pct(q.score)}</span>
                </div>
                <div className="mt-1 font-medium">{q.prompt}</div>
                <div className="mt-1 text-slate-600">{q.feedback}</div>
              </li>
            ))}
          </ul>
          <div className="mt-4 flex gap-2">
            <Link to={`/projects/${projectId}/growth`}><Button>See growth & next step</Button></Link>
            <Button variant="secondary" onClick={() => setSummary(null)}>Take another quiz</Button>
          </div>
        </Card>
      </div>
    );
  }

  // ---------------- active question view
  if (session && question) {
    const progress = session.answered / session.target_questions;
    return (
      <div className="space-y-4">
        <div className="flex items-center justify-between text-sm text-slate-500">
          <span>Question {question.ordinal + 1} of {session.target_questions}</span>
          <div className="flex items-center gap-3">
            <div className="w-40"><Progress value={progress} tone="orange" /></div>
            <Button size="sm" variant="ghost" onClick={quit}>Quit</Button>
          </div>
        </div>
        <Card>
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <Badge tone="blue">{question.kind === "mcq" ? "Multiple choice" : "Open answer"}</Badge>
            <Badge tone={DIFF_TONE[question.difficulty]}>{question.difficulty}</Badge>
            {question.concept_name && <Badge>{question.concept_name}</Badge>}
            {question.source_material && <span className="text-slate-400">based on {question.source_material}, p.{question.source_pages.join(", ")}</span>}
          </div>
          <p className="mt-3 text-lg font-medium text-slate-800">{question.prompt}</p>

          {!result && (
            <div className="mt-4 space-y-2">
              {question.kind === "mcq" ? (
                question.options.map((o, i) => (
                  <button key={i} type="button" onClick={() => setChoice(i)} className={`block w-full rounded-lg border px-4 py-2.5 text-left text-sm transition ${choice === i ? "border-orange-400 bg-orange-50" : "border-slate-200 hover:bg-slate-50"}`}>
                    <span className="mr-2 font-semibold text-slate-400">{String.fromCharCode(65 + i)}</span>{o}
                  </button>
                ))
              ) : (
                <textarea className={inputClass} rows={5} value={answer} onChange={(e) => setAnswer(e.target.value)} placeholder="Write your answer in your own words…" />
              )}
              <div className="flex items-center gap-3 pt-2">
                <Button onClick={submit} disabled={!!busy || (question.kind === "mcq" ? choice === null : !answer.trim())}>Submit answer</Button>
                {busy && <Spinner label={busy} />}
              </div>
            </div>
          )}

          {result && (
            <div className={`mt-4 rounded-xl border p-4 ${result.is_correct ? "border-emerald-200 bg-emerald-50" : "border-rose-200 bg-rose-50"}`}>
              <div className="flex items-center gap-2">
                <Badge tone={result.is_correct ? "green" : "red"}>{result.is_correct ? "Correct" : "Not quite"}</Badge>
                {question.kind === "open" && <span className="text-xs text-slate-500">score {pct(result.score)}</span>}
              </div>
              {question.kind === "mcq" && question.options.map((o, i) => (
                <div key={i} className={`mt-2 rounded-lg px-3 py-1.5 text-sm ${i === result.correct_option ? "bg-emerald-100 font-medium" : i === choice ? "bg-rose-100 line-through" : "opacity-60"}`}>{String.fromCharCode(65 + i)}. {o}</div>
              ))}
              <p className="mt-3 text-sm text-slate-700">{result.feedback}</p>
              {result.evaluation?.missing_points?.length > 0 && (
                <div className="mt-2 text-sm"><span className="font-medium">Focus on:</span><ul className="ml-4 list-disc">{result.evaluation.missing_points.map((p: string) => <li key={p}>{p}</li>)}</ul></div>
              )}
              {result.evaluation?.accuracy_issues?.length > 0 && <div className="mt-2 text-sm text-rose-700">Inaccuracies: {result.evaluation.accuracy_issues.join("; ")}</div>}
              {question.kind === "open" && result.reference_answer && <details className="mt-2 text-sm"><summary className="cursor-pointer text-slate-500">Reference answer</summary><p className="mt-1 text-slate-700">{result.reference_answer}</p></details>}
              {result.mastery && (
                <div className="mt-3 text-sm">
                  <div className="flex items-center justify-between"><span className="font-medium">{result.mastery.concept_name} mastery</span><span>{pct(result.mastery.score)}</span></div>
                  <div className="mt-1"><Progress value={result.mastery.score} /></div>
                </div>
              )}
              <div className="mt-4"><Button onClick={next}>{result.completed ? "See results" : "Next question"}</Button></div>
            </div>
          )}
          <div className="mt-3"><ErrorBox message={error} /></div>
        </Card>
      </div>
    );
  }

  // ---------------- start view
  return (
    <div className="grid gap-6 lg:grid-cols-3">
      <Card title="Start an adaptive quiz" className="lg:col-span-2">
        <p className="text-sm text-slate-600">Each question is chosen from your current mastery: weak and untested concepts come first, difficulty follows your evidence, and open-ended answers get written feedback.</p>
        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          <label className="text-sm"><span className="mb-1 block font-medium">Questions</span>
            <select className={inputClass} value={count} onChange={(e) => setCount(Number(e.target.value))}>{[3, 5, 7, 10].map((n) => <option key={n} value={n}>{n}</option>)}</select>
          </label>
          <label className="text-sm"><span className="mb-1 block font-medium">Focus (optional)</span>
            <select className={inputClass} value={focus} onChange={(e) => setFocus(e.target.value)}>
              <option value="">Let the companion choose</option>
              {concepts.map((c: any) => <option key={c.concept_id} value={c.concept_id}>{c.name} ({c.attempts ? pct(c.score) : "untested"})</option>)}
            </select>
          </label>
        </div>
        <div className="mt-4 flex items-center gap-3">
          <Button onClick={start} disabled={!!busy || concepts.length === 0}>Start quiz</Button>
          {busy && <Spinner label={busy} />}
        </div>
        {concepts.length === 0 && <p className="mt-2 text-sm text-amber-600">Upload and process a material first so there are concepts to test.</p>}
        <div className="mt-3"><ErrorBox message={error} /></div>
      </Card>
      <Card title="Past quizzes">
        {sessions.length === 0 ? <p className="text-sm text-slate-500">No quizzes yet.</p> : (
          <ul className="space-y-2 text-sm">
            {sessions.map((s) => (
              <li key={s.id} className="flex items-center justify-between">
                <div><Badge tone={s.status === "completed" ? "green" : s.status === "active" ? "amber" : "slate"}>{s.status}</Badge> <span className="ml-1 text-xs text-slate-500">{timeAgo(s.created_at)}</span></div>
                <div className="flex items-center gap-2">
                  {s.status === "completed" && <span className="font-medium">{pct(s.score)}</span>}
                  {s.status === "active" && <Button size="sm" variant="secondary" onClick={() => resume(s.id)}>Resume</Button>}
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
