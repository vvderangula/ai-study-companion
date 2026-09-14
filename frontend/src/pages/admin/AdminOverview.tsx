import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { admin } from "../../api";
import { Card, ErrorBox, Spinner, Stat, pct, useLoad } from "../../components/ui";

export default function AdminOverview() {
  const { data, error, loading } = useLoad(admin.overview);
  if (loading) return <Spinner label="Loading platform snapshot…" />;
  if (error) return <ErrorBox message={error} />;
  if (!data) return null;
  return (
    <div className="space-y-6">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Total users" value={data.users.total} hint={`${data.users.active_7d} active in 7d · ${data.users.active_1d} today`} />
        <Stat label="Spaces / projects" value={`${data.spaces} / ${data.projects}`} />
        <Stat label="Materials" value={data.materials.total} hint={`${data.materials.ready} ready · ${data.materials.failed} failed`} tone={data.materials.failed ? "warn" : "default"} />
        <Stat label="Learning activity (7d)" value={data.activity_7d} hint={`${data.tutor_questions_7d} tutor · ${data.quizzes_7d} quizzes`} />
        <Stat label="AI requests (7d)" value={data.ai.requests_7d} hint={`$${data.ai.cost_7d} est. cost`} />
        <Stat label="AI error rate" value={pct(data.ai.error_rate)} tone={data.ai.error_rate > 0.05 ? "bad" : "good"} />
        <Stat label="Avg AI latency" value={`${data.ai.avg_latency_ms} ms`} />
        <Stat label="Background jobs" value={`${data.jobs.running} running`} hint={`${data.jobs.queued} queued · ${data.jobs.failed} failed · ${data.jobs.completed} done`} tone={data.jobs.failed ? "warn" : "default"} />
      </div>
      <Card title="Platform activity (14 days)">
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={data.activity_over_time}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
            <XAxis dataKey="date" tick={{ fontSize: 10 }} tickFormatter={(d) => d.slice(5)} />
            <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
            <Tooltip />
            <Bar dataKey="events" fill="#0f172a" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </Card>
    </div>
  );
}
