import { useState } from "react";
import { Link } from "react-router-dom";
import { admin } from "../../api";
import { Badge, Card, ErrorBox, Spinner, inputClass, pct, timeAgo, useLoad } from "../../components/ui";

export default function AdminUsers() {
  const [search, setSearch] = useState("");
  const { data, error, loading } = useLoad(() => admin.users(search), [search]);
  return (
    <Card title="Users" action={<input className={`${inputClass} w-56`} placeholder="Search email…" value={search} onChange={(e) => setSearch(e.target.value)} />}>
      {loading && <Spinner />}
      <ErrorBox message={error} />
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-left text-xs uppercase text-slate-500">
            <tr><th className="py-2">User</th><th>Role</th><th>Registered</th><th>Last active</th><th>Spaces</th><th>Projects</th><th>Activity</th><th>Progress</th></tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {data?.map((u) => (
              <tr key={u.id} className="hover:bg-slate-50">
                <td className="py-2"><Link to={`/admin/users/${u.id}`} className="font-medium hover:text-orange-600">{u.full_name}</Link><div className="text-xs text-slate-500">{u.email}</div></td>
                <td><Badge tone={u.role === "admin" ? "orange" : "slate"}>{u.role}</Badge></td>
                <td>{new Date(u.created_at).toLocaleDateString()}</td>
                <td>{u.last_active_at ? timeAgo(u.last_active_at) : "never"}</td>
                <td>{u.spaces}</td><td>{u.projects}</td><td>{u.activity}</td><td>{pct(u.overall_progress)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
