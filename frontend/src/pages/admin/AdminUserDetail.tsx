import { Link, useParams } from "react-router-dom";
import { admin } from "../../api";
import { Badge, Card, ErrorBox, Progress, Spinner, Stat, pct, timeAgo, useLoad } from "../../components/ui";

export default function AdminUserDetail() {
  const { userId = "" } = useParams();
  const { data, error, loading } = useLoad(() => admin.user(userId), [userId]);
  if (loading) return <Spinner />;
  if (error) return <ErrorBox message={error} />;
  if (!data) return null;
  const u = data.user;
  return (
    <div className="space-y-6">
      <div className="text-xs text-slate-500"><Link to="/admin/users" className="hover:text-orange-600">Users</Link> / {u.email}</div>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="User" value={u.full_name} hint={`${u.email} · ${u.role}`} />
        <Stat label="Registered" value={new Date(u.created_at).toLocaleDateString()} hint={u.last_active_at ? `last active ${timeAgo(u.last_active_at)}` : "never active"} />
        <Stat label="Quizzes completed" value={data.assessment.quizzes_completed} hint={`avg score ${pct(data.assessment.average_score)}`} />
        <Stat label="AI usage" value={data.usage.ai_requests} hint={`${data.usage.tokens} tokens · $${data.usage.cost_usd}`} />
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Learning overview">
          <div className="text-sm"><span className="font-medium">Spaces:</span> {data.spaces.map((s: any) => s.name).join(", ") || "none"}</div>
          <ul className="mt-3 space-y-3">
            {data.projects.map((p: any) => (
              <li key={p.id} className="text-sm">
                <div className="flex justify-between"><span className="font-medium">{p.name}</span><span>{pct(p.mastery)}</span></div>
                <div className="text-xs text-slate-500">{p.materials} materials · {p.concepts} concepts · {timeAgo(p.last_accessed_at)}</div>
                <Progress value={p.mastery} />
              </li>
            ))}
          </ul>
          <div className="mt-4 grid grid-cols-3 gap-2 text-center text-xs">
            <div className="rounded bg-slate-50 p-2"><div className="text-lg font-semibold">{data.usage.tutor}</div>tutor</div>
            <div className="rounded bg-slate-50 p-2"><div className="text-lg font-semibold">{data.usage.quiz}</div>quiz AI</div>
            <div className="rounded bg-slate-50 p-2"><div className="text-lg font-semibold">{data.usage.sessions}</div>sessions</div>
          </div>
        </Card>
        <Card title="Activity timeline">
          <ul className="max-h-[28rem] space-y-2 overflow-y-auto text-sm">
            {data.timeline.map((e: any) => (
              <li key={e.id} className="flex justify-between gap-2 border-l-2 border-slate-200 pl-3">
                <span><Badge>{e.label}</Badge> <span className="ml-1 text-slate-600">{e.ref_title}</span></span>
                <span className="shrink-0 text-xs text-slate-400">{timeAgo(e.created_at)}</span>
              </li>
            ))}
          </ul>
        </Card>
      </div>
    </div>
  );
}
