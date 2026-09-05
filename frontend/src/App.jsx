import { Route, Routes } from "react-router-dom";
import Footer from "./components/Footer";
import NavBar from "./components/NavBar";
import StorePage from "./pages/StorePage";
import WalSidecarPage from "./pages/WalSidecarPage";

export default function App() {
  return (
    <div className="flex min-h-screen flex-col bg-slate-50">
      <NavBar />
      <main className="flex-1">
        <Routes>
          <Route path="/" element={<StorePage />} />
          <Route path="/wal-sidecar" element={<WalSidecarPage />} />
        </Routes>
      </main>
      <Footer />
    </div>
  );
}
