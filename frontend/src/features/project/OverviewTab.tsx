import { useState } from "react";
import { Link } from "react-router-dom";
import { generateRecommendation, updateRecommendation } from "../../api";
import { Badge, Button, Card, Progress, Stat, pct, timeAgo, trendLabel, trendTone } from "../../components/ui";

const ACTION_TAB: Record<string, string> = { quiz: "quiz", tutor: "tutor", review: "materials", upload: "materials" };
const ACTION_LABEL: Record<string, string> = { quiz: "Take a quiz", tutor: "Ask the tutor", review: "Review material", upload: "Upload material" };

export default function OverviewTab({ dashboard, refresh }: { dashboard: any; refresh: () => void }) {
  const p = dashboard.progress;
  const rec = dashboard.recommendation;
  const ctx = dashboard.learning_context;
  const pid = dashboard.project.id;
  const [busy, setBusy] = useState(false);

  async function regenerate() {
    setBusy(true);
    try {
      await generateRecommendation(pid);
      refresh();
    } finally {
      setBusy(false);
    }
  }
  async function mark(status: "done" | "dismissed") {
    await updateRecommendation(pid, rec.id, status);
    refresh();
  }

  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Overall mastery" value={pct(p.overall_mastery)} hint={`${p.concepts_assessed}/${p.concepts_total} concepts assessed`} />
        <Stat label="Quiz accuracy" value={pct(p.quiz_accuracy)} hint={`${dashboard.performance.questions_answered} questions answered`} />
        <Stat label="Strong concepts" value={p.concepts_strong} tone="good" />
        <Stat label="Needs attention" value={p.concepts_attention} tone={p.concepts_attention ? "warn" : "default"} />
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card title="Recommended next step" className="lg:col-span-2" action={<Button size="sm" variant="ghost" onClick={regenerate} disabled={busy}>{busy ? "Thinking…" : "Refresh"}</Button>}>
          {rec ? (
            <div>
              <div className="flex items-center gap-2">
                <Badge tone="orange">{ACTION_LABEL[rec.action] ?? rec.action}</Badge>
                <span className="text-xs text-slate-400">triggered by {rec.trigger.replace("_", " ")} · {timeAgo(rec.created_at)}</span>
              </div>
              <div className="mt-2 text-lg font-semibold">{rec.title}</div>
              <p className="mt-1 text-sm text-slate-600">{rec.reason}</p>
              {rec.concept_names?.length > 0 && <div className="mt-2 flex flex-wrap gap-1">{rec.concept_names.map((n: string) => <Badge key={n}>{n}</Badge>)}</div>}
              <div className="mt-4 flex flex-wrap gap-2">
                <Link to={`/projects/${pid}/${ACTION_TAB[rec.action] ?? "overview"}${rec.action === "tutor" && rec.payload?.suggested_prompt ? `?q=${encodeURIComponent(rec.payload.suggested_prompt)}` : ""}`}>
                  <Button>{ACTION_LABEL[rec.action] ?? "Go"}</Button>
                </Link>
                <Button variant="secondary" onClick={() => mark("done")}>Done</Button>
                <Button variant="ghost" onClick={() => mark("dismissed")}>Dismiss</Button>
              </div>
            </div>
          ) : (
            <p className="text-sm text-slate-500">Upload and process a material to get your first recommendation.</p>
          )}
        </Card>

        <Card title="Continue learning">
          <div className="font-medium">{dashboard.continue_learning.label}</div>
          <Link to={`/projects/${pid}/${dashboard.continue_learning.tab}`} className="mt-3 inline-block">
            <Button variant="secondary">Continue</Button>
          </Link>
          <div className="mt-4 grid grid-cols-2 gap-2 text-sm">
            <Link to={`/projects/${pid}/tutor`} className="rounded-lg border border-slate-200 px-3 py-2 text-center hover:bg-slate-50">Ask tutor</Link>
            <Link to={`/projects/${pid}/quiz`} className="rounded-lg border border-slate-200 px-3 py-2 text-center hover:bg-slate-50">Take quiz</Link>
            <Link to={`/projects/${pid}/materials`} className="rounded-lg border border-slate-200 px-3 py-2 text-center hover:bg-slate-50">Materials</Link>
            <Link to={`/projects/${pid}/growth`} className="rounded-lg border border-slate-200 px-3 py-2 text-center hover:bg-slate-50">Growth</Link>
          </div>
        </Card>

        <Card title="Concepts" className="lg:col-span-2">
          {dashboard.concepts.length === 0 ? (
            <p className="text-sm text-slate-500">Concepts are extracted automatically when a material finishes processing.</p>
          ) : (
            <ul className="space-y-3">
              {dashboard.concepts.map((c: any) => (
                <li key={c.concept_id}>
                  <div className="flex items-center justify-between gap-2 text-sm">
                    <span className="font-medium" title={c.description}>{c.name}</span>
                    <div className="flex items-center gap-2">
                      <Badge tone={trendTone(c.trend)}>{trendLabel(c.trend)}</Badge>
                      <span className="w-10 text-right text-xs text-slate-500">{c.attempts ? pct(c.score) : "–"}</span>
                    </div>
                  </div>
                  <div className="mt-1"><Progress value={c.attempts ? c.score : 0} /></div>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <div className="space-y-6">
          <Card title="What the companion knows about you">
            {ctx.goal && <p className="text-sm"><span className="font-medium">Goal:</span> {ctx.goal}</p>}
            {ctx.weak.length > 0 && <p className="mt-2 text-sm"><span className="font-medium text-rose-600">Weak:</span> {ctx.weak.map((w: any) => w.name).join(", ")}</p>}
            {ctx.strong.length > 0 && <p className="mt-1 text-sm"><span className="font-medium text-emerald-600">Strong:</span> {ctx.strong.map((w: any) => w.name).join(", ")}</p>}
            {ctx.notes.length > 0 && (
              <ul className="mt-2 space-y-1 text-sm text-slate-600">
                {ctx.notes.slice(0, 5).map((n: any) => (
                  <li key={n.id}><Badge>{n.kind.replace("_", " ")}</Badge> {n.content}</li>
                ))}
              </ul>
            )}
            {!ctx.goal && ctx.weak.length === 0 && ctx.strong.length === 0 && ctx.notes.length === 0 && <p className="text-sm text-slate-500">Context builds up as you learn: goals, preferences, strengths and persistent difficulties.</p>}
            <Link to={`/projects/${pid}/growth`} className="mt-3 inline-block text-xs text-orange-600 hover:underline">Manage context →</Link>
          </Card>
          <Card title="Recent activity">
            {dashboard.recent_activity.length === 0 ? <p className="text-sm text-slate-500">No activity yet.</p> : (
              <ul className="space-y-2 text-sm">
                {dashboard.recent_activity.slice(0, 8).map((e: any) => (
                  <li key={e.id} className="flex justify-between gap-2">
                    <span className="truncate"><span className="font-medium">{e.label}</span>{e.ref_title ? ` · ${e.ref_title}` : ""}</span>
                    <span className="shrink-0 text-xs text-slate-400">{timeAgo(e.created_at)}</span>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}
