import { Link } from 'react-router-dom'
import {
  Building,
  Briefcase,
  PlusCircle,
  Users,
  Sparkles,
  ArrowRight,
} from 'lucide-react'
import { PageHeader } from '@/components/common/PageHeader'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'

const PORTAL_CARDS = [
  {
    to: '/recruiter/company',
    icon: Building,
    title: 'Quản lý công ty',
    description: 'Tạo và xem thông tin công ty của bạn trước khi đăng tin.',
    cta: 'Quản lý công ty',
    ai: false,
  },
  {
    to: '/recruiter/jobs',
    icon: Briefcase,
    title: 'Tin tuyển dụng',
    description: 'Xem và quản lý các tin tuyển dụng cùng ứng viên của bạn.',
    cta: 'Xem tin tuyển dụng',
    ai: false,
  },
  {
    to: '/recruiter/jobs/new',
    icon: PlusCircle,
    title: 'Đăng tin tuyển dụng',
    description:
      'Tạo tin tuyển dụng mới với sự hỗ trợ của AI bóc tách kỹ năng JD.',
    cta: 'Đăng tin',
    ai: true,
  },
  {
    to: '/recruiter/search/candidates',
    icon: Users,
    title: 'Tìm ứng viên AI',
    description:
      'Mô tả ứng viên bạn cần bằng ngôn ngữ tự nhiên — AI tìm hồ sơ theo ngữ nghĩa.',
    cta: 'Tìm kiếm ngữ nghĩa',
    ai: true,
  },
]

export function RecruiterPortalPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Nhà tuyển dụng"
        title="Tổng quan tuyển dụng"
        description="Quản lý công ty, tin tuyển dụng và ứng viên với sự hỗ trợ của AI."
        actions={
          <Link to="/recruiter/jobs/new">
            <Button>
              <Sparkles className="h-4 w-4" aria-hidden="true" />
              Đăng tin tuyển dụng
            </Button>
          </Link>
        }
      />

      <div className="grid gap-6 md:grid-cols-2">
        {PORTAL_CARDS.map((card) => (
          <Card
            key={card.to}
            className="group border-border/70 transition-all duration-200 hover:-translate-y-0.5 hover:border-primary/30 hover:shadow-soft"
          >
            <CardHeader className="gap-3">
              <div className="flex items-center justify-between">
                <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-primary/10 text-primary">
                  <card.icon className="h-5 w-5" aria-hidden="true" />
                </div>
                {card.ai ? <Badge variant="ai-gradient">AI</Badge> : null}
              </div>
              <CardTitle className="font-display text-lg font-semibold">
                {card.title}
              </CardTitle>
              <CardDescription>{card.description}</CardDescription>
            </CardHeader>
            <CardContent>
              <Link to={card.to}>
                <Button
                  variant={card.ai ? 'default' : 'outline'}
                  className="w-full"
                >
                  {card.cta}
                  <ArrowRight className="h-4 w-4" aria-hidden="true" />
                </Button>
              </Link>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  )
}