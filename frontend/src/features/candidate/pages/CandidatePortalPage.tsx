import { Link } from 'react-router-dom'
import {
  FileUp,
  Search,
  Sparkles,
  User,
  Briefcase,
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
    to: '/jobs',
    icon: Briefcase,
    title: 'Tìm việc làm',
    description: 'Duyệt và lọc danh sách việc làm mới nhất từ các công ty.',
    cta: 'Duyệt việc làm',
    ai: false,
  },
  {
    to: '/jobs/search',
    icon: Search,
    title: 'Tìm việc AI',
    description:
      'Mô tả công việc bạn muốn bằng ngôn ngữ tự nhiên — AI tìm việc theo ngữ nghĩa.',
    cta: 'Tìm kiếm ngữ nghĩa',
    ai: true,
  },
  {
    to: '/candidate/recommendations',
    icon: Sparkles,
    title: 'Gợi ý việc làm',
    description: 'Xem top công việc được AI gợi ý dựa trên kỹ năng của bạn.',
    cta: 'Xem gợi ý',
    ai: true,
  },
  {
    to: '/candidate/cv-upload',
    icon: FileUp,
    title: 'Upload CV',
    description: 'Tải lên CV PDF để AI phân tích và trích xuất hồ sơ chuyên môn.',
    cta: 'Tải lên CV',
    ai: false,
  },
]

export function CandidatePortalPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Ứng viên"
        title="Tổng quan ứng viên"
        description="Quản lý hành trình tìm việc và ứng tuyển của bạn với sự hỗ trợ của AI."
        actions={
          <Link to="/candidate/profile">
            <Button variant="outline">
              <User className="h-4 w-4" aria-hidden="true" />
              Hồ sơ cá nhân
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
                <Button variant={card.ai ? 'default' : 'outline'} className="w-full">
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