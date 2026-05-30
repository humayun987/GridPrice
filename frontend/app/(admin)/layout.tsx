"use client";

import { useSession, signOut } from "next-auth/react";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";
import { LayoutDashboard, BarChart2, Settings, LogOut, Menu, X, Zap, ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";

const navItems = [
  { label: "Forecast", href: "/dashboard", icon: LayoutDashboard },
  { label: "Compare Markets", href: "/dashboard/compare", icon: BarChart2 },
];
const adminItems = [{ label: "Admin Panel", href: "/admin", icon: Settings }];

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const { data: session } = useSession();
  const pathname = usePathname();
  const router = useRouter();
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [userMenuOpen, setUserMenuOpen] = useState(false);

  const handleSignOut = async () => {
    await signOut({ redirect: false });
    router.push("/login");
  };

  return (
    <div className="min-h-screen bg-zinc-50 flex">
      <aside className={cn("fixed left-0 top-0 h-full bg-zinc-950 flex flex-col transition-all duration-300 z-40", sidebarOpen ? "w-60" : "w-16")}>
        <div className="flex items-center justify-between px-4 h-16 border-b border-zinc-800">
          {sidebarOpen && <span className="text-white font-semibold text-base tracking-tight">tatva<span className="text-emerald-400">.gridprice</span></span>}
          <button onClick={() => setSidebarOpen(!sidebarOpen)} className="text-zinc-400 hover:text-white transition-colors p-1 rounded">
            {sidebarOpen ? <X size={18} /> : <Menu size={18} />}
          </button>
        </div>

        <nav className="flex-1 px-2 py-4 space-y-1">
          {navItems.map((item) => (
            <a key={item.href} href={item.href} className={cn("flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors", pathname === item.href ? "bg-emerald-500/10 text-emerald-400" : "text-zinc-400 hover:text-white hover:bg-zinc-800")}>
              <item.icon size={18} className="shrink-0" />
              {sidebarOpen && <span>{item.label}</span>}
            </a>
          ))}
          {sidebarOpen && <p className="text-zinc-600 text-xs uppercase tracking-widest px-3 pt-4 pb-1">Admin</p>}
          {adminItems.map((item) => (
            <a key={item.href} href={item.href} className={cn("flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors", pathname === item.href ? "bg-emerald-500/10 text-emerald-400" : "text-zinc-400 hover:text-white hover:bg-zinc-800")}>
              <item.icon size={18} className="shrink-0" />
              {sidebarOpen && <span>{item.label}</span>}
            </a>
          ))}
        </nav>

        {sidebarOpen && (
          <div className="px-4 py-4 border-t border-zinc-800">
            <div className="flex items-center gap-2">
              <div className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
              <span className="text-zinc-500 text-xs">Forecasts updated daily</span>
            </div>
          </div>
        )}
      </aside>

      <div className={cn("flex-1 flex flex-col transition-all duration-300", sidebarOpen ? "ml-60" : "ml-16")}>
        <header className="h-16 bg-white border-b border-zinc-100 flex items-center justify-between px-6 sticky top-0 z-30">
          <div className="flex items-center gap-2">
            <Zap size={16} className="text-emerald-500" />
            <span className="text-zinc-500 text-sm">IEX Market Intelligence</span>
          </div>
          <div className="relative">
            <button onClick={() => setUserMenuOpen(!userMenuOpen)} className="flex items-center gap-2 text-sm text-zinc-700 hover:text-zinc-900 transition-colors">
              <div className="w-7 h-7 rounded-full bg-zinc-900 flex items-center justify-center">
                <span className="text-white text-xs font-medium">{session?.user?.email?.[0]?.toUpperCase() ?? "U"}</span>
              </div>
              <span className="font-medium">{session?.user?.email}</span>
              <ChevronDown size={14} className="text-zinc-400" />
            </button>
            {userMenuOpen && (
              <div className="absolute right-0 top-10 w-48 bg-white border border-zinc-100 rounded-xl shadow-lg py-1 z-50">
                <div className="px-3 py-2 border-b border-zinc-100">
                  <p className="text-xs text-zinc-400">Signed in as</p>
                  <p className="text-sm font-medium text-zinc-900 truncate">{session?.user?.email}</p>
                  <p className="text-xs text-emerald-500 capitalize mt-0.5">{(session as any)?.role}</p>
                </div>
                <button onClick={handleSignOut} className="w-full flex items-center gap-2 px-3 py-2 text-sm text-zinc-600 hover:text-red-600 hover:bg-red-50 transition-colors">
                  <LogOut size={14} />
                  Sign out
                </button>
              </div>
            )}
          </div>
        </header>
        <main className="flex-1 p-6">{children}</main>
      </div>
    </div>
  );
}
