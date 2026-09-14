import { useEffect, useRef, useState } from "react";
import { deleteMaterial, listMaterials, retryMaterial, uploadMaterial, type Material } from "../../api";
import { Badge, Button, Card, ConfirmDialog, Empty, ErrorBox, Spinner, timeAgo, useLoad } from "../../components/ui";

const STAGES = ["queued", "reading", "structure", "extracting", "indexing", "ready"];
const STAGE_LABEL: Record<string, string> = { queued: "Queued", reading: "Reading content", structure: "Understanding structure", extracting: "Extracting knowledge", indexing: "Creating searchable index", ready: "Ready" };

function stageIndex(m: Material) {
  if (m.status === "ready") return STAGES.length - 1;
  if (m.status === "queued") return 0;
  return Math.max(1, STAGES.indexOf(m.stage ?? "reading"));
}

export default function MaterialsTab({ projectId, onChange }: { projectId: string; onChange: () => void }) {
  const { data, error, loading, refresh, setData } = useLoad(() => listMaterials(projectId), [projectId]);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<Material | null>(null);
  const [deleting, setDeleting] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const pending = data?.some((m) => m.status === "queued" || m.status === "processing");

  useEffect(() => {
    if (!pending) return;
    const t = setInterval(async () => {
      const fresh = await listMaterials(projectId);
      setData(fresh);
      if (!fresh.some((m) => m.status === "queued" || m.status === "processing")) onChange();
    }, 2500);
    return () => clearInterval(t);
  }, [pending, projectId, setData, onChange]);

  async function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setBusy(true);
    setUploadError(null);
    try {
      await uploadMaterial(projectId, file);
      refresh();
    } catch (err: any) {
      setUploadError(err.message);
    } finally {
      setBusy(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  return (
    <div className="space-y-6">
      <Card title="Add learning material">
        <div className="flex flex-wrap items-center gap-3">
          <input ref={fileRef} type="file" accept="application/pdf" onChange={onFile} className="text-sm" disabled={busy} />
          {busy && <Spinner label="Uploading…" />}
        </div>
        <p className="mt-2 text-xs text-slate-500">PDF up to 25 MB. Text, tables and scanned pages are supported. Processing runs in the background; you can leave this page.</p>
        <div className="mt-2"><ErrorBox message={uploadError} /></div>
      </Card>

      {loading && !data && <Spinner label="Loading materials…" />}
      <ErrorBox message={error} />
      {data && data.length === 0 && <Empty title="No materials yet" body="Upload a PDF to give the tutor and quizzes a knowledge foundation." />}
      <div className="space-y-3">
        {data?.map((m) => (
          <Card key={m.id}>
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="truncate font-semibold">{m.title}</span>
                  <Badge tone={m.status === "ready" ? "green" : m.status === "failed" ? "red" : "amber"}>{m.status}</Badge>
                </div>
                <div className="text-xs text-slate-500">
                  {m.original_name} · {(m.size_bytes / 1024 / 1024).toFixed(2)} MB · uploaded {timeAgo(m.created_at)}
                  {m.status === "ready" && ` · ${m.page_count} pages · ${m.chunk_count} passages`}
                </div>
                {m.summary && <p className="mt-2 text-sm text-slate-600">{m.summary}</p>}
                {m.status === "failed" && <p className="mt-2 text-sm text-rose-600">{m.error_message ?? "Processing failed."}</p>}
                {(m.status === "queued" || m.status === "processing") && (
                  <ol className="mt-3 flex flex-wrap gap-2 text-xs">
                    {STAGES.map((s, i) => {
                      const idx = stageIndex(m);
                      const state = i < idx ? "done" : i === idx ? "current" : "todo";
                      return (
                        <li key={s} className={`rounded-full px-2 py-0.5 ${state === "done" ? "bg-emerald-50 text-emerald-700" : state === "current" ? "bg-orange-100 text-orange-700 animate-pulse" : "bg-slate-100 text-slate-400"}`}>
                          {STAGE_LABEL[s]}
                        </li>
                      );
                    })}
                  </ol>
                )}
                {m.job && m.job.attempts > 1 && <div className="mt-1 text-xs text-slate-400">attempt {m.job.attempts}/{m.job.max_attempts}</div>}
              </div>
              <div className="flex gap-2">
                {m.status === "failed" && <Button size="sm" variant="secondary" onClick={() => retryMaterial(projectId, m.id).then(refresh)}>Retry</Button>}
                <Button size="sm" variant="danger" onClick={() => setPendingDelete(m)}>Delete</Button>
              </div>
            </div>
          </Card>
        ))}
      </div>

      <ConfirmDialog
        open={pendingDelete !== null}
        title="Delete this material?"
        body={`“${pendingDelete?.title ?? ""}” will be removed, along with everything your tutor and quizzes learned from it.`}
        busy={deleting}
        onCancel={() => setPendingDelete(null)}
        onConfirm={async () => {
          if (!pendingDelete) return;
          setDeleting(true);
          try {
            await deleteMaterial(projectId, pendingDelete.id);
            setPendingDelete(null);
            refresh();
            onChange();
          } finally {
            setDeleting(false);
          }
        }}
      />
    </div>
  );
}
