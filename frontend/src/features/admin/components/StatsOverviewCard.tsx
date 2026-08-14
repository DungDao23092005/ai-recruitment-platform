import {
  Users,
  UserCheck,
  Briefcase,
  Building2,
  FileText,
  ClipboardList,
  UserCog,
} from 'lucide-react'
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import type { AdminStats } from '@/types/admin'

export interface StatsOverviewCardProps {
  stats: AdminStats
}

interface StatItem {
  label: string
  value: number
  icon: typeof Users
}

function StatCard({ label, value, icon: Icon }: StatItem) {
  return (
    <Card>
      <CardContent className="flex items-center gap-4 py-5">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-secondary text-secondary-foreground">
          <Icon className="h-5 w-5" aria-hidden="true" />
        </div>
        <div>
          <p className="text-2xl font-bold">{value}</p>
          <p className="text-xs uppercase text-muted-foreground">{label}</p>
        </div>
      </CardContent>
    </Card>
  )
}

export function StatsOverviewCard({ stats }: StatsOverviewCardProps) {
  const items: StatItem[] = [
    { label: 'Tổng người dùng', value: stats.total_users, icon: Users },
    { label: 'Ứng viên', value: stats.total_candidates, icon: UserCheck },
    {
      label: 'Nhà tuyển dụng',
      value: stats.total_recruiters,
      icon: Briefcase,
    },
    { label: 'Quản trị viên', value: stats.total_admins, icon: UserCog },
    { label: 'Công ty', value: stats.total_companies, icon: Building2 },
    { label: 'Tin tuyển dụng', value: stats.total_jobs, icon: FileText },
    {
      label: 'Đơn ứng tuyển',
      value: stats.total_applications,
      icon: ClipboardList,
    },
  ]

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Tổng quan hệ thống</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {items.map((item) => (
            <StatCard key={item.label} {...item} />
          ))}
        </div>
      </CardContent>
    </Card>
  )
}