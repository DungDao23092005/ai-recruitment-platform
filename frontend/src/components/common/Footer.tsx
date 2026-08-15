import { Link } from 'react-router-dom'
import { Logo } from '@/components/common/Logo'

const CANDIDATE_LINKS = [
  { to: '/jobs', label: 'Tìm việc làm' },
  { to: '/jobs/search', label: 'Tìm việc AI' },
  { to: '/candidate/recommendations', label: 'Gợi ý việc làm' },
  { to: '/candidate/cv-upload', label: 'Upload CV' },
]

const RECRUITER_LINKS = [
  { to: '/recruiter/jobs/new', label: 'Đăng tin tuyển dụng' },
  { to: '/recruiter/search/candidates', label: 'Tìm ứng viên AI' },
  { to: '/recruiter/company', label: 'Quản lý công ty' },
  { to: '/recruiter/portal', label: 'Quản lý tuyển dụng' },
]

const PLATFORM_LINKS = [
  { to: '/ai/chat', label: 'Trợ lý AI' },
  { to: '/health', label: 'Sức khỏe hệ thống' },
]

export function Footer() {
  return (
    <footer className="border-t bg-muted/20">
      <div className="container py-12">
        <div className="grid gap-10 md:grid-cols-[2fr_1fr_1fr_1fr]">
          <div>
            <Logo />
            <p className="mt-4 max-w-sm text-sm leading-relaxed text-muted-foreground">
              Nền tảng tuyển dụng thông minh dành cho ứng viên và nhà tuyển
              dụng tại Việt Nam. AI đối sánh CV, gợi ý việc làm và tìm ứng viên
              phù hợp — nhanh chóng và chính xác.
            </p>
          </div>
          <div>
            <h3 className="font-display text-sm font-semibold text-foreground">
              Ứng viên
            </h3>
            <ul className="mt-3 space-y-2 text-sm text-muted-foreground">
              {CANDIDATE_LINKS.map((link) => (
                <li key={link.to}>
                  <Link
                    to={link.to}
                    className="transition-colors hover:text-foreground"
                  >
                    {link.label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
          <div>
            <h3 className="font-display text-sm font-semibold text-foreground">
              Nhà tuyển dụng
            </h3>
            <ul className="mt-3 space-y-2 text-sm text-muted-foreground">
              {RECRUITER_LINKS.map((link) => (
                <li key={link.to}>
                  <Link
                    to={link.to}
                    className="transition-colors hover:text-foreground"
                  >
                    {link.label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
          <div>
            <h3 className="font-display text-sm font-semibold text-foreground">
              Nền tảng
            </h3>
            <ul className="mt-3 space-y-2 text-sm text-muted-foreground">
              {PLATFORM_LINKS.map((link) => (
                <li key={link.to}>
                  <Link
                    to={link.to}
                    className="transition-colors hover:text-foreground"
                  >
                    {link.label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        </div>
        <div className="mt-10 flex flex-col items-center justify-between gap-2 border-t pt-6 text-xs text-muted-foreground sm:flex-row">
          <p>© {new Date().getFullYear()} Nền tảng tuyển dụng AI. Bảo lưu mọi quyền.</p>
          <p>Xây dựng với React, FastAPI và trí tuệ nhân tạo.</p>
        </div>
      </div>
    </footer>
  )
}