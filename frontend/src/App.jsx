import { Routes, Route, Navigate } from "react-router-dom";
import Sidebar from "./components/layout/Sidebar";
import Header from "./components/layout/Header";
import TransactionsPage from "./pages/TransactionsPage";
import RulesPage from "./pages/RulesPage";
import VendorsPage from "./pages/VendorsPage";
import GLReferencePage from "./pages/GLReferencePage";

export default function App() {
  return (
    <div className="flex h-screen bg-gray-50">
      <Sidebar />
      <div className="flex flex-1 flex-col overflow-hidden">
        <Header />
        <main className="flex-1 overflow-y-auto p-6">
          <Routes>
            <Route path="/" element={<Navigate to="/transactions" replace />} />
            <Route path="/transactions" element={<TransactionsPage />} />
            <Route path="/rules" element={<RulesPage />} />
            <Route path="/vendors" element={<VendorsPage />} />
            <Route path="/gl-reference" element={<GLReferencePage />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}
