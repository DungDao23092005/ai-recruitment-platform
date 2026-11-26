import { useCallback, useEffect, useState } from 'react'
import { Building, Pencil, PlusCircle } from 'lucide-react'
import { PageHeader } from '@/components/common/PageHeader'
import { EmptyState } from '@/components/ui/empty-state'
import { ErrorBanner } from '@/components/ui/error-banner'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { CompanyForm } from '@/features/recruiter/components/CompanyForm'
import { CompanyCard } from '@/features/recruiter/components/CompanyCard'
import { getCompanies } from '@/api/companies'
import { useWorkspace } from '@/contexts/WorkspaceContext'
import { getFriendlyErrorMessage } from '@/utils/errors'
import type { Company } from '@/types/company'

export function RecruiterCompanyPage() {
  const { selectedCompanyId, refreshWorkspaces, selectWorkspace } =
    useWorkspace()
  const [companies, setCompanies] = useState<Company[]>([])
  const [editingCompany, setEditingCompany] = useState<Company | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

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
    void loadCompanies()
  }, [loadCompanies])

  useEffect(() => {
    const handleCompanyUpdated = () => {
      void loadCompanies()
    }

    window.addEventListener('company:updated', handleCompanyUpdated)
    return () => {
      window.removeEventListener('company:updated', handleCompanyUpdated)
    }
  }, [loadCompanies])

  const handleCreated = async (created: Company) => {
    setCompanies((prev) => [created, ...prev])
    selectWorkspace(created.id)
    await refreshWorkspaces()
  }

  const isEditing = Boolean(editingCompany)

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Nhà tuyển dụng"
        title="Quản lý công ty"
        description="Tạo và xem thông tin công ty của bạn trước khi đăng tin tuyển dụng."
      />

      <div className="grid gap-6 lg:grid-cols-2 items-start">
        <Card className="border-border/80 shadow-sm">
          <CardHeader className="p-6">
            <div className="space-y-1">
              <CardTitle className="flex items-center gap-2 font-display text-lg font-bold tracking-tight">
                {isEditing ? (
                  <Pencil className="h-5 w-5 text-primary" aria-hidden="true" />
                ) : (
                  <PlusCircle className="h-5 w-5 text-primary" aria-hidden="true" />
                )}
                {isEditing ? 'Chỉnh sửa công ty' : 'Tạo công ty'}
              </CardTitle>
              <CardDescription>
                {isEditing
                  ? 'Cập nhật thông tin công ty của bạn.'
                  : 'Đăng ký công ty của bạn trước khi đăng tin tuyển dụng.'}
              </CardDescription>
            </div>
          </CardHeader>
          <CardContent className="p-6 pt-0">
            {isEditing ? (
              <div className="mb-4 flex items-center gap-2 rounded-lg border border-primary/20 bg-primary/5 px-3.5 py-2 text-xs text-primary">
                <span className="flex h-2 w-2 rounded-full bg-primary animate-pulse" />
                <span className="font-medium">Chế độ chỉnh sửa thông tin công ty</span>
              </div>
            ) : null}

            {editingCompany ? (
              <CompanyForm
                key={`company-edit-${editingCompany.id}`}
                mode="edit"
                company={editingCompany}
                onUpdated={async (updated) => {
                  setCompanies((prev) =>
                    prev.map((c) => (c.id === updated.id ? updated : c)),
                  )
                  setEditingCompany(null)
                  await refreshWorkspaces()
                }}
                onCancelEdit={() => setEditingCompany(null)}
              />
            ) : (
              <CompanyForm
                key="company-create"
                onCreated={(created) => {
                  void handleCreated(created)
                }}
              />
            )}
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
            <Card className="h-full border-border/80 shadow-sm">
              <CardHeader className="p-6">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex items-center gap-3.5 min-w-0 flex-1">
                    <Skeleton className="h-12 w-12 rounded-xl shrink-0" />
                    <div className="space-y-2 flex-1">
                      <Skeleton className="h-5 w-40" />
                      <Skeleton className="h-4 w-24 rounded-full" />
                    </div>
                  </div>
                  <Skeleton className="h-8 w-24 rounded-md shrink-0" />
                </div>
              </CardHeader>
              <CardContent className="space-y-3 px-6 pb-6 pt-0">
                <div className="grid gap-2.5 rounded-lg border border-border/50 bg-muted/20 p-3 sm:grid-cols-2">
                  <Skeleton className="h-5 w-32" />
                  <Skeleton className="h-5 w-28" />
                </div>
              </CardContent>
              <CardFooter className="border-t bg-muted/20 px-6 py-4">
                <Skeleton className="h-9 w-60 rounded-md" />
              </CardFooter>
            </Card>
          ) : null}

          {!isLoading && error == null ? (
            companies.length > 0 ? (
              <div className="space-y-4">
                {companies.map((c) => (
                  <CompanyCard
                    key={c.id}
                    company={c}
                    isActive={selectedCompanyId === c.id}
                    onSelect={() => selectWorkspace(c.id)}
                    onEdit={() => setEditingCompany(c)}
                  />
                ))}
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
