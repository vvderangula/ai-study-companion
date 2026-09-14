import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { admin } from "../../api";
import { Card, ErrorBox, Spinner, Stat, pct, useLoad } from "../../components/ui";

export default function AdminLearning() {
  const { data, error, loading } = useLoad(admin.learning);
  if (loading) return <Spinner />;
  if (error) return <ErrorBox message={error} />;
  if (!data) return null;
  return (
    <div className="space-y-6">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Users active (7d)" value={data.engagement.users_active_7d} hint={`${data.engagement.avg_events_per_active_user} events / active user`} />
        <Stat label="Active projects (7d)" value={data.active_projects_7d} />
        <Stat label="Quizzes completed" value={data.assessment.quizzes_completed} hint={`avg score ${pct(data.assessment.average_score)}`} />
        <Stat label="Average mastery" value={pct(data.average_mastery)} />
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Learning activity (30 days)">
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={data.activity_over_time}><CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" /><XAxis dataKey="date" tick={{ fontSize: 10 }} tickFormatter={(d) => d.slice(5)} /><YAxis allowDecimals={false} tick={{ fontSize: 11 }} /><Tooltip /><Bar dataKey="events" fill="#0f172a" radius={[4, 4, 0, 0]} /></BarChart>
          </ResponsiveContainer>
        </Card>
        <Card title="Most used features (30 days)">
          <ul className="space-y-2 text-sm">{data.features.map((f: any) => <li key={f.feature} className="flex justify-between"><span>{f.feature}</span><span className="font-medium">{f.count}</span></li>)}</ul>
        </Card>
        <Card title="Where learners commonly struggle">
          {data.common_struggles.length === 0 ? <p className="text-sm text-slate-500">No weak concepts recorded yet.</p> : <ul className="space-y-2 text-sm">{data.common_struggles.map((s: any) => <li key={s.concept} className="flex justify-between"><span>{s.concept}</span><span className="text-rose-600">{s.count} learners</span></li>)}</ul>}
        </Card>
      </div>
    </div>
  );
}
