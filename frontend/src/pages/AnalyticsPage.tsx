import { Link } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { getGlobalAnalytics } from "../api";
import { Badge, Card, ErrorBox, Progress, Spinner, Stat, pct, useLoad, usePageTitle } from "../components/ui";

export default function AnalyticsPage() {
  usePageTitle("Analytics");
  const { data, error, loading } = useLoad(getGlobalAnalytics);
  if (loading) return <Spinner label="Aggregating across your projects…" />;
  if (error) return <ErrorBox message={error} />;
  if (!data) return null;
  const o = data.overall, p = data.performance, ai = data.ai_usage, t = data.trends;
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Your learning analytics</h1>
        <p className="text-sm text-slate-500">Aggregated across all spaces and projects.</p>
      </div>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Learning activity" value={o.total_activity} hint="events recorded" />
        <Stat label="Active days" value={o.active_days} />
        <Stat label="Spaces" value={o.spaces} />
        <Stat label="Projects" value={o.projects} />
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Learning performance">
          <div className="grid grid-cols-2 gap-3">
            <Stat label="Overall mastery" value={pct(p.overall_mastery)} />
            <Stat label="Avg assessment" value={pct(p.average_assessment)} />
          </div>
          <div className="mt-4 text-sm">
            <div className="font-medium">Improving</div>
            <div className="mt-1 flex flex-wrap gap-1">{p.concepts_improving.length ? p.concepts_improving.map((c: string) => <Badge key={c} tone="green">{c}</Badge>) : <span className="text-slate-500">none yet</span>}</div>
            <div className="mt-3 font-medium">Requiring attention</div>
            <div className="mt-1 flex flex-wrap gap-1">{p.concepts_attention.length ? p.concepts_attention.map((c: string) => <Badge key={c} tone="red">{c}</Badge>) : <span className="text-slate-500">none</span>}</div>
          </div>
          <ul className="mt-4 space-y-2">
            {p.per_project.map((pp: any) => (
              <li key={pp.project_id} className="text-sm">
                <div className="flex justify-between"><Link to={`/projects/${pp.project_id}`} className="hover:text-orange-600">{pp.name}</Link><span>{pct(pp.mastery)}</span></div>
                <Progress value={pp.mastery} />
              </li>
            ))}
          </ul>
        </Card>
        <Card title="AI usage">
          <div className="grid grid-cols-2 gap-3">
            <Stat label="Tutor interactions" value={ai.tutor_interactions} />
            <Stat label="Questions asked" value={ai.questions_asked} />
            <Stat label="Quiz activity" value={ai.quiz_activity} hint="sessions" />
            <Stat label="AI feedback" value={ai.ai_evaluations} hint="open answers graded" />
          </div>
        </Card>
        <Card title="Activity over time (30 days)">
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={t.activity_over_time}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis dataKey="date" tick={{ fontSize: 10 }} tickFormatter={(d) => d.slice(5)} />
              <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
              <Tooltip />
              <Bar dataKey="events" fill="#f97316" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </Card>
        <Card title="Mastery & assessment over time">
          {t.mastery_over_time.length < 2 && t.assessment_trend.length < 2 ? <p className="text-sm text-slate-500">Trends appear after a few sessions.</p> : (
            <ResponsiveContainer width="100%" height={200}>
              <LineChart data={t.mastery_over_time.map((m: any) => ({ ...m, mastery: Math.round(m.mastery * 100) }))}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="date" tick={{ fontSize: 10 }} tickFormatter={(d) => d.slice(5)} />
                <YAxis domain={[0, 100]} unit="%" tick={{ fontSize: 11 }} />
                <Tooltip />
                <Line type="monotone" dataKey="mastery" stroke="#f97316" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          )}
        </Card>
      </div>
    </div>
  );
}
