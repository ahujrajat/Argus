import { NavLink } from "react-router-dom";

const links = [
  { to: "/findings", label: "Findings" },
  { to: "/runs", label: "Live Runs" },
  { to: "/cost", label: "Cost & Usage" },
  { to: "/pipeline", label: "Pipeline" },
];

export function Nav() {
  return (
    <nav className="w-56 min-h-screen bg-gray-900 text-gray-200 flex flex-col py-8 px-4 gap-1">
      <span className="text-xl font-bold text-white mb-8 tracking-tight">Argus</span>
      {links.map((l) => (
        <NavLink
          key={l.to}
          to={l.to}
          className={({ isActive }) =>
            `px-3 py-2 rounded text-sm font-medium transition-colors ${
              isActive
                ? "bg-indigo-600 text-white"
                : "hover:bg-gray-800 text-gray-400"
            }`
          }
        >
          {l.label}
        </NavLink>
      ))}
    </nav>
  );
}
