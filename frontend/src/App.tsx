import { Navigate, Route, Routes } from "react-router-dom";

import Layout from "./components/Layout";
import ProtectedRoute from "./components/ProtectedRoute";
import { AuthProvider, useAuth } from "./context/AuthContext";
import AnalyticsPage from "./pages/AnalyticsPage";
import ContextPage from "./pages/ContextPage";
import HomePage from "./pages/HomePage";
import LoginPage from "./pages/LoginPage";
import ProjectPage from "./pages/ProjectPage";
import RegisterPage from "./pages/RegisterPage";
import SpacePage from "./pages/SpacePage";
import SpacesPage from "./pages/SpacesPage";
import AdminLayout from "./pages/admin/AdminLayout";
import AdminActivity from "./pages/admin/AdminActivity";
import AdminAI from "./pages/admin/AdminAI";
import AdminEvals from "./pages/admin/AdminEvals";
import AdminHealth from "./pages/admin/AdminHealth";
import AdminLearning from "./pages/admin/AdminLearning";
import AdminOverview from "./pages/admin/AdminOverview";
import AdminProjects from "./pages/admin/AdminProjects";
import AdminUserDetail from "./pages/admin/AdminUserDetail";
import AdminUsers from "./pages/admin/AdminUsers";

function AdminGate({ children }: { children: React.ReactNode }) {
  const { isAdmin } = useAuth();
  return isAdmin ? <>{children}</> : <Navigate to="/" replace />;
}

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route
          path="/"
          element={
            <ProtectedRoute>
              <Layout />
            </ProtectedRoute>
          }
        >
          <Route index element={<HomePage />} />
          <Route path="spaces" element={<SpacesPage />} />
          <Route path="spaces/:spaceId" element={<SpacePage />} />
          <Route path="projects/:projectId" element={<ProjectPage />} />
          <Route path="projects/:projectId/:tab" element={<ProjectPage />} />
          <Route path="analytics" element={<AnalyticsPage />} />
          <Route path="context" element={<ContextPage />} />
          <Route
            path="admin"
            element={
              <AdminGate>
                <AdminLayout />
              </AdminGate>
            }
          >
            <Route index element={<AdminOverview />} />
            <Route path="users" element={<AdminUsers />} />
            <Route path="users/:userId" element={<AdminUserDetail />} />
            <Route path="projects" element={<AdminProjects />} />
            <Route path="activity" element={<AdminActivity />} />
            <Route path="learning" element={<AdminLearning />} />
            <Route path="ai" element={<AdminAI />} />
            <Route path="evals" element={<AdminEvals />} />
            <Route path="health" element={<AdminHealth />} />
          </Route>
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AuthProvider>
  );
}
