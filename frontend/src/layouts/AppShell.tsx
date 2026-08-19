import { useEffect, useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import {
  Bot,
  Briefcase,
  Building,
  ClipboardList,
  FileText,
  LayoutDashboard,
  LogOut,
  Menu,
  PlusCircle,
  Search,
  Sparkles,
  User,
  Users,
  X,
  type LucideIcon,
} from 'lucide-react'
import { cn } from '@/utils/cn'
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
  end?: boolean
}

interface NavSection {
  title?: string
  items: NavItem[]
}

function useAppNav(role?: UserRole): NavSection[] {
  if (role === 'candidate') {
    return [
      {
        items: [
          { to: '/candidate/portal', label: 'Tổng quan', icon: LayoutDashboard },
        ],
      },
      {
        title: 'Tìm việc',
        items: [
          { to: '/candidate/jobs', label: 'Việc làm', icon: Briefcase, end: true },
          { to: '/candidate/applications', label: 'Đơn ứng tuyển', icon: ClipboardList },
          { to: '/jobs/search', label: 'Tìm việc AI', icon: Search },
          { to: '/candidate/recommendations', label: 'Gợi ý việc làm', icon: Sparkles },
        ],
      },
      {
        title: 'Hồ sơ',
        items: [
          { to: '/candidate/cv-upload', label: 'Upload CV', icon: FileText },
          { to: '/candidate/profile', label: 'Hồ sơ cá nhân', icon: User },
        ],
      },
    ]
  }
  if (role === 'recruiter') {
    return [
      {
        items: [
          { to: '/recruiter/portal', label: 'Tổng quan', icon: LayoutDashboard },
        ],
      },
      {
        title: 'Tuyển dụng',
        items: [
          { to: '/recruiter/company', label: 'Công ty', icon: Building },
          { to: '/recruiter/jobs', label: 'Tin tuyển dụng', icon: Briefcase, end: true },
          { to: '/recruiter/jobs/new', label: 'Đăng tin mới', icon: PlusCircle },
        ],
      },
      {
        title: 'AI hỗ trợ',
        items: [
          { to: '/recruiter/search/candidates', label: 'Tìm ứng viên AI', icon: Search },
        ],
      },
      {
        title: 'Tài khoản',
        items: [{ to: '/recruiter/profile', label: 'Hồ sơ cá nhân', icon: User }],
      },
    ]
  }
  return [
    {
      items: [
        { to: '/admin/dashboard', label: 'Tổng quan', icon: LayoutDashboard },
        { to: '/admin/users', label: 'Quản lý người dùng', icon: Users },
      ],
    },
    {
      title: 'Tuyển dụng',
      items: [
        { to: '/recruiter/portal', label: 'Quản lý tuyển dụng', icon: Users },
        { to: '/recruiter/jobs', label: 'Tin tuyển dụng', icon: Briefcase, end: true },
      ],
    },
    {
      title: 'AI hỗ trợ',
      items: [
        { to: '/recruiter/search/candidates', label: 'Tìm ứng viên AI', icon: Search },
      ],
    },
  ]
}

function SidebarNav({ role }: { role?: UserRole }) {
  const sections = useAppNav(role)
  const sectionClass = ({ isActive }: { isActive: boolean }) =>
    cn(
      'flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
      isActive
        ? 'bg-primary/10 text-primary'
        : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground',
    )

  return (
    <nav className="flex-1 space-y-6 overflow-y-auto p-4" aria-label="Điều hướng ứng dụng">
      {sections.map((section, index) => (
        <div key={index}>
          {section.title ? (
            <p className="mb-2 px-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              {section.title}
            </p>
          ) : null}
          <ul className="space-y-1">
            {section.items.map((item) => (
              <li key={item.to}>
                <NavLink to={item.to} end={item.end} className={sectionClass}>
                  {item.icon ? (
                    <item.icon className="h-4 w-4" aria-hidden="true" />
                  ) : null}
                  {item.label}
                </NavLink>
              </li>
            ))}
          </ul>
        </div>
      ))}
      <div>
        <p className="mb-2 px-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          Nền tảng
        </p>
        <ul className="space-y-1">
          <li>
            <NavLink to="/ai/chat" className={sectionClass}>
              <Bot className="h-4 w-4" aria-hidden="true" />
              Trợ lý AI
            </NavLink>
          </li>
          <li>
            <NavLink to="/jobs" end className={sectionClass}>
              <Briefcase className="h-4 w-4" aria-hidden="true" />
              Việc làm công khai
            </NavLink>
          </li>
          <li>
            <NavLink to="/health" className={sectionClass}>
              <FileText className="h-4 w-4" aria-hidden="true" />
              Sức khỏe hệ thống
            </NavLink>
          </li>
        </ul>
      </div>
    </nav>
  )
}

