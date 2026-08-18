import { Outlet } from 'react-router-dom'
import { CheckCircle2, Sparkles } from 'lucide-react'
import { Logo } from '@/components/common/Logo'

const HIGHLIGHTS = [
  'Đối sánh CV thông minh bằng trí tuệ nhân tạo',
  'Gợi ý việc làm và ứng viên theo ngữ nghĩa',
  'Trợ lý AI đồng hành trong mọi bước tuyển dụng',
]

export function AuthLayout() {
  return (
    <div className="grid min-h-screen lg:grid-cols-2">
      <div className="relative hidden flex-col justify-between overflow-hidden bg-foreground p-12 lg:flex">
        <div className="ai-gradient absolute inset-0 opacity-[0.97]" aria-hidden="true" />
        <div className="absolute inset-0 bg-grid opacity-[0.12]" aria-hidden="true" />
        <div className="absolute -bottom-32 -right-24 h-96 w-96 rounded-full bg-white/10 blur-3xl" aria-hidden="true" />
        <div className="relative">
          <Logo variant="light" />
        </div>
        <div className="relative max-w-md">
          <p className="inline-flex items-center gap-2 rounded-full border border-white/25 bg-white/10 px-3 py-1 text-xs font-semibold text-white">
            <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
            Nền tảng tuyển dụng thông minh
          </p>
          <h1 className="mt-5 font-display text-3xl font-bold leading-tight text-white sm:text-4xl">
            Tìm đúng người.
            <br />
            Trúng công việc.
            <br />
            Nhanh hơn với AI.
          </h1>
          <ul className="mt-8 space-y-3.5">
            {HIGHLIGHTS.map((item) => (
              <li key={item} className="flex items-start gap-3 text-sm text-white/90">
                <CheckCircle2
                  className="mt-0.5 h-4 w-4 shrink-0 text-white"
                  aria-hidden="true"
                />
                {item}
              </li>
            ))}
          </ul>
        </div>
        <p className="relative text-xs text-white/70">
          Được xây dựng cho thị trường Việt Nam — dữ liệu thực tế, AI đối sánh
          chính xác.
        </p>
      </div>

      <div className="flex items-center justify-center p-4 sm:p-8">
        <div className="w-full max-w-md">
          <div className="mb-8 lg:hidden">
            <Logo />
          </div>
          <Outlet />
        </div>
      </div>
    </div>
  )
}