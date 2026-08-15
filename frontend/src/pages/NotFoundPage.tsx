import { Link } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import { Button } from '@/components/ui/button'

export function NotFoundPage() {
  return (
    <div className="container flex flex-col items-center justify-center py-24 text-center">
      <p className="ai-text font-display text-7xl font-bold">404</p>
      <h1 className="mt-4 font-display text-2xl font-bold tracking-tight">
        Trang không tồn tại
      </h1>
      <p className="mt-2 max-w-md text-sm text-muted-foreground">
        Trang bạn đang tìm kiếm không tồn tại hoặc đã bị di chuyển.
      </p>
      <Link to="/" className="mt-6">
        <Button>
          <ArrowLeft className="mr-1.5 h-4 w-4" aria-hidden="true" />
          Về trang chủ
        </Button>
      </Link>
    </div>
  )
}