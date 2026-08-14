import { Outlet } from 'react-router-dom'

export function DashboardLayout() {
  return (
    <div className="flex min-h-screen">
      <aside className="w-64 border-r bg-muted/30">
        <div className="flex h-14 items-center border-b px-4 font-semibold">
          Dashboard
        </div>
        <nav className="flex flex-col gap-1 p-2" aria-label="Dashboard">
          <span className="px-3 py-2 text-sm text-muted-foreground">
            Navigation coming soon
          </span>
        </nav>
      </aside>
      <div className="flex flex-1 flex-col">
        <header className="flex h-14 items-center border-b px-6">
          <span className="text-sm font-medium">Topbar</span>
        </header>
        <main className="flex-1 p-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}