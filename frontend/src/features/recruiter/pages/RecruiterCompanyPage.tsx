import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Building, PlusCircle } from 'lucide-react'
import { PageHeader } from '@/components/common/PageHeader'
import { Button } from '@/components/ui/button'
import { EmptyState } from '@/components/ui/empty-state'
import { ErrorBanner } from '@/components/ui/error-banner'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { CompanyForm } from '@/features/recruiter/components/CompanyForm'
import { CompanyCard } from '@/features/recruiter/components/CompanyCard'
import { getCompanies } from '@/api/companies'
import { getFriendlyErrorMessage } from '@/utils/errors'
import type { Company } from '@/types/company'

export function RecruiterCompanyPage() {
  const [company, setCompany] = useState<Company | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const loadCompanies = useCallback(async () => {
    setIsLoading(true)
    setError(null)
    try {
      const list = await getCompanies()
      setCompany(list[0] ?? null)
    } catch (err) {
      setError(getFriendlyErrorMessage(err))
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadCompanies()
  }, [loadCompanies])

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Nhà tuyển dụng"
        title="Quản lý công ty"
        description="Tạo và xem thông tin công ty của bạn trước khi đăng tin tuyển dụng."
      />

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <PlusCircle className="h-5 w-5 text-primary" aria-hidden="true" />
              Tạo công ty
            </CardTitle>
            <CardDescription>
              Đăng ký công ty của bạn trước khi đăng tin tuyển dụng.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <CompanyForm onCreated={setCompany} />
          </CardContent>
        </Card>

        <div className="space-y-4">
          {error != null ? (
            <ErrorBanner
              message={error}
              onRetry={() => void loadCompanies()}
            />
          ) : null}

          {isLoading ? (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Building className="h-5 w-5 text-primary" aria-hidden="true" />
                  Công ty của bạn
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <p className="text-sm text-muted-foreground">
                  Đang tải thông tin công ty...
                </p>
                <Skeleton className="h-6 w-2/3" />
                <Skeleton className="h-4 w-1/2" />
                <Skeleton className="h-10 w-full" />
              </CardContent>
            </Card>
          ) : null}

          {!isLoading && error == null ? (
            company ? (
              <div className="space-y-4">
                <h2 className="font-display text-lg font-semibold">
                  Công ty của bạn
                </h2>
                <CompanyCard company={company} />
                <Link to="/recruiter/jobs/new">
                  <Button className="w-full sm:w-auto">
                    <Building className="h-4 w-4" aria-hidden="true" />
                    Đăng tin tuyển dụng cho công ty này
                  </Button>
                </Link>
              </div>
            ) : (
              <EmptyState
                icon={<Building className="h-6 w-6" aria-hidden="true" />}
                title="Chưa có công ty"
                description="Sử dụng biểu mẫu bên cạnh để tạo công ty đầu tiên của bạn."
              />
            )
          ) : null}
        </div>
      </div>
    </div>
  )
}