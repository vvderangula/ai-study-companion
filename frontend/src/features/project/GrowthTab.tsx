import { useState } from "react";
import { Link } from "react-router-dom";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { addNote, deleteNote, getContext, getGrowth } from "../../api";
import { Badge, Button, Card, ErrorBox, Progress, Spinner, Stat, inputClass, pct, timeAgo, trendLabel, trendTone, useLoad } from "../../components/ui";

function ConceptRow({ c }: { c: any }) {
  return (
    <li className="rounded-xl border border-slate-100 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="font-medium">{c.name}</div>
        <div className="flex items-center gap-2 text-sm">
          {c.attempts > 0 && <span className="text-slate-500">{pct(c.previous)} → <span className="font-semibold text-slate-800">{pct(c.score)}</span></span>}
          <Badge tone={trendTone(c.trend)}>{trendLabel(c.trend)}</Badge>
        </div>
      </div>
      <div className="mt-2"><Progress value={c.attempts ? c.score : 0} /></div>
      <div className="mt-1 flex flex-wrap gap-3 text-xs text-slate-500">
        <span>{c.attempts} attempts</span>
        <span>confidence {pct(c.confidence)}</span>
        {c.source_pages?.length > 0 && <span>pages {c.source_pages.slice(0, 5).join(", ")}</span>}
        {c.description && <span className="basis-full text-slate-400">{c.description}</span>}
      </div>
    </li>
  );
}

export default function GrowthTab({ projectId }: { projectId: string }) {
  const { data, error, loading } = useLoad(() => getGrowth(projectId), [projectId]);
  const ctx = useLoad(() => getContext(projectId), [projectId]);
  const [note, setNote] = useState({ kind: "preference", content: "" });

  if (loading) return <Spinner label="Analysing growth…" />;
  if (error) return <ErrorBox message={error} />;
  if (!data) return null;
  const rec = data.recommendation;

  async function saveNote(e: React.FormEvent) {
    e.preventDefault();
    if (!note.content.trim()) return;
    await addNote(projectId, note);
    setNote({ ...note, content: "" });
    ctx.refresh();
  }

  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-4">
        <Stat label="Overall mastery" value={pct(data.overall_mastery)} />
        <Stat label="Improving" value={data.improving.length} tone="good" />
        <Stat label="Stable" value={data.stable.length} />
        <Stat label="Needs attention" value={data.attention.length + data.weak.filter((w: any) => w.trend !== "needs_attention").length} tone="warn" />
      </div>

      {rec && (
        <Card title="What should I do next?">
          <div className="text-lg font-semibold">{rec.title}</div>
          <p className="mt-1 text-sm text-slate-600">{rec.reason}</p>
          <Link to={`/projects/${projectId}/${rec.action === "quiz" ? "quiz" : rec.action === "tutor" ? "tutor" : "materials"}`} className="mt-3 inline-block"><Button>Do it</Button></Link>
        </Card>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Mastery over time">
          {data.timeline.length < 2 ? <p className="text-sm text-slate-500">The trend appears after a couple of learning sessions.</p> : (
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={data.timeline.map((t: any) => ({ ...t, mastery: Math.round(t.mastery * 100) }))}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                <YAxis domain={[0, 100]} tick={{ fontSize: 11 }} unit="%" />
                <Tooltip />
                <Line type="monotone" dataKey="mastery" stroke="#f97316" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          )}
        </Card>
        <Card title="Recent mastery changes">
          {data.history.length === 0 ? <p className="text-sm text-slate-500">Answer quiz questions to build a history.</p> : (
            <ul className="max-h-56 space-y-1 overflow-y-auto text-sm">
              {data.history.slice(0, 15).map((h: any) => {
                const c = data.concepts.find((x: any) => x.concept_id === h.concept_id);
                const up = h.score >= h.previous_score;
                return (
                  <li key={h.id} className="flex justify-between gap-2">
                    <span className="truncate">{c?.name ?? "concept"}</span>
                    <span className={up ? "text-emerald-600" : "text-rose-600"}>{pct(h.previous_score)} → {pct(h.score)}</span>
                    <span className="text-xs text-slate-400">{timeAgo(h.created_at)}</span>
                  </li>
                );
              })}
            </ul>
          )}
        </Card>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Needs attention / weak">
          {data.attention.length + data.weak.length === 0 ? <p className="text-sm text-slate-500">Nothing here. Nice.</p> : (
            <ul className="space-y-2">{[...new Map([...data.attention, ...data.weak].map((c: any) => [c.concept_id, c])).values()].map((c: any) => <ConceptRow key={c.concept_id} c={c} />)}</ul>
          )}
        </Card>
        <Card title="Strong">
          {data.strong.length === 0 ? <p className="text-sm text-slate-500">Concepts reach “strong” at 75% mastery.</p> : <ul className="space-y-2">{data.strong.map((c: any) => <ConceptRow key={c.concept_id} c={c} />)}</ul>}
        </Card>
      </div>

      <Card title="All concepts">
        <ul className="grid gap-2 md:grid-cols-2">{data.concepts.map((c: any) => <ConceptRow key={c.concept_id} c={c} />)}</ul>
      </Card>

      <Card title="Learning context" action={<span className="text-xs text-slate-400">You are the source of truth: edit what the companion remembers.</span>}>
        {ctx.data && (
          <div className="grid gap-6 lg:grid-cols-2">
            <div>
              <ul className="space-y-2 text-sm">
                {ctx.data.notes.length === 0 && <li className="text-slate-500">No notes yet. They are added automatically from quizzes and tutor conversations, or by you.</li>}
                {ctx.data.notes.map((n: any) => (
                  <li key={n.id} className="flex items-start justify-between gap-2 rounded-lg bg-slate-50 px-3 py-2">
                    <span><Badge>{n.kind.replace("_", " ")}</Badge> <span className="ml-1">{n.content}</span> <span className="text-xs text-slate-400">({n.source})</span></span>
                    <button className="text-xs text-slate-400 hover:text-rose-600" onClick={() => deleteNote(projectId, n.id).then(ctx.refresh)}>remove</button>
                  </li>
                ))}
              </ul>
              {ctx.data.recent_mistakes.length > 0 && (
                <div className="mt-4 text-sm">
                  <div className="font-medium">Recent mistakes the tutor is aware of</div>
                  <ul className="mt-1 list-disc pl-5 text-slate-600">{ctx.data.recent_mistakes.map((m: any) => <li key={m.id}>{m.concept_name}: {m.prompt}</li>)}</ul>
                </div>
              )}
            </div>
            <form onSubmit={saveNote} className="space-y-2">
              <div className="text-sm font-medium">Tell the companion something</div>
              <select className={inputClass} value={note.kind} onChange={(e) => setNote({ ...note, kind: e.target.value })}>
                <option value="preference">Preference (e.g. I like analogies)</option>
                <option value="goal">Goal</option>
                <option value="weakness">Something I struggle with</option>
                <option value="strength">Something I already know well</option>
              </select>
              <input className={inputClass} value={note.content} onChange={(e) => setNote({ ...note, content: e.target.value })} placeholder="e.g. Explain things with code examples where possible" maxLength={400} />
              <Button type="submit" size="sm" disabled={!note.content.trim()}>Save</Button>
              <details className="text-xs text-slate-400"><summary className="cursor-pointer">What the tutor actually receives</summary><pre className="mt-1 whitespace-pre-wrap rounded bg-slate-50 p-2">{ctx.data.prompt_block}</pre></details>
            </form>
          </div>
        )}
      </Card>
    </div>
  );
}
