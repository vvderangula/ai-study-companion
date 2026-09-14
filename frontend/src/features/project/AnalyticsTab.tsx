import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { getProjectAnalytics } from "../../api";
import { Badge, Card, ErrorBox, Spinner, Stat, pct, useLoad } from "../../components/ui";

export default function AnalyticsTab({ projectId }: { projectId: string }) {
  const { data, error, loading } = useLoad(() => getProjectAnalytics(projectId), [projectId]);
  if (loading) return <Spinner label="Crunching numbers…" />;
  if (error) return <ErrorBox message={error} />;
  if (!data) return null;
  const a = data.activity, p = data.performance, g = data.growth, ai = data.ai_activity;
  return (
    <div className="space-y-6">
      <Card title="Activity">
        <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-6">
          <Stat label="Active days" value={a.active_days} />
          <Stat label="Tutor questions" value={a.tutor_questions} />
          <Stat label="Quiz attempts" value={a.quiz_attempts} hint={`${a.quizzes_completed} completed`} />
          <Stat label="Questions answered" value={a.questions_answered} />
          <Stat label="Materials" value={a.materials} hint={`${a.material_interactions} interactions`} />
          <Stat label="AI requests" value={ai.total_requests} />
        </div>
        <div className="mt-4">
          <ResponsiveContainer width="100%" height={180}>
            <BarChart data={a.activity_over_time}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis dataKey="date" tick={{ fontSize: 10 }} tickFormatter={(d) => d.slice(5)} />
              <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
              <Tooltip />
              <Bar dataKey="events" fill="#f97316" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Performance">
          <div className="grid grid-cols-2 gap-3">
            <Stat label="Quiz accuracy" value={pct(p.quiz_accuracy)} />
            <Stat label="Current mastery" value={pct(p.current_mastery)} />
          </div>
          <div className="mt-4 text-sm">
            <div className="font-medium">Mastered</div>
            <div className="mt-1 flex flex-wrap gap-1">{p.concepts_mastered.length ? p.concepts_mastered.map((c: string) => <Badge key={c} tone="green">{c}</Badge>) : <span className="text-slate-500">none yet</span>}</div>
            <div className="mt-3 font-medium">Requiring attention</div>
            <div className="mt-1 flex flex-wrap gap-1">{p.concepts_attention.length ? p.concepts_attention.map((c: string) => <Badge key={c} tone="red">{c}</Badge>) : <span className="text-slate-500">none</span>}</div>
          </div>
        </Card>
        <Card title="Assessment trend">
          {g.assessment_trend.length === 0 ? <p className="text-sm text-slate-500">Complete a quiz to see your score trend.</p> : (
            <ResponsiveContainer width="100%" height={200}>
              <LineChart data={g.assessment_trend.map((t: any, i: number) => ({ ...t, n: i + 1, score: Math.round((t.score ?? 0) * 100) }))}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="n" tick={{ fontSize: 11 }} label={{ value: "quiz #", position: "insideBottomRight", fontSize: 10 }} />
                <YAxis domain={[0, 100]} unit="%" tick={{ fontSize: 11 }} />
                <Tooltip />
                <Line type="monotone" dataKey="score" stroke="#0ea5e9" strokeWidth={2} />
              </LineChart>
            </ResponsiveContainer>
          )}
        </Card>
        <Card title="Mastery over time">
          {g.mastery_over_time.length < 2 ? <p className="text-sm text-slate-500">Needs a few sessions of evidence.</p> : (
            <ResponsiveContainer width="100%" height={200}>
              <LineChart data={g.mastery_over_time.map((t: any) => ({ ...t, mastery: Math.round(t.mastery * 100) }))}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="date" tick={{ fontSize: 10 }} tickFormatter={(d) => d.slice(5)} />
                <YAxis domain={[0, 100]} unit="%" tick={{ fontSize: 11 }} />
                <Tooltip />
                <Line type="monotone" dataKey="mastery" stroke="#f97316" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          )}
        </Card>
        <Card title="AI activity">
          <div className="grid grid-cols-2 gap-3">
            <Stat label="Tutor interactions" value={ai.tutor_interactions} />
            <Stat label="Questions generated" value={ai.quiz_questions_generated} />
            <Stat label="AI evaluations" value={ai.ai_evaluations} hint="open-ended grading" />
            <Stat label="Recommendations" value={ai.recommendations_generated} />
          </div>
        </Card>
      </div>
    </div>
  );
}
