import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Building, FileText, Sparkles } from 'lucide-react'
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
import { getCompanies } from '@/api/companies'
import { COMPANY_SIZE_LABELS } from '@/types/company'
import type { Company } from '@/types/company'
import { getFriendlyErrorMessage } from '@/utils/errors'
import { JobForm } from '@/features/recruiter/components/JobForm'
import { AIPredictJDModal } from '@/features/recruiter/components/AIPredictJDModal'
import type { ParsedJob } from '@/features/recruiter/components/AIPredictJDModal'

export interface JobCreatePageProps {
  companyId?: string | null
}

export function JobCreatePage({ companyId }: JobCreatePageProps) {
  const [showAiModal, setShowAiModal] = useState(false)
  const [appliedParsed, setAppliedParsed] = useState<ParsedJob | null>(null)
  const [formRevision, setFormRevision] = useState(0)

  const [companies, setCompanies] = useState<Company[] | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedCompanyId, setSelectedCompanyId] = useState<string | null>(
    null,
  )

  const companyIdValue = companyId ?? null

  const loadCompanies = useCallback(async () => {
    setIsLoading(true)
    setError(null)
    try {
      const list = await getCompanies()
      setCompanies(list)
    } catch (err) {
      setError(getFriendlyErrorMessage(err))
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    if (companyIdValue == null) {
      void loadCompanies()
    }
  }, [companyIdValue, loadCompanies])

  const effectiveCompanyId =
    companyIdValue ??
    selectedCompanyId ??
    (companies != null && companies.length === 1 ? companies[0].id : null)

  const activeCompany =
    companies?.find((company) => company.id === effectiveCompanyId) ?? null

  const formVisible = effectiveCompanyId != null
  const showEmptyState =
    !formVisible &&
    !isLoading &&
    error == null &&
    companies != null &&
    companies.length === 0
  const showSelector =
    !formVisible &&
    !isLoading &&
    error == null &&
    companies != null &&
    companies.length > 1

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Nhà tuyển dụng"
        title="Đăng tin tuyển dụng"
        description="Tạo tin tuyển dụng mới với sự hỗ trợ của AI bóc tách kỹ năng JD."
        actions={
          formVisible ? (
            <Button variant="outline" onClick={() => setShowAiModal(true)}>
              <Sparkles className="h-4 w-4" aria-hidden="true" />
              Phân tích JD bằng AI
            </Button>
          ) : undefined
        }
      />

      {!formVisible && error != null ? (
        <ErrorBanner message={error} onRetry={() => void loadCompanies()} />
      ) : null}

      {!formVisible && isLoading ? (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <FileText className="h-5 w-5 text-primary" aria-hidden="true" />
              Thông tin tin tuyển dụng
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-24 w-full" />
            <Skeleton className="h-10 w-full" />
          </CardContent>
        </Card>
      ) : null}

      {showEmptyState ? (
        <EmptyState
          icon={<Building className="h-6 w-6" aria-hidden="true" />}
          title="Chưa có công ty"
          description="Bạn cần tạo công ty trước khi đăng tin tuyển dụng."
        >
          <Link to="/recruiter/company">
            <Button>
              <Building className="h-4 w-4" aria-hidden="true" />
              Tạo công ty
            </Button>
          </Link>
        </EmptyState>
      ) : null}

      {showSelector ? (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Building className="h-5 w-5 text-primary" aria-hidden="true" />
              Chọn công ty
            </CardTitle>
            <CardDescription>
              Bạn có nhiều công ty. Chọn công ty để đăng tin tuyển dụng.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid gap-3">
              {companies?.map((company) => (
                <button
                  key={company.id}
                  type="button"
                  onClick={() => setSelectedCompanyId(company.id)}
                  className="flex items-center gap-3 rounded-lg border border-border bg-background px-4 py-3 text-left transition-colors hover:border-primary/50 hover:bg-muted/40"
                >
                  <Building className="h-5 w-5 shrink-0 text-primary" aria-hidden="true" />
                  <span>
                    <span className="block text-sm font-medium">
                      {company.name}
                    </span>
                    <span className="block text-xs text-muted-foreground">
                      {COMPANY_SIZE_LABELS[company.size]}
                    </span>
                  </span>
                </button>
              ))}
            </div>
          </CardContent>
        </Card>
      ) : null}

      {formVisible && activeCompany ? (
        <Card>
          <CardContent className="flex items-center gap-3 py-4">
            <Building className="h-5 w-5 shrink-0 text-primary" aria-hidden="true" />
            <div>
              <p className="text-sm font-medium">{activeCompany.name}</p>
              <p className="text-xs text-muted-foreground">
                {COMPANY_SIZE_LABELS[activeCompany.size]}
              </p>
            </div>
          </CardContent>
        </Card>
      ) : null}

      {formVisible ? (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <FileText className="h-5 w-5 text-primary" aria-hidden="true" />
              Thông tin tin tuyển dụng
            </CardTitle>
            <CardDescription>
              Điền thông tin công việc. Bạn có thể dùng AI để trích xuất kỹ năng
              từ bản mô tả công việc.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <JobForm
              key={`job-form-${formRevision}`}
              companyId={effectiveCompanyId}
              initialValues={
                appliedParsed
                  ? {
                      title: appliedParsed.title ?? '',
                      description:
                        appliedParsed.summary ??
                        appliedParsed.title ??
                        '',
                      skills: appliedParsed.required_skills?.join(', ') ?? '',
                    }
                  : undefined
              }
            />
          </CardContent>
        </Card>
      ) : null}

      {formVisible && showAiModal ? (
        <AIPredictJDModal
          onClose={() => setShowAiModal(false)}
          onApply={(parsed) => {
            setAppliedParsed(parsed)
            setFormRevision((prev) => prev + 1)
            setShowAiModal(false)
          }}
        />
      ) : null}
    </div>
  )
}