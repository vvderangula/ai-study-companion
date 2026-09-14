import { useState } from "react";
import { addGlobalNote, deleteGlobalNote, getGlobalContext } from "../api";
import { Badge, Button, Card, Empty, ErrorBox, Field, Spinner, inputClass, timeAgo, useLoad, usePageTitle } from "../components/ui";

// Labels are deliberately full sentences about the student: a Project already has
// its own "learning goal", so a bare "Goal" here would read as the same thing.
const KINDS = [
  { value: "goal", label: "What I'm working towards", hint: "Something bigger than one project — an exam, a deadline, a career step." },
  { value: "preference", label: "How I learn best", hint: "How you want things explained to you." },
];

export default function ContextPage() {
  usePageTitle("About me");
  const { data, error, loading, refresh } = useLoad(getGlobalContext);
  const [kind, setKind] = useState("preference");
  const [content, setContent] = useState("");
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (content.trim().length < 3) return;
    setBusy(true);
    setFormError(null);
    try {
      await addGlobalNote({ kind, content: content.trim() });
      setContent("");
      refresh();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Could not save that note.");
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: string) {
    await deleteGlobalNote(id);
    refresh();
  }

  if (loading) return <Spinner label="Loading your learning context…" />;
  if (error) return <ErrorBox message={error} />;
  if (!data) return null;

  const notes = (data.notes ?? []) as any[];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">About me</h1>
        <p className="text-sm text-slate-500">
          What your tutor remembers about you in every project. Your progress in a subject — weak topics, mistakes
          and materials — stays inside its own project and is never carried into another.
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1fr_20rem]">
        <Card title="What your tutor knows about you">
          {notes.length === 0 ? (
            <Empty
              title="Nothing saved yet"
              body="Tell your tutor what you're working towards or how you like things explained, and it will remember that in every project."
            />
          ) : (
            <ul className="space-y-2">
              {notes.map((n) => (
                <li key={n.id} className="flex items-start justify-between gap-3 rounded-lg border border-slate-200 px-3 py-2">
                  <div className="min-w-0">
                    <Badge tone={n.kind === "goal" ? "blue" : "orange"}>
                      {KINDS.find((k) => k.value === n.kind)?.label ?? n.kind}
                    </Badge>
                    <p className="mt-1 break-words text-sm text-slate-800">{n.content}</p>
                    <p className="mt-0.5 text-xs text-slate-400">
                      {n.source === "user" ? "added by you" : `learned by the tutor`} · {timeAgo(n.updated_at ?? n.created_at)}
                    </p>
                  </div>
                  <Button variant="ghost" size="sm" onClick={() => remove(n.id)}>
                    Remove
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <div className="space-y-6">
          <Card title="Add something about me">
            <form onSubmit={submit} className="space-y-3">
              <Field label="Type of note" hint={KINDS.find((k) => k.value === kind)?.hint}>
                <select className={inputClass} value={kind} onChange={(e) => setKind(e.target.value)}>
                  {KINDS.map((k) => (
                    <option key={k.value} value={k.value}>
                      {k.label}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Tell your tutor">
                <textarea
                  className={inputClass}
                  rows={3}
                  maxLength={400}
                  placeholder="e.g. Explain with worked examples before the theory."
                  value={content}
                  onChange={(e) => setContent(e.target.value)}
                />
              </Field>
              <ErrorBox message={formError} />
              <Button type="submit" disabled={busy || content.trim().length < 3}>
                {busy ? "Saving…" : "Save"}
              </Button>
            </form>
          </Card>

          <Card title="What your tutor sees">
            <p className="mb-2 text-xs text-slate-500">The exact wording passed to your tutor in every project.</p>
            {data.prompt_block ? (
              <pre className="whitespace-pre-wrap break-words rounded-lg bg-slate-50 p-2 text-xs text-slate-600">{data.prompt_block}</pre>
            ) : (
              <p className="text-sm text-slate-500">Nothing yet — what you save above will appear here.</p>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}
