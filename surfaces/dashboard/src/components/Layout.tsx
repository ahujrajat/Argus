import { Outlet } from "react-router-dom";
import { Nav } from "./Nav";

export function Layout() {
  return (
    <div className="flex min-h-screen bg-[#f5f5f7] text-gray-900">
      <Nav />
      <main className="flex-1 p-8 overflow-auto min-w-0">
        <Outlet />
      </main>
    </div>
  );
}
