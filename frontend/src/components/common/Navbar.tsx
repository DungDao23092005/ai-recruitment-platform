import { useState } from 'react'
import { NavLink, Link } from 'react-router-dom'
import {
  Bot,
  LayoutDashboard,
  LogOut,
  Menu,
  Search,
  Sparkles,
  User,
  X,
  type LucideIcon,
} from 'lucide-react'
import { cn } from '@/utils/cn'
import { NAV_LINKS } from '@/routes'
import { useAuth } from '@/contexts/AuthContext'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Logo } from '@/components/common/Logo'
import { USER_ROLE_LABELS } from '@/types/auth'
import type { UserRole } from '@/types/auth'

interface NavItem {
  to: string
  label: string
  icon?: LucideIcon
}

const AI_LINK: NavItem = { to: '/ai/chat', label: 'Trợ lý AI', icon: Bot }

function roleNavLinks(role?: UserRole): NavItem[] {
  if (role === 'candidate') {
    return [
      { to: '/candidate/portal', label: 'Tổng quan', icon: LayoutDashboard },
      { to: '/jobs/search', label: 'Tìm việc AI', icon: Search },
      { to: '/candidate/recommendations', label: 'Gợi ý việc làm', icon: Sparkles },
      AI_LINK,
    ]
  }
  if (role === 'admin') {
    return [
      { to: '/admin/dashboard', label: 'Bảng điều khiển', icon: LayoutDashboard },
      { to: '/recruiter/portal', label: 'Quản lý tuyển dụng', icon: User },
      { to: '/recruiter/search/candidates', label: 'Tìm ứng viên AI', icon: Search },
      AI_LINK,
    ]
  }
  return [
    { to: '/recruiter/portal', label: 'Quản lý tuyển dụng', icon: LayoutDashboard },
    { to: '/recruiter/jobs/new', label: 'Đăng tin', icon: Sparkles },
    { to: '/recruiter/search/candidates', label: 'Tìm ứng viên AI', icon: Search },
    AI_LINK,
  ]
}

function NavLinks({ links }: { links: NavItem[] }) {
  return (
    <>
      {links.map((link) => (
        <NavLink
          key={link.to}
          to={link.to}
          className={({ isActive }) =>
            cn(
              'flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
              isActive
                ? 'bg-primary/10 text-primary'
                : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground',
            )
          }
        >
          {link.icon ? (
            <link.icon className="h-4 w-4" aria-hidden="true" />
          ) : null}
          {link.label}
        </NavLink>
      ))}
    </>
  )
}

export function Navbar() {
  const { currentUser, isAuthenticated, isLoading, logout } = useAuth()
  const [mobileOpen, setMobileOpen] = useState(false)

  const role = currentUser?.role
  const appLinks = roleNavLinks(role)
  const profilePath =
    role === 'candidate'
      ? '/candidate/profile'
      : role === 'recruiter'
        ? '/recruiter/profile'
        : '/admin/dashboard'

  const handleLogout = () => {
    logout()
    setMobileOpen(false)
  }

  return (
    <header className="sticky top-0 z-40 w-full border-b bg-background/90 backdrop-blur supports-[backdrop-filter]:bg-background/70">
      <nav
        className="container flex h-16 items-center justify-between gap-4"
        aria-label="Điều hướng chính"
      >
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="icon"
            className="lg:hidden"
            onClick={() => setMobileOpen(true)}
            aria-label="Mở menu"
            type="button"
          >
            <Menu className="h-5 w-5" aria-hidden="true" />
          </Button>
          <Logo />
        </div>

        <div className="hidden items-center gap-1 lg:flex">
          <NavLinks links={NAV_LINKS} />
          {isAuthenticated ? <NavLinks links={appLinks} /> : null}
        </div>

        <div className="flex items-center gap-2">
          {isLoading ? null : isAuthenticated && currentUser ? (
            <>
              <Badge variant="outline-ai" className="hidden sm:inline-flex">
                {USER_ROLE_LABELS[currentUser.role]}
              </Badge>
              <span className="hidden max-w-[14rem] truncate text-sm text-muted-foreground xl:inline">
                {currentUser.email}
              </span>
              <Link to={profilePath}>
                <Button variant="ghost" size="sm">
                  Hồ sơ
                </Button>
              </Link>
              <Button
                variant="outline"
                size="sm"
                onClick={() => logout()}
                type="button"
                className="hidden sm:inline-flex"
              >
                <LogOut className="mr-1.5 h-3.5 w-3.5" aria-hidden="true" />
                Đăng xuất
              </Button>
            </>
          ) : (
            <>
              <Link to="/login">
                <Button variant="ghost" size="sm">
                  Đăng nhập
                </Button>
              </Link>
              <Link to="/register">
                <Button variant="default" size="sm">
                  Tạo tài khoản
                </Button>
              </Link>
            </>
          )}
        </div>
      </nav>

      {mobileOpen ? (
        <div className="border-t bg-background lg:hidden">
          <div className="container flex flex-col gap-1 py-4">
            <div className="mb-2 flex items-center justify-between">
              <p className="text-sm font-semibold text-foreground">Menu</p>
              <Button
                variant="ghost"
                size="icon"
                onClick={() => setMobileOpen(false)}
                aria-label="Đóng menu"
                type="button"
                className="h-8 w-8"
              >
                <X className="h-4 w-4" aria-hidden="true" />
              </Button>
            </div>
            <NavLinks links={NAV_LINKS} />
            {isAuthenticated ? <NavLinks links={appLinks} /> : null}
            <div className="mt-3 flex flex-col gap-2 border-t pt-3">
              {isAuthenticated && currentUser ? (
                <>
                  <div className="flex items-center gap-2">
                    <Badge variant="outline-ai">
                      {USER_ROLE_LABELS[currentUser.role]}
                    </Badge>
                    <span className="truncate text-sm text-muted-foreground">
                      {currentUser.email}
                    </span>
                  </div>
                  <Link to={profilePath} onClick={() => setMobileOpen(false)}>
                    <Button variant="outline" size="sm" className="w-full">
                      Hồ sơ
                    </Button>
                  </Link>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleLogout}
                    type="button"
                  >
                    <LogOut className="mr-1.5 h-3.5 w-3.5" aria-hidden="true" />
                    Đăng xuất
                  </Button>
                </>
              ) : (
                <>
                  <Link to="/login" onClick={() => setMobileOpen(false)}>
                    <Button variant="outline" size="sm" className="w-full">
                      Đăng nhập
                    </Button>
                  </Link>
                  <Link to="/register" onClick={() => setMobileOpen(false)}>
                    <Button variant="default" size="sm" className="w-full">
                      Tạo tài khoản
                    </Button>
                  </Link>
                </>
              )}
            </div>
          </div>
        </div>
      ) : null}
    </header>
  )
}