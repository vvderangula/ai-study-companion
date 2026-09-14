import { useState } from "react";
import { admin } from "../../api";
import { Badge, Button, Card, ErrorBox, Spinner, inputClass, pct, timeAgo, useLoad } from "../../components/ui";

export default function AdminEvals() {
  const runs = useLoad(admin.evals);
  const projects = useLoad(admin.projects);
  const [projectId, setProjectId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [detail, setDetail] = useState<any | null>(null);

  async function run() {
    setBusy(true);
    setError(null);
    try {
      const d = await admin.runEval(projectId);
      setDetail(d);
      runs.refresh();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <Card title="Run the evaluation suite">
        <p className="text-sm text-slate-600">Runs the real tutor and quiz paths against a project: grounded questions (derived from its concepts), unsupported questions, prompt-injection attempts, and quiz structure/adaptivity. Scores combine rule checks with a model judge, and each run is compared with the previous run on the same project to flag regressions.</p>
        <div className="mt-3 flex flex-wrap gap-2">
          <select className={`${inputClass} max-w-md`} value={projectId} onChange={(e) => setProjectId(e.target.value)}>
            <option value="">Choose a project with processed material…</option>
            {projects.data?.filter((p) => p.materials > 0).map((p) => <option key={p.id} value={p.id}>{p.name} ({p.owner})</option>)}
          </select>
          <Button onClick={run} disabled={!projectId || busy}>{busy ? "Running (may take a minute)…" : "Run evaluation"}</Button>
        </div>
        {busy && <div className="mt-2"><Spinner label="Executing cases…" /></div>}
        <div className="mt-2"><ErrorBox message={error} /></div>
      </Card>

      <Card title="Runs">
        {runs.loading && <Spinner />}
        <table className="w-full text-sm">
          <thead className="text-left text-xs uppercase text-slate-500"><tr><th className="py-1">When</th><th>Suite</th><th>Model</th><th>Passed</th><th>Tutor grounded</th><th>Unsupported</th><th>Safety</th><th>Assessment</th><th>Regressions</th><th>Cost</th></tr></thead>
          <tbody className="divide-y divide-slate-100">
            {runs.data?.map((r) => (
              <tr key={r.id} className="cursor-pointer hover:bg-slate-50" onClick={() => admin.evalDetail(r.id).then(setDetail)}>
                <td className="py-1">{timeAgo(r.created_at)}</td><td>{r.suite}</td><td className="text-xs">{r.model}</td>
                <td>{r.passed_cases}/{r.total_cases}</td>
                <td>{pct(r.scores?.["category:tutor_grounded"])}</td><td>{pct(r.scores?.["category:tutor_unsupported"])}</td><td>{pct(r.scores?.["category:safety"])}</td><td>{pct(r.scores?.["category:assessment"])}</td>
                <td>{r.regressions?.length ? <Badge tone="red">{r.regressions.length}</Badge> : r.baseline_run_id ? <Badge tone="green">none</Badge> : <span className="text-xs text-slate-400">first run</span>}</td>
                <td>${r.cost_usd}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      {detail && (
        <Card title={`Run ${detail.run.id.slice(0, 8)} · ${detail.run.passed_cases}/${detail.run.total_cases} passed`} action={<button className="text-xs text-slate-500" onClick={() => setDetail(null)}>close</button>}>
          {detail.run.regressions?.length > 0 && <div className="mb-3 rounded-lg bg-rose-50 p-3 text-sm text-rose-700">Regressions vs previous run: {detail.run.regressions.map((r: any) => `${r.metric} ${pct(r.previous)} → ${pct(r.current)}`).join("; ")}</div>}
          <div className="mb-3 flex flex-wrap gap-1 text-xs">{Object.entries(detail.run.scores ?? {}).map(([k, v]: any) => <Badge key={k}>{k}: {pct(v)}</Badge>)}</div>
          <div className="mb-3 text-xs text-slate-500">Prompt versions: {Object.entries(detail.run.prompt_versions ?? {}).map(([k, v]) => `${k}@${v}`).join(", ")}</div>
          <ul className="divide-y divide-slate-100 text-sm">
            {detail.results.map((r: any) => (
              <li key={r.id} className="py-2">
                <div className="flex flex-wrap items-center gap-2"><Badge tone={r.passed ? "green" : "red"}>{r.passed ? "pass" : "fail"}</Badge><Badge tone="blue">{r.category}</Badge><span className="font-medium">{r.case_id}</span><span className="text-xs text-slate-500">overall {pct(r.scores?.overall)}</span></div>
                {r.input?.question && <div className="mt-1 text-slate-600">Q: {r.input.question}</div>}
                {r.output?.answer && <div className="mt-1 line-clamp-3 text-xs text-slate-500">A: {r.output.answer}</div>}
                <div className="mt-1 text-xs text-slate-400">{Object.entries(r.scores ?? {}).filter(([k]) => k !== "overall").map(([k, v]: any) => `${k} ${pct(v)}`).join(" · ")}{r.notes ? ` · ${r.notes}` : ""}</div>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}
