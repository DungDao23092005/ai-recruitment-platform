import { Link, NavLink } from 'react-router-dom'
import { Sparkles } from 'lucide-react'
import { cn } from '@/utils/cn'
import { NAV_LINKS } from '@/routes'

export function Navbar() {
  return (
    <header className="sticky top-0 z-50 w-full border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <nav
        className="container flex h-14 items-center justify-between"
        aria-label="Main navigation"
      >
        <Link
          to="/"
          className="flex items-center gap-2 font-semibold"
          aria-label="AI Recruitment Platform home"
        >
          <span className="ai-gradient flex h-8 w-8 items-center justify-center rounded-lg text-white">
            <Sparkles className="h-4 w-4" />
          </span>
          <span>AI Recruitment</span>
        </Link>
        <div className="flex items-center gap-1">
          {NAV_LINKS.map((link) => (
            <NavLink
              key={link.to}
              to={link.to}
              className={({ isActive }) =>
                cn(
                  'rounded-md px-3 py-2 text-sm font-medium transition-colors',
                  isActive
                    ? 'bg-secondary text-secondary-foreground'
                    : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground',
                )
              }
            >
              {link.label}
            </NavLink>
          ))}
        </div>
      </nav>
    </header>
  )
}