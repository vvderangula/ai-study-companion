import { useState } from "react";
import { admin } from "../../api";
import { Badge, Card, ErrorBox, Spinner, inputClass, timeAgo, useLoad } from "../../components/ui";

const TYPES = ["", "space_created", "project_created", "material_uploaded", "material_processed", "material_failed", "tutor_question_asked", "quiz_started", "question_answered", "quiz_completed", "mastery_updated", "recommendation_generated"];

export default function AdminActivity() {
  const [f, setF] = useState({ event_type: "", days: "7", user_id: "", project_id: "" });
  const params = Object.fromEntries(Object.entries(f).filter(([, v]) => v));
  const { data, error, loading } = useLoad(() => admin.activity({ ...params, limit: "200" }), [JSON.stringify(params)]);
  return (
    <Card title="Platform activity">
      <div className="mb-4 grid gap-2 sm:grid-cols-4">
        <select className={inputClass} value={f.event_type} onChange={(e) => setF({ ...f, event_type: e.target.value })}>{TYPES.map((t) => <option key={t} value={t}>{t || "All activity types"}</option>)}</select>
        <select className={inputClass} value={f.days} onChange={(e) => setF({ ...f, days: e.target.value })}><option value="1">Last day</option><option value="7">Last 7 days</option><option value="30">Last 30 days</option><option value="">All time</option></select>
        <input className={inputClass} placeholder="User id" value={f.user_id} onChange={(e) => setF({ ...f, user_id: e.target.value })} />
        <input className={inputClass} placeholder="Project id" value={f.project_id} onChange={(e) => setF({ ...f, project_id: e.target.value })} />
      </div>
      {loading && <Spinner />}
      <ErrorBox message={error} />
      <ul className="divide-y divide-slate-100 text-sm">
        {data?.map((e) => (
          <li key={e.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
            <div><Badge>{e.label}</Badge> <span className="ml-1">{e.ref_title}</span> <span className="text-xs text-slate-500">· {e.user_email}</span></div>
            <span className="text-xs text-slate-400">{timeAgo(e.created_at)} · project {e.project_id?.slice(0, 8) ?? "–"}</span>
          </li>
        ))}
        {data?.length === 0 && <li className="py-4 text-slate-500">No events match.</li>}
      </ul>
    </Card>
  );
}
