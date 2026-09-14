import { useState } from "react";
import { Link } from "react-router-dom";
import { createSpace, listSpaces } from "../api";
import { Button, Card, Empty, ErrorBox, Field, Modal, Spinner, inputClass, timeAgo, useLoad, usePageTitle } from "../components/ui";

const COLORS = ["#f97316", "#0ea5e9", "#10b981", "#8b5cf6", "#ef4444", "#eab308"];
const ICONS = ["📚", "🧠", "💻", "🎯", "🎨", "🔬", "📈", "🌍"];

export default function SpacesPage() {
  usePageTitle("Spaces");
  const { data, error, loading, refresh } = useLoad(listSpaces);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ name: "", description: "", color: COLORS[0], icon: ICONS[0] });
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setFormError(null);
    try {
      await createSpace(form);
      setOpen(false);
      setForm({ name: "", description: "", color: COLORS[0], icon: ICONS[0] });
      refresh();
    } catch (err: any) {
      setFormError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Spaces</h1>
          <p className="text-sm text-slate-500">A space is a broad area you want to grow in. Projects inside it are focused journeys.</p>
        </div>
        <Button onClick={() => setOpen(true)}>New space</Button>
      </div>
      {loading && <Spinner label="Loading spaces…" />}
      <ErrorBox message={error} />
      {data && data.length === 0 && <Empty title="No spaces yet" body="Create one for a skill, subject, certification, or hobby." action={<Button onClick={() => setOpen(true)}>Create a space</Button>} />}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {data?.map((s: any) => (
          <Link key={s.id} to={`/spaces/${s.id}`}>
            <Card className="h-full transition hover:border-orange-200">
              <div className="flex items-center gap-3">
                <span className="grid h-11 w-11 place-items-center rounded-xl text-2xl" style={{ backgroundColor: `${s.color}22` }}>
                  {s.icon}
                </span>
                <div className="min-w-0">
                  <div className="truncate font-semibold">{s.name}</div>
                  <div className="text-xs text-slate-500">
                    {s.project_count} projects · {timeAgo(s.updated_at)}
                  </div>
                </div>
              </div>
              {s.description && <p className="mt-3 line-clamp-2 text-sm text-slate-600">{s.description}</p>}
            </Card>
          </Link>
        ))}
      </div>

      <Modal open={open} onClose={() => setOpen(false)} title="Create a space">
        <form onSubmit={submit} className="space-y-4">
          <Field label="Name">
            <input className={inputClass} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="e.g. Machine Learning" required maxLength={120} />
          </Field>
          <Field label="Description">
            <textarea className={inputClass} rows={2} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} placeholder="What do you want to develop here?" />
          </Field>
          <div className="grid grid-cols-2 gap-4">
            <Field label="Icon">
              <div className="flex flex-wrap gap-1">
                {ICONS.map((i) => (
                  <button type="button" key={i} onClick={() => setForm({ ...form, icon: i })} className={`h-9 w-9 rounded-lg text-lg ${form.icon === i ? "bg-orange-100 ring-2 ring-orange-400" : "bg-slate-100"}`}>
                    {i}
                  </button>
                ))}
              </div>
            </Field>
            <Field label="Colour">
              <div className="flex flex-wrap gap-2">
                {COLORS.map((c) => (
                  <button type="button" key={c} onClick={() => setForm({ ...form, color: c })} className={`h-8 w-8 rounded-full ${form.color === c ? "ring-2 ring-offset-2 ring-slate-500" : ""}`} style={{ backgroundColor: c }} />
                ))}
              </div>
            </Field>
          </div>
          <ErrorBox message={formError} />
          <div className="flex justify-end gap-2">
            <Button type="button" variant="secondary" onClick={() => setOpen(false)}>Cancel</Button>
            <Button type="submit" disabled={busy}>{busy ? "Creating…" : "Create"}</Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