function SidebarUser({
  role,
  onLogout,
}: {
  role?: UserRole
  onLogout: () => void
}) {
  const { currentUser } = useAuth()
  const initials = currentUser?.email?.charAt(0).toUpperCase() ?? '?'

  return (
    <div className="border-t p-4">
      <div className="flex items-center gap-3">
        <div className="ai-gradient flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-sm font-bold text-white">
          {initials}
        </div>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium text-foreground">
            {currentUser?.email}
          </p>
          <Badge variant="outline-ai" className="mt-1">
            {USER_ROLE_LABELS[role ?? 'candidate']}
          </Badge>
        </div>
      </div>
      <Button
        variant="outline"
        size="sm"
        className="mt-3 w-full"
        onClick={onLogout}
        type="button"
      >
        <LogOut className="mr-1.5 h-3.5 w-3.5" aria-hidden="true" />
        Đăng xuất
      </Button>
    </div>
  )
}

export function AppShell() {
  const { currentUser, logout } = useAuth()
  const [drawerOpen, setDrawerOpen] = useState(false)
  const location = useLocation()
  const role = currentUser?.role

  useEffect(() => {
    setDrawerOpen(false)
  }, [location.pathname])

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setDrawerOpen(false)
      }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [])

  const sidebar = (
    <div className="flex h-full flex-col">
      <div className="flex h-16 items-center border-b px-5">
        <Logo />
      </div>
      <SidebarNav role={role} />
      <SidebarUser role={role} onLogout={logout} />
    </div>
  )

  return (
    <div className="flex min-h-screen">
      <aside className="sticky top-0 hidden h-screen w-64 shrink-0 border-r bg-card lg:block">
        {sidebar}
      </aside>

      {drawerOpen ? (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div
            className="absolute inset-0 bg-foreground/40 backdrop-blur-[2px]"
            onClick={() => setDrawerOpen(false)}
            aria-hidden="true"
          />
          <div className="absolute inset-y-0 left-0 w-72 max-w-[85vw] border-r bg-card shadow-soft-lg">
            <button
              type="button"
              className="absolute right-3 top-4 z-10 flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground hover:bg-accent hover:text-accent-foreground"
              onClick={() => setDrawerOpen(false)}
              aria-label="Đóng menu điều hướng"
            >
              <X className="h-4 w-4" aria-hidden="true" />
            </button>
            {sidebar}
          </div>
        </div>
      ) : null}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-16 items-center gap-3 border-b bg-background/95 px-4 backdrop-blur supports-[backdrop-filter]:bg-background/70 sm:px-6">
          <Button
            variant="ghost"
            size="icon"
            className="lg:hidden"
            onClick={() => setDrawerOpen(true)}
            aria-label="Mở menu điều hướng"
            type="button"
          >
            <Menu className="h-5 w-5" aria-hidden="true" />
          </Button>
          <div className="flex-1" />
          <Badge variant="outline-ai" className="hidden sm:inline-flex">
            {USER_ROLE_LABELS[role ?? 'candidate']}
          </Badge>
          <Button variant="ghost" size="sm" type="button" onClick={logout}>
            Đăng xuất
          </Button>
        </header>
        <main className="flex-1">
          <div className="container py-6 sm:py-8">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  )
}