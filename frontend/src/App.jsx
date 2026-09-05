import { Route, Routes } from "react-router-dom";
import NavBar from "./components/NavBar";
import AdminPage from "./pages/AdminPage";
import StorePage from "./pages/StorePage";

export default function App() {
  return (
    <div className="min-h-screen">
      <NavBar />
      <Routes>
        <Route path="/" element={<StorePage />} />
        <Route path="/admin" element={<AdminPage />} />
      </Routes>
    </div>
  );
}
