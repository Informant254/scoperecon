import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./lib/auth";
import { Landing } from "./pages/Landing";
import { Pricing } from "./pages/Pricing";
import { Login } from "./pages/Login";
import { Signup } from "./pages/Signup";
import { Dashboard } from "./pages/Dashboard";
import { Billing } from "./pages/Billing";
import { NewScan } from "./pages/NewScan";

function Private({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="container" style={{ padding: "4rem 0" }}>Loading…</div>;
  if (!user) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

export function App() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/pricing" element={<Pricing />} />
      <Route path="/login" element={<Login />} />
      <Route path="/signup" element={<Signup />} />
      <Route
        path="/app"
        element={
          <Private>
            <Dashboard />
          </Private>
        }
      />
      <Route
        path="/app/scan"
        element={
          <Private>
            <NewScan />
          </Private>
        }
      />
      <Route
        path="/app/billing"
        element={
          <Private>
            <Billing />
          </Private>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
