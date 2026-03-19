import { NavLink } from "react-router-dom";

const links = [
  { to: "/transactions", label: "Transactions", icon: "\u{1F4CB}" },
  { to: "/rules", label: "Rules", icon: "\u{1F4D0}" },
  { to: "/vendors", label: "Vendors", icon: "\u{1F3E2}" },
  { to: "/gl-reference", label: "GL Reference", icon: "\u{1F4D6}" },
];

export default function Sidebar() {
  return (
    <nav className="flex w-56 flex-col border-r border-gray-200 bg-white">
      <div className="flex h-14 items-center border-b border-gray-200 px-5">
        <span className="text-lg font-semibold text-gray-800">GL Classify</span>
      </div>
      <ul className="mt-2 flex-1 space-y-1 px-3">
        {links.map((l) => (
          <li key={l.to}>
            <NavLink
              to={l.to}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition ${
                  isActive
                    ? "bg-blue-50 text-blue-700"
                    : "text-gray-600 hover:bg-gray-100 hover:text-gray-900"
                }`
              }
            >
              <span className="text-base">{l.icon}</span>
              {l.label}
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  );
}
