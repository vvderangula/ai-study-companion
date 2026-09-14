import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { createProject, deleteSpace, getSpace } from "../api";
import { Button, Card, Empty, ErrorBox, Field, ConfirmDialog, Modal, Progress, Spinner, Stat, inputClass, pct, timeAgo, useLoad, usePageTitle } from "../components/ui";

export default function SpacePage() {
  const { spaceId = "" } = useParams();
  const navigate = useNavigate();
  const { data, error, loading, refresh } = useLoad(() => getSpace(spaceId), [spaceId]);
  usePageTitle(data?.space?.name ?? "Space");
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ name: "", description: "", learning_goal: "" });
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setFormError(null);
    try {
      const project = await createProject({ space_id: spaceId, ...form });
      navigate(`/projects/${project.id}/materials`);
    } catch (err: any) {
      setFormError(err.message);
      setBusy(false);
    }
  }

  async function remove() {
    setDeleting(true);
    try {
      await deleteSpace(spaceId);
      navigate("/spaces");
    } finally {
      setDeleting(false);
    }
  }

  if (loading) return <Spinner label="Loading space…" />;
  if (error) return <ErrorBox message={error} />;
  if (!data) return null;
  const s = data.space;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <span className="grid h-12 w-12 place-items-center rounded-xl text-2xl" style={{ backgroundColor: `${s.color}22` }}>{s.icon}</span>
          <div>
            <div className="text-xs text-slate-500"><Link to="/spaces" className="hover:text-orange-600">Spaces</Link> / {s.name}</div>
            <h1 className="text-2xl font-bold">{s.name}</h1>
            {s.description && <p className="text-sm text-slate-500">{s.description}</p>}
          </div>
        </div>
        <div className="flex gap-2">
          <Button variant="danger" onClick={() => setConfirmOpen(true)}>Delete</Button>
          <Button onClick={() => setOpen(true)}>New project</Button>
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <Stat label="Projects" value={data.project_count} />
        <Stat label="Overall progress" value={pct(data.overall_progress)} hint="Average mastery across projects" />
        <Stat label="Needs attention" value={data.attention.reduce((n: number, a: any) => n + a.concepts.length, 0)} hint="Concepts flagged" tone={data.attention.length ? "warn" : "default"} />
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card title="Projects" className="lg:col-span-2">
          {data.projects.length === 0 ? (
            <Empty title="No projects yet" body="A project is one focused learning journey with its own materials, tutor, quizzes and mastery." action={<Button onClick={() => setOpen(true)}>Create a project</Button>} />
          ) : (
            <ul className="divide-y divide-slate-100">
              {data.projects.map((p: any) => (
                <li key={p.id} className="py-3">
                  <Link to={`/projects/${p.id}`} className="block rounded-lg px-2 py-1 hover:bg-slate-50">
                    <div className="flex items-center justify-between gap-3">
                      <div className="min-w-0">
                        <div className="truncate font-medium">{p.name}</div>
                        <div className="text-xs text-slate-500">
                          {p.materials} materials · {p.concepts_total} concepts · {timeAgo(p.last_accessed_at)}
                        </div>
                      </div>
                      <div className="w-32 shrink-0">
                        <div className="text-right text-xs text-slate-500">{pct(p.overall_mastery)}</div>
                        <Progress value={p.overall_mastery} />
                      </div>
                    </div>
                    {p.learning_goal && <div className="mt-1 text-xs text-slate-500">Goal: {p.learning_goal}</div>}
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Card>
        <div className="space-y-6">
          <Card title="Areas requiring attention">
            {data.attention.length === 0 ? <p className="text-sm text-slate-500">Nothing flagged yet.</p> : (
              <ul className="space-y-2 text-sm">
                {data.attention.map((a: any) => (
                  <li key={a.project_id}>
                    <Link to={`/projects/${a.project_id}/growth`} className="font-medium hover:text-orange-600">{a.project}</Link>
                    <div className="text-xs text-rose-600">{a.concepts.join(", ")}</div>
                  </li>
                ))}
              </ul>
            )}
          </Card>
          <Card title="Recent activity">
            {data.recent_activity.length === 0 ? <p className="text-sm text-slate-500">No activity yet.</p> : (
              <ul className="space-y-2 text-sm">
                {data.recent_activity.slice(0, 8).map((e: any) => (
                  <li key={e.id} className="flex justify-between gap-2">
                    <span className="truncate"><span className="font-medium">{e.label}</span>{e.ref_title ? ` · ${e.ref_title}` : ""}</span>
                    <span className="shrink-0 text-xs text-slate-400">{timeAgo(e.created_at)}</span>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      </div>

      <Modal open={open} onClose={() => setOpen(false)} title="Create a project">
        <form onSubmit={submit} className="space-y-4">
          <Field label="Project name">
            <input className={inputClass} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="e.g. Neural networks fundamentals" required maxLength={120} />
          </Field>
          <Field label="Description">
            <input className={inputClass} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} placeholder="What is this project about?" />
          </Field>
          <Field label="Learning goal" hint="The tutor and quizzes use this to focus on what matters to you.">
            <textarea className={inputClass} rows={2} value={form.learning_goal} onChange={(e) => setForm({ ...form, learning_goal: e.target.value })} placeholder="e.g. Be able to explain backpropagation and implement a small network from scratch." />
          </Field>
          <ErrorBox message={formError} />
          <div className="flex justify-end gap-2">
            <Button type="button" variant="secondary" onClick={() => setOpen(false)}>Cancel</Button>
            <Button type="submit" disabled={busy}>{busy ? "Creating…" : "Create project"}</Button>
          </div>
        </form>
      </Modal>
      <button className="hidden" onClick={refresh} />

      <ConfirmDialog
        open={confirmOpen}
        title="Delete this space?"
        body={`“${s.name}” and all ${data.project_count} project(s) inside it — materials, conversations, quizzes and progress — will be deleted.`}
        busy={deleting}
        onCancel={() => setConfirmOpen(false)}
        onConfirm={remove}
      />
    </div>
  );
}
