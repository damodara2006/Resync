import { HardDriveDownload, ShoppingBag } from "lucide-react";
import { NavLink } from "react-router-dom";

const linkClass = ({ isActive }) =>
  `flex items-center gap-2 rounded-lg px-3.5 py-2 text-sm font-medium transition ${
    isActive
      ? "bg-indigo-600 text-white shadow-sm shadow-indigo-200"
      : "text-slate-500 hover:bg-slate-100 hover:text-slate-900"
  }`;

export default function NavBar() {
  return (
    <nav className="sticky top-0 z-10 border-b border-slate-200 bg-white/90 backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-3.5">
        <div className="flex items-center gap-2.5">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-600 text-sm font-bold text-white">
            R
          </span>
          <div className="leading-tight">
            <span className="block text-base font-bold tracking-tight text-slate-900">
              Resync
            </span>
            <span className="hidden text-[11px] text-slate-400 sm:block">
              Payment reconciliation
            </span>
          </div>
        </div>
        <div className="flex gap-1.5">
          <NavLink to="/" end className={linkClass}>
            <ShoppingBag size={16} />
            Store
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
