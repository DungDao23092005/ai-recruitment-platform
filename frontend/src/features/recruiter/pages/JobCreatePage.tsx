import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
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
import { useWorkspace } from '@/contexts/WorkspaceContext'
import { COMPANY_SIZE_LABELS } from '@/types/company'
import type { Company, CompanySize } from '@/types/company'
import { getFriendlyErrorMessage } from '@/utils/errors'
import { JobForm } from '@/features/recruiter/components/JobForm'
import { AIPredictJDModal } from '@/features/recruiter/components/AIPredictJDModal'
import type { ParsedJob } from '@/features/recruiter/components/AIPredictJDModal'

export interface JobCreatePageProps {
  companyId?: string | null
}

export function JobCreatePage({ companyId }: JobCreatePageProps) {
  let workspaceContext: ReturnType<typeof useWorkspace> | null = null
  try {
    workspaceContext = useWorkspace()
  } catch {
    workspaceContext = null
  }
  const workspaceCompanyId = workspaceContext?.selectedCompanyId ?? null
  const selectWorkspace = workspaceContext?.selectWorkspace

  const [searchParams, setSearchParams] = useSearchParams()
  const rawQueryCompanyId = searchParams.get('company_id')

  const [showAiModal, setShowAiModal] = useState(false)
  const [appliedParsed, setAppliedParsed] = useState<ParsedJob | null>(null)
  const [formRevision, setFormRevision] = useState(0)

  const [companies, setCompanies] = useState<Company[] | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [inPageSelectedCompanyId, setInPageSelectedCompanyId] = useState<
    string | null
  >(null)
  const [wantsToChangeCompany, setWantsToChangeCompany] = useState(false)

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

  // Validate query parameter against authorized companies
  const validatedQueryCompanyId = useMemo(() => {
    if (!rawQueryCompanyId || !companies) return null
    const match = companies.find((c) => c.id === rawQueryCompanyId)
    return match ? match.id : null
  }, [rawQueryCompanyId, companies])

  // Clear invalid/stale query parameter appropriately
  useEffect(() => {
    if (rawQueryCompanyId && companies && !validatedQueryCompanyId) {
      searchParams.delete('company_id')
      setSearchParams(searchParams, { replace: true })
    }
  }, [rawQueryCompanyId, companies, validatedQueryCompanyId, searchParams, setSearchParams])

  // PO3 Approved Precedence:
  // 1. Explicit companyId component prop, if supplied.
  // 2. Validated company_id URL query parameter.
  // 3. Explicit in-page company selection.
  // 4. Active WorkspaceContext.selectedCompanyId, if authorized.
  // 5. Single authorized company fallback.
  // 6. Otherwise, display the company selector.
  const effectiveCompanyId = useMemo(() => {
    if (companyIdValue) {
      return companyIdValue
    }

    if (!companies || companies.length === 0) {
      return null
    }

    if (wantsToChangeCompany && !inPageSelectedCompanyId) {
      return null
    }

    if (validatedQueryCompanyId) {
      return validatedQueryCompanyId
    }

    if (
      inPageSelectedCompanyId &&
      companies.some((c) => c.id === inPageSelectedCompanyId)
    ) {
      return inPageSelectedCompanyId
    }

    if (
      workspaceCompanyId &&
      companies.some((c) => c.id === workspaceCompanyId)
    ) {
      return workspaceCompanyId
    }

    if (companies.length === 1) {
      return companies[0].id
    }

    return null
  }, [
    companyIdValue,
    companies,
    wantsToChangeCompany,
    inPageSelectedCompanyId,
    validatedQueryCompanyId,
    workspaceCompanyId,
  ])

  // Synchronize active workspace ID with effective company ID
  useEffect(() => {
    if (
      effectiveCompanyId &&
      selectWorkspace &&
      workspaceCompanyId !== effectiveCompanyId
    ) {
      selectWorkspace(effectiveCompanyId)
    }
  }, [effectiveCompanyId, workspaceCompanyId, selectWorkspace])

  const handleSelectCompany = (id: string) => {
    if (selectWorkspace) {
      selectWorkspace(id)
    }
    setInPageSelectedCompanyId(id)
    setWantsToChangeCompany(false)
    setSearchParams({ company_id: id }, { replace: true })
  }

  const handleSwitchCompany = () => {
    setInPageSelectedCompanyId(null)
    setWantsToChangeCompany(true)
    searchParams.delete('company_id')
    setSearchParams(searchParams, { replace: true })
  }

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
        <Card className="border-border/80 shadow-sm">
          <CardHeader className="p-6">
            <CardTitle className="flex items-center gap-2 font-display text-lg font-bold tracking-tight">
              <FileText className="h-5 w-5 text-primary" aria-hidden="true" />
              Thông tin tin tuyển dụng
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4 p-6 pt-0">
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
        <Card className="border-border/80 shadow-sm">
          <CardHeader className="p-6">
            <CardTitle className="flex items-center gap-2 font-display text-lg font-bold tracking-tight">
              <Building className="h-5 w-5 text-primary" aria-hidden="true" />
              Chọn công ty
            </CardTitle>
            <CardDescription>
              Bạn có nhiều công ty. Chọn công ty để đăng tin tuyển dụng.
            </CardDescription>
          </CardHeader>
          <CardContent className="p-6 pt-0">
            <div className="grid gap-3 sm:grid-cols-2">
              {companies?.map((company) => {
                const monogram = company.name?.trim()
                  ? company.name.trim().charAt(0).toUpperCase()
                  : 'C'
                return (
                  <button
                    key={company.id}
                    type="button"
                    onClick={() => handleSelectCompany(company.id)}
                    className="flex items-center gap-3.5 rounded-xl border border-border/70 bg-card p-4 text-left transition-all hover:border-primary/50 hover:bg-muted/40 shadow-xs"
                  >
                    <div
                      className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg border border-primary/20 bg-primary/10 font-display text-base font-bold text-primary select-none"
                      aria-hidden="true"
                    >
                      {monogram}
                    </div>
                    <div className="min-w-0 space-y-0.5">
                      <span className="block font-display text-sm font-semibold text-foreground truncate">
                        {company.name}
                      </span>
                      <span className="block text-xs text-muted-foreground">
                        {COMPANY_SIZE_LABELS[company.size as CompanySize] ?? company.size}
                      </span>
                    </div>
                  </button>
                )
              })}
            </div>
          </CardContent>
        </Card>
      ) : null}

      {formVisible && activeCompany ? (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border/80 bg-card px-4 py-3 shadow-xs">
          <div className="flex items-center gap-3 min-w-0">
            <div
              className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-primary/20 bg-primary/10 font-display text-base font-bold text-primary select-none"
              aria-hidden="true"
            >
              {activeCompany.name?.trim()
                ? activeCompany.name.trim().charAt(0).toUpperCase()
                : 'C'}
            </div>
            <div className="min-w-0 space-y-0.5">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-display text-sm font-bold text-foreground truncate">
                  {activeCompany.name}
                </span>
                {activeCompany.slug ? (
                  <span className="inline-flex items-center rounded-full border border-border/50 bg-muted/60 px-2 py-0.5 font-mono text-[11px] text-muted-foreground">
                    @{activeCompany.slug}
                  </span>
                ) : null}
              </div>
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <span>Quy mô:</span>
                <span className="font-medium text-foreground">
                  {COMPANY_SIZE_LABELS[activeCompany.size as CompanySize] ?? activeCompany.size}
                </span>
              </div>
            </div>
          </div>
          {companyIdValue == null && companies != null && companies.length > 1 ? (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={handleSwitchCompany}
              className="text-xs text-muted-foreground hover:text-foreground"
            >
              Đổi công ty
            </Button>
          ) : null}
        </div>
      ) : null}

      {formVisible ? (
        <Card className="border-border/80 shadow-sm">
          <CardHeader className="p-6">
            <CardTitle className="flex items-center gap-2 font-display text-lg font-bold tracking-tight">
              <FileText className="h-5 w-5 text-primary" aria-hidden="true" />
              Thông tin tin tuyển dụng
            </CardTitle>
            <CardDescription>
              Điền thông tin công việc. Bạn có thể dùng AI để trích xuất kỹ năng
              từ bản mô tả công việc.
            </CardDescription>
          </CardHeader>
          <CardContent className="p-6 pt-0">
            <JobForm
              key={`job-form-${formRevision}`}
              companyId={effectiveCompanyId}
              onOpenAiModal={() => setShowAiModal(true)}
              initialValues={
                appliedParsed
                  ? {
                      title: appliedParsed.title ?? '',
                      description:
                        appliedParsed.summary ??
                        appliedParsed.title ??
                        '',
                      required_skills: appliedParsed.required_skills?.join(', ') ?? '',
                      preferred_skills: appliedParsed.preferred_skills?.join(', ') ?? '',
                      minimum_years_experience:
                        appliedParsed.minimum_years_experience?.toString() ?? '',
                      education_level: appliedParsed.education_level ?? '',
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
