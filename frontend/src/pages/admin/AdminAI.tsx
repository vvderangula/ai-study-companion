import { useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { admin } from "../../api";
import { Badge, Card, ErrorBox, Spinner, Stat, pct, timeAgo, useLoad } from "../../components/ui";

export default function AdminAI() {
  const { data, error, loading } = useLoad(() => admin.ai(14));
  const prompts = useLoad(admin.prompts);
  const [detail, setDetail] = useState<any | null>(null);
  if (loading) return <Spinner />;
  if (error) return <ErrorBox message={error} />;
  if (!data) return null;
  const t = data.totals;
  return (
    <div className="space-y-6">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Requests (14d)" value={t.requests} hint={`${t.fallbacks} used fallback provider`} />
        <Stat label="Errors" value={t.errors} tone={t.errors ? "bad" : "good"} hint={`${pct(t.requests ? t.errors / t.requests : 0)} error rate`} />
        <Stat label="Latency" value={`${t.avg_latency_ms} ms`} hint={`p95 ${t.p95_latency_ms} ms`} />
        <Stat label="Estimated cost" value={`$${t.cost_usd}`} hint={`${t.tokens_in.toLocaleString()} in · ${t.tokens_out.toLocaleString()} out tokens`} />
      </div>
      <div className="grid gap-6 lg:grid-cols-3">
        <Card title="By feature" className="lg:col-span-2">
          <table className="w-full text-sm">
            <thead className="text-left text-xs uppercase text-slate-500"><tr><th className="py-1">Feature</th><th>Requests</th><th>Errors</th><th>Fallbacks</th><th>Avg ms</th><th>Tokens</th><th>Cost</th></tr></thead>
            <tbody className="divide-y divide-slate-100">{data.by_feature.map((f: any) => <tr key={f.feature}><td className="py-1 font-medium">{f.feature}</td><td>{f.requests}</td><td className={f.errors ? "text-rose-600" : ""}>{f.errors}</td><td>{f.fallbacks}</td><td>{f.avg_latency_ms}</td><td>{(f.tokens_in + f.tokens_out).toLocaleString()}</td><td>${f.cost}</td></tr>)}</tbody>
          </table>
        </Card>
        <Card title="Models & providers">
          <ul className="space-y-1 text-sm">{data.by_provider.map((p: any) => <li key={p.provider} className="flex justify-between"><Badge tone="blue">{p.provider}</Badge><span>{p.requests}</span></li>)}</ul>
          <ul className="mt-3 space-y-1 text-xs text-slate-600">{data.by_model.map((m: any) => <li key={m.model} className="flex justify-between"><span className="truncate">{m.model}</span><span>{m.requests}</span></li>)}</ul>
        </Card>
        <Card title="Requests & cost per day" className="lg:col-span-3">
          <ResponsiveContainer width="100%" height={180}>
            <BarChart data={data.by_day}><CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" /><XAxis dataKey="date" tick={{ fontSize: 10 }} tickFormatter={(d) => d.slice(5)} /><YAxis allowDecimals={false} tick={{ fontSize: 11 }} /><Tooltip /><Bar dataKey="requests" fill="#0ea5e9" radius={[4, 4, 0, 0]} /><Bar dataKey="errors" fill="#ef4444" radius={[4, 4, 0, 0]} /></BarChart>
          </ResponsiveContainer>
        </Card>
        <Card title="Recent requests (click to inspect)" className="lg:col-span-2">
          <ul className="max-h-96 divide-y divide-slate-100 overflow-y-auto text-xs">
            {data.recent_requests.map((r: any) => (
              <li key={r.id} className="cursor-pointer py-1.5 hover:bg-slate-50" onClick={() => admin.aiRequest(r.id).then(setDetail)}>
                <div className="flex justify-between"><span><Badge tone={r.status === "ok" ? "green" : r.status === "fallback" ? "amber" : "red"}>{r.status}</Badge> <span className="ml-1 font-medium">{r.feature}</span> · {r.prompt_name}@{r.prompt_version} · {r.provider}/{r.model}</span><span className="text-slate-400">{r.latency_ms} ms · {timeAgo(r.created_at)}</span></div>
              </li>
            ))}
          </ul>
        </Card>
        <Card title="Prompt registry">
          <ul className="space-y-2 text-xs">{prompts.data?.map((p) => <li key={p.name}><span className="font-medium">{p.name}</span> <Badge>v{p.version}</Badge><div className="text-slate-500">{p.responsibility}</div></li>)}</ul>
        </Card>
        {data.recent_errors.length > 0 && (
          <Card title="Recent AI errors" className="lg:col-span-3">
            <ul className="space-y-1 text-xs">{data.recent_errors.map((r: any) => <li key={r.id}><span className="font-medium">{r.feature}</span> · {timeAgo(r.created_at)} · <span className="text-rose-600">{r.error}</span></li>)}</ul>
          </Card>
        )}
      </div>
      {detail && (
        <Card title={`Request ${detail.id.slice(0, 8)}`} action={<button className="text-xs text-slate-500" onClick={() => setDetail(null)}>close</button>}>
          <pre className="max-h-96 overflow-auto rounded bg-slate-50 p-3 text-xs">{JSON.stringify(detail, null, 2)}</pre>
        </Card>
      )}
    </div>
  );
}
