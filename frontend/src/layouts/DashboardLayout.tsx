import { Link, Outlet } from 'react-router-dom'

const SIDEBAR_LINKS = [
  { to: '/', label: 'Home' },
  { to: '/jobs', label: 'Việc làm' },
  { to: '/health', label: 'Health' },
]

export function DashboardLayout() {
  return (
    <div className="flex min-h-screen">
      <aside className="w-64 border-r bg-muted/30">
        <div className="flex h-14 items-center border-b px-4 font-semibold">
          Dashboard
        </div>
        <nav className="flex flex-col gap-1 p-2" aria-label="Dashboard">
          {SIDEBAR_LINKS.map((link) => (
            <Link
              key={link.to}
              to={link.to}
              className="rounded-md px-3 py-2 text-sm font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
            >
              {link.label}
            </Link>
          ))}
        </nav>
      </aside>
      <div className="flex flex-1 flex-col">
        <header className="flex h-14 items-center border-b px-6">
          <span className="text-sm font-medium">AI Recruitment Platform</span>
        </header>
        <main className="flex-1 p-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
