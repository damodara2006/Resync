import { HardDriveDownload, LayoutDashboard, ShoppingBag } from "lucide-react";
import { NavLink } from "react-router-dom";

const linkClass = ({ isActive }) =>
  `flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition ${
    isActive ? "bg-indigo-600 text-white" : "text-gray-400 hover:text-white"
  }`;

export default function NavBar() {
  return (
    <nav className="sticky top-0 z-10 border-b border-white/10 bg-[#0b0f14]/80 backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
        <span className="text-lg font-bold text-white">
          Re<span className="text-indigo-400">sync</span>
        </span>
        <div className="flex gap-2">
          <NavLink to="/" end className={linkClass}>
            <ShoppingBag size={16} />
            Store
          </NavLink>
          <NavLink to="/admin" className={linkClass}>
            <LayoutDashboard size={16} />
            Admin Dashboard
          </NavLink>
          <NavLink to="/wal-sidecar" className={linkClass}>
            <HardDriveDownload size={16} />
            WAL Sidecar
          </NavLink>
        </div>
      </div>
    </nav>
  );
}
