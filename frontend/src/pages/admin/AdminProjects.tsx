import { admin } from "../../api";
import { Card, ErrorBox, Spinner, pct, timeAgo, useLoad } from "../../components/ui";

export default function AdminProjects() {
  const spaces = useLoad(admin.spaces);
  const projects = useLoad(admin.projects);
  return (
    <div className="space-y-6">
      <Card title="Spaces">
        {spaces.loading && <Spinner />}
        <ErrorBox message={spaces.error} />
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-xs uppercase text-slate-500"><tr><th className="py-2">Space</th><th>Owner</th><th>Projects</th><th>Activity</th><th>Last activity</th></tr></thead>
            <tbody className="divide-y divide-slate-100">
              {spaces.data?.map((s) => (
                <tr key={s.id}><td className="py-2 font-medium">{s.icon} {s.name}</td><td>{s.owner}</td><td>{s.projects}</td><td>{s.activity}</td><td>{s.last_activity ? timeAgo(s.last_activity) : "–"}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
      <Card title="Projects">
        {projects.loading && <Spinner />}
        <ErrorBox message={projects.error} />
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-xs uppercase text-slate-500"><tr><th className="py-2">Project</th><th>Owner</th><th>Space</th><th>Materials</th><th>Tutor</th><th>Quizzes</th><th>Progress</th><th>Last activity</th></tr></thead>
            <tbody className="divide-y divide-slate-100">
              {projects.data?.map((p) => (
                <tr key={p.id}><td className="py-2 font-medium">{p.name}</td><td>{p.owner}</td><td>{p.space}</td><td>{p.materials}</td><td>{p.tutor_activity}</td><td>{p.quiz_activity}</td><td>{pct(p.progress)}</td><td>{timeAgo(p.last_accessed_at)}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
