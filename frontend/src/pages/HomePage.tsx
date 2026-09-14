import { Link } from "react-router-dom";
import { getHome } from "../api";
import { Badge, Button, Card, Empty, ErrorBox, Progress, Spinner, Stat, pct, timeAgo, trendLabel, trendTone, useLoad, usePageTitle } from "../components/ui";
import { useAuth } from "../context/AuthContext";

const ACTION_LABEL: Record<string, string> = { quiz: "Take quiz", tutor: "Ask tutor", review: "Review", upload: "Upload" };
const ACTION_TAB: Record<string, string> = { quiz: "quiz", tutor: "tutor", review: "materials", upload: "materials" };

export default function HomePage() {
  usePageTitle("Home");
  const { user } = useAuth();
  const { data, error, loading } = useLoad(getHome);

  if (loading) return <Spinner label="Loading your workspace…" />;
  if (error) return <ErrorBox message={error} />;
  if (!data) return null;

  const cont = data.continue_learning;
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">Welcome back, {user?.full_name.split(" ")[0]}</h1>
          <p className="text-sm text-slate-500">
            {data.spaces} spaces · {data.projects} projects · overall mastery {pct(data.overall_progress)}
          </p>
        </div>
        <Link to="/spaces">
          <Button>Open spaces</Button>
        </Link>
      </div>

      {data.projects === 0 ? (
        <Empty title="Start your first learning journey" body="Create a space for a broad area, then a project for a focused goal, then upload a PDF to learn from." action={<Link to="/spaces"><Button>Create a space</Button></Link>} />
      ) : (
        <div className="grid gap-6 lg:grid-cols-3">
          <Card title="Continue learning" className="lg:col-span-2">
            {cont ? (
              <div className="flex flex-wrap items-center justify-between gap-4">
                <div>
                  <div className="text-lg font-semibold">{cont.project.name}</div>
                  <div className="text-sm text-slate-500">{cont.label} · last active {timeAgo(cont.project.last_accessed_at)}</div>
                </div>
                <Link to={`/projects/${cont.project.id}/${cont.tab}`}>
                  <Button>Continue</Button>
                </Link>
              </div>
            ) : (
              <p className="text-sm text-slate-500">No recent activity yet.</p>
            )}
          </Card>
          <Card title="Overall progress">
            <div className="text-3xl font-semibold">{pct(data.overall_progress)}</div>
            <div className="mt-2">
              <Progress value={data.overall_progress} />
            </div>
            <p className="mt-2 text-xs text-slate-500">Weighted mastery across your projects.</p>
          </Card>

          <Card title="Recommended next steps" className="lg:col-span-2">
            {data.recommendations.length === 0 ? (
              <p className="text-sm text-slate-500">Recommendations appear once a project has processed material or a completed quiz.</p>
            ) : (
              <ul className="space-y-3">
                {data.recommendations.map((r: any) => {
                  const proj = data.recent_projects.find((p: any) => p.id === r.project_id);
                  return (
                    <li key={r.id} className="flex flex-wrap items-start justify-between gap-3 rounded-xl border border-slate-100 bg-slate-50 p-4">
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <Badge tone="orange">{ACTION_LABEL[r.action] ?? r.action}</Badge>
                          <span className="text-xs text-slate-500">{proj?.name}</span>
                        </div>
                        <div className="mt-1 font-medium">{r.title}</div>
                        <p className="mt-0.5 text-sm text-slate-600">{r.reason}</p>
                      </div>
                      <Link to={`/projects/${r.project_id}/${ACTION_TAB[r.action] ?? "overview"}`}>
                        <Button size="sm" variant="secondary">Go</Button>
                      </Link>
                    </li>
                  );
                })}
              </ul>
            )}
          </Card>

          <Card title="Areas to improve">
            {data.areas_to_improve.length === 0 ? (
              <p className="text-sm text-slate-500">Nothing flagged. Take a quiz to find gaps.</p>
            ) : (
              <ul className="space-y-3">
                {data.areas_to_improve.map((a: any) => (
                  <li key={a.concept_id}>
                    <div className="flex items-center justify-between text-sm">
                      <Link to={`/projects/${a.project_id}/growth`} className="font-medium hover:text-orange-600">{a.name}</Link>
                      <Badge tone={trendTone(a.trend)}>{trendLabel(a.trend)}</Badge>
                    </div>
                    <div className="mt-1 flex items-center gap-2">
                      <Progress value={a.score} />
                      <span className="w-10 text-right text-xs text-slate-500">{pct(a.score)}</span>
                    </div>
                    <div className="text-xs text-slate-400">{a.project}</div>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card title="Recent projects" className="lg:col-span-3">
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {data.recent_projects.map((p: any) => (
                <Link key={p.id} to={`/projects/${p.id}`} className="rounded-xl border border-slate-100 p-4 transition hover:border-orange-200 hover:bg-orange-50/30">
                  <div className="font-medium">{p.name}</div>
                  <div className="mt-1 text-xs text-slate-500">
                    {p.materials} materials · {p.concepts_total} concepts · {timeAgo(p.last_accessed_at)}
                  </div>
                  <div className="mt-3 flex items-center gap-2">
                    <Progress value={p.overall_mastery} />
                    <span className="text-xs text-slate-500">{pct(p.overall_mastery)}</span>
                  </div>
                  {p.concepts_attention > 0 && <div className="mt-2 text-xs text-rose-600">{p.concepts_attention} concepts need attention</div>}
                </Link>
              ))}
            </div>
          </Card>
          <div className="hidden">
            <Stat label="" value="" />
          </div>
        </div>
      )}
    </div>
  );
}
