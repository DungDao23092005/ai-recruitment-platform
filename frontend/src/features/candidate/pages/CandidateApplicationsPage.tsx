import { Link } from 'react-router-dom'
import { FileText, Search } from 'lucide-react'
import { PageHeader } from '@/components/common/PageHeader'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { ErrorBanner } from '@/components/ui/error-banner'
import { EmptyState } from '@/components/ui/empty-state'
import { ApplicationCard } from '@/features/candidate/components/ApplicationCard'
import { useMyApplications } from '@/features/candidate/hooks/useMyApplications'

export function CandidateApplicationsPage() {
  const { applications, isLoading, error, refresh, updateStatus } =
    useMyApplications()

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Ứng viên"
        title="Đơn ứng tuyển của tôi"
        description="Theo dõi các vị trí bạn đã ứng tuyển."
      />

      {isLoading ? (
        <div className="space-y-4">
          {Array.from({ length: 4 }).map((_, index) => (
            <Skeleton key={index} className="h-40 w-full" />
          ))}
        </div>
      ) : null}

      {error ? <ErrorBanner message={error} onRetry={refresh} /> : null}

      {!isLoading && !error && applications.length === 0 ? (
        <EmptyState
          icon={<FileText className="h-6 w-6" aria-hidden="true" />}
          title="Bạn chưa có đơn ứng tuyển"
          description="Hãy khám phá các công việc phù hợp và nộp đơn để theo dõi trạng thái tại đây."
        >
          <Link to="/candidate/jobs">
            <Button>
              <Search className="h-4 w-4" aria-hidden="true" />
              Khám phá việc làm
            </Button>
          </Link>
        </EmptyState>
      ) : null}

      {!isLoading && !error && applications.length > 0 ? (
        <div className="space-y-4">
          {applications.map((application) => (
            <ApplicationCard
              key={application.id}
              application={application}
              onWithdrawn={(applicationId) =>
                updateStatus(applicationId, 'withdrawn')
              }
            />
          ))}
        </div>
      ) : null}
    </div>
  )
}