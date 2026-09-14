import { useState } from "react";
import { Link, NavLink, useNavigate, useParams } from "react-router-dom";
import { deleteProject, getProject } from "../api";
import { Button, ErrorBox, Spinner, ConfirmDialog, useLoad, usePageTitle } from "../components/ui";
import AnalyticsTab from "../features/project/AnalyticsTab";
import GrowthTab from "../features/project/GrowthTab";
import MaterialsTab from "../features/project/MaterialsTab";
import OverviewTab from "../features/project/OverviewTab";
import QuizTab from "../features/project/QuizTab";
import TutorTab from "../features/project/TutorTab";

const TABS = [
  { key: "overview", label: "Overview" },
  { key: "materials", label: "Materials" },
  { key: "tutor", label: "Tutor" },
  { key: "quiz", label: "Quiz" },
  { key: "growth", label: "Growth" },
  { key: "analytics", label: "Analytics" },
];

export default function ProjectPage() {
  const { projectId = "", tab = "overview" } = useParams();
  const navigate = useNavigate();
  const { data, error, loading, refresh } = useLoad(() => getProject(projectId), [projectId, tab]);
  // Before the early returns: hooks must run on every render.
  usePageTitle(data?.project ? `${data.project.name} · ${TABS.find((t) => t.key === tab)?.label ?? "Overview"}` : "Project");
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);

  if (loading && !data) return <Spinner label="Loading project…" />;
  if (error) return <ErrorBox message={error} />;
  if (!data) return null;
  const project = data.project;

  async function remove() {
    setDeleting(true);
    try {
      await deleteProject(projectId);
      navigate(`/spaces/${project.space_id}`);
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-xs text-slate-500">
            <Link to="/spaces" className="hover:text-orange-600">Spaces</Link> / <Link to={`/spaces/${project.space_id}`} className="hover:text-orange-600">Space</Link> / {project.name}
          </div>
          <h1 className="truncate text-2xl font-bold">{project.name}</h1>
          {project.learning_goal && <p className="text-sm text-slate-500">Goal: {project.learning_goal}</p>}
        </div>
        <Button variant="danger" size="sm" onClick={() => setConfirmOpen(true)}>Delete project</Button>
      </div>

      <nav className="flex gap-1 overflow-x-auto rounded-xl border border-slate-200 bg-white p-1">
        {TABS.map((t) => (
          <NavLink key={t.key} to={`/projects/${projectId}/${t.key}`} end className={({ isActive }) => `whitespace-nowrap rounded-lg px-3 py-1.5 text-sm font-medium ${isActive || (t.key === "overview" && tab === "overview") ? "bg-orange-500 text-white" : "text-slate-600 hover:bg-slate-100"}`}>
            {t.label}
          </NavLink>
        ))}
      </nav>

      {tab === "overview" && <OverviewTab dashboard={data} refresh={refresh} />}
      {tab === "materials" && <MaterialsTab projectId={projectId} onChange={refresh} />}
      {tab === "tutor" && <TutorTab projectId={projectId} />}
      {tab === "quiz" && <QuizTab projectId={projectId} dashboard={data} />}
      {tab === "growth" && <GrowthTab projectId={projectId} />}
      {tab === "analytics" && <AnalyticsTab projectId={projectId} />}

      <ConfirmDialog
        open={confirmOpen}
        title="Delete this project?"
        body={`“${project.name}”, its materials, conversations, quizzes and all your progress will be deleted.`}
        busy={deleting}
        onCancel={() => setConfirmOpen(false)}
        onConfirm={remove}
      />
    </div>
  );
}
