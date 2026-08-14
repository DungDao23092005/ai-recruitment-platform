import { Link, NavLink } from 'react-router-dom'
import { Sparkles } from 'lucide-react'
import { cn } from '@/utils/cn'
import { NAV_LINKS } from '@/routes'
import { useAuth } from '@/contexts/AuthContext'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { USER_ROLE_LABELS } from '@/types/auth'

export function Navbar() {
  const { currentUser, isAuthenticated, isLoading, logout } = useAuth()

  const profilePath =
    currentUser?.role === 'candidate'
      ? '/candidate/profile'
      : currentUser?.role === 'recruiter'
        ? '/recruiter/profile'
        : currentUser?.role === 'admin'
          ? '/admin/dashboard'
          : '/'

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

        <div className="hidden items-center gap-1 md:flex">
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
          {isAuthenticated && currentUser ? (
            <NavLink
              to="/ai/chat"
              className={({ isActive }) =>
                cn(
                  'rounded-md px-3 py-2 text-sm font-medium transition-colors',
                  isActive
                    ? 'bg-secondary text-secondary-foreground'
                    : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground',
                )
              }
            >
              Trợ lý AI
            </NavLink>
          ) : null}
          {isAuthenticated && currentUser?.role === 'candidate' ? (
            <>
              <NavLink
                to="/jobs/search"
                className={({ isActive }) =>
                  cn(
                    'rounded-md px-3 py-2 text-sm font-medium transition-colors',
                    isActive
                      ? 'bg-secondary text-secondary-foreground'
                      : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground',
                  )
                }
              >
                Tìm việc AI
              </NavLink>
              <NavLink
                to="/candidate/recommendations"
                className={({ isActive }) =>
                  cn(
                    'rounded-md px-3 py-2 text-sm font-medium transition-colors',
                    isActive
                      ? 'bg-secondary text-secondary-foreground'
                      : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground',
                  )
                }
              >
                Gợi ý việc làm
              </NavLink>
              <NavLink
                to="/candidate/cv-upload"
                className={({ isActive }) =>
                  cn(
                    'rounded-md px-3 py-2 text-sm font-medium transition-colors',
                    isActive
                      ? 'bg-secondary text-secondary-foreground'
                      : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground',
                  )
                }
              >
                Upload CV
              </NavLink>
            </>
          ) : null}
          {isAuthenticated &&
          (currentUser?.role === 'recruiter' ||
            currentUser?.role === 'admin') ? (
            <>
              {currentUser?.role === 'admin' ? (
                <NavLink
                  to="/admin/dashboard"
                  className={({ isActive }) =>
                    cn(
                      'rounded-md px-3 py-2 text-sm font-medium transition-colors',
                      isActive
                        ? 'bg-secondary text-secondary-foreground'
                        : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground',
                    )
                  }
                >
                  Admin Dashboard
                </NavLink>
              ) : null}
              <NavLink
                to="/recruiter/portal"
                className={({ isActive }) =>
                  cn(
                    'rounded-md px-3 py-2 text-sm font-medium transition-colors',
                    isActive
                      ? 'bg-secondary text-secondary-foreground'
                      : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground',
                  )
                }
              >
                Quản lý tuyển dụng
              </NavLink>
              <NavLink
                to="/recruiter/search/candidates"
                className={({ isActive }) =>
                  cn(
                    'rounded-md px-3 py-2 text-sm font-medium transition-colors',
                    isActive
                      ? 'bg-secondary text-secondary-foreground'
                      : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground',
                  )
                }
              >
                Tìm ứng viên AI
              </NavLink>
              <NavLink
                to="/recruiter/jobs/new"
                className={({ isActive }) =>
                  cn(
                    'rounded-md px-3 py-2 text-sm font-medium transition-colors',
                    isActive
                      ? 'bg-secondary text-secondary-foreground'
                      : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground',
                  )
                }
              >
                Đăng tin
              </NavLink>
            </>
          ) : null}
        </div>

        <div className="flex items-center gap-2">
          {isLoading ? null : isAuthenticated && currentUser ? (
            <>
              <Badge variant="ai-gradient" className="hidden sm:inline-flex">
                {USER_ROLE_LABELS[currentUser.role]}
              </Badge>
              <span className="hidden text-sm text-muted-foreground md:inline">
                {currentUser.email}
              </span>
              <Link to={profilePath}>
                <Button variant="ghost" size="sm">
                  Profile
                </Button>
              </Link>
              <Button
                variant="outline"
                size="sm"
                onClick={() => logout()}
                type="button"
              >
                Logout
              </Button>
            </>
          ) : (
            <>
              <Link to="/login">
                <Button variant="ghost" size="sm">
                  Login
                </Button>
              </Link>
              <Link to="/register">
                <Button variant="default" size="sm">
                  Register
                </Button>
              </Link>
            </>
          )}
        </div>
      </nav>
    </header>
  )
}