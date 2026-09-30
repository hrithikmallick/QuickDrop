import { Navigate, Route, Routes } from "react-router-dom";
import Dashboard from "./pages/Dashboard";
import Download from "./pages/Download";
import Login from "./pages/Login";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Dashboard />} />
      <Route path="/login" element={<Login />} />
      <Route path="/d/:token" element={<Download />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
