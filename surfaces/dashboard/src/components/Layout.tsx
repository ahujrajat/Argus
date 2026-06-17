import { Outlet } from "react-router-dom";
import { Nav } from "./Nav";

export function Layout() {
  return (
    <div className="flex min-h-screen bg-gray-950 text-gray-100">
      <Nav />
      <main className="flex-1 p-8 overflow-auto">
        <Outlet />
      </main>
    </div>
  );
}
