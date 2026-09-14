import { admin } from "../../api";
import { Badge, Card, ErrorBox, Spinner, Stat, pct, timeAgo, useLoad } from "../../components/ui";

function Light({ ok, label }: { ok: boolean; label: string }) {
  return <div className="flex items-center gap-2 text-sm"><span className={`h-2.5 w-2.5 rounded-full ${ok ? "bg-emerald-500" : "bg-rose-500"}`} />{label}</div>;
}

export default function AdminHealth() {
  const { data, error, loading, refresh } = useLoad(admin.health);
  if (loading) return <Spinner />;
  if (error) return <ErrorBox message={error} />;
  if (!data) return null;
  return (
    <div className="space-y-6">
      <div className="grid gap-6 lg:grid-cols-3">
        <Card title="Services" action={<button className="text-xs text-slate-500" onClick={refresh}>refresh</button>}>
          <div className="space-y-2">
            <Light ok={data.api.ok} label={`API (${data.api.environment})`} />
            <Light ok={data.database.ok} label={`MongoDB ${data.database.ping_ms !== null ? `· ping ${data.database.ping_ms} ms` : "unreachable"}`} />
            {data.ai_providers.map((p: any) => <Light key={p.name} ok={p.configured} label={`AI provider: ${p.name} ${p.configured ? "" : "(no key configured)"} · ${p.models.primary}`} />)}
            <Light ok label={`Embeddings: ${data.embeddings.backend} (${data.embeddings.model})`} />
          </div>
        </Card>
        <Card title="AI (last 24h)">
          <div className="grid grid-cols-2 gap-2">
            <Stat label="Requests" value={data.ai_last_24h.requests} />
            <Stat label="Error rate" value={pct(data.ai_last_24h.error_rate)} tone={data.ai_last_24h.error_rate > 0.05 ? "bad" : "good"} />
            <Stat label="Avg latency" value={`${data.ai_last_24h.avg_latency_ms} ms`} />
            <Stat label="Errors" value={data.ai_last_24h.errors} />
          </div>
        </Card>
        <Card title="Background processing">
          <div className="grid grid-cols-2 gap-2">
            <Stat label="Queued" value={data.background.queued} />
            <Stat label="Running" value={data.background.running} />
            <Stat label="Failed" value={data.background.failed} tone={data.background.failed ? "warn" : "default"} />
            <Stat label="Backlog" value={data.background.backlog} hint="materials not yet ready" />
          </div>
          <div className="mt-2 text-xs text-slate-500">backend: {data.background.backend} · completed {data.background.completed}</div>
        </Card>
      </div>
      <Card title="Recent job failures">
        {data.background.recent_failures.length === 0 ? <p className="text-sm text-slate-500">No failed jobs.</p> : (
          <ul className="space-y-2 text-xs">{data.background.recent_failures.map((j: any) => <li key={j.id}><Badge tone="red">{j.kind}</Badge> stage {j.stage ?? "–"} · attempts {j.attempts}/{j.max_attempts} · {timeAgo(j.created_at)}<pre className="mt-1 whitespace-pre-wrap rounded bg-slate-50 p-2 text-[11px] text-slate-600">{j.error?.slice(0, 400)}</pre></li>)}</ul>
        )}
      </Card>
    </div>
  );
}
