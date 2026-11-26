import { Link } from 'react-router-dom'
import { Building, FileText, Pencil, Users } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { useWorkspace } from '@/contexts/WorkspaceContext'
import { COMPANY_SIZE_LABELS } from '@/types/company'
import type { Company, CompanySize } from '@/types/company'

export interface CompanyCardProps {
  company: Company
  isActive?: boolean
  onSelect?: () => void
  onEdit?: () => void
}

export function CompanyCard({
  company,
  isActive: propIsActive,
  onSelect,
  onEdit,
}: CompanyCardProps) {
  const { selectedCompanyId, selectWorkspace } = useWorkspace()
  const isActive = propIsActive ?? selectedCompanyId === company.id

  const handleSelect = () => {
    if (onSelect) {
      onSelect()
    } else {
      selectWorkspace(company.id)
    }
  }

  const monogram = company.name?.trim()
    ? company.name.trim().charAt(0).toUpperCase()
    : 'C'

  return (
    <Card className="h-full border-border/80 shadow-sm transition-shadow hover:shadow-md">
      <CardHeader className="p-6">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-center gap-3.5 min-w-0">
            <div
              className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl border border-primary/20 bg-primary/10 font-display text-xl font-bold text-primary shadow-xs select-none"
              aria-hidden="true"
            >
              {monogram}
            </div>
            <div className="space-y-1 min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <CardTitle className="font-display text-lg font-bold tracking-tight text-foreground truncate">
                  {company.name}
                </CardTitle>
                {isActive ? (
                  <Badge variant="outline-ai" className="shrink-0 text-xs font-semibold">
                    Đang chọn
                  </Badge>
                ) : null}
              </div>
              <div>
                <span className="inline-flex items-center rounded-full border border-border/60 bg-muted/70 px-2.5 py-0.5 font-mono text-xs text-muted-foreground">
                  @{company.slug}
                </span>
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {!isActive ? (
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={handleSelect}
                className="gap-1.5"
              >
                Chọn làm việc
              </Button>
            ) : null}
            {onEdit ? (
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={onEdit}
                className="gap-1.5"
              >
                <Pencil className="h-3.5 w-3.5" aria-hidden="true" />
                Chỉnh sửa
              </Button>
            ) : null}
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-3 px-6 pb-6 pt-0 text-sm">
        <div className="grid gap-2.5 rounded-lg border border-border/50 bg-muted/20 p-3 sm:grid-cols-2">
          <div className="flex items-center gap-2 text-muted-foreground">
            <FileText className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
            <span className="text-sm font-medium">Mã số thuế: {company.tax_code}</span>
          </div>
          <div className="flex items-center gap-2 text-muted-foreground">
            <Users className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
            <span className="text-xs">Quy mô:</span>
            <Badge variant="neutral" className="text-xs font-medium">
              {COMPANY_SIZE_LABELS[company.size as CompanySize] ?? company.size}
            </Badge>
          </div>
        </div>
      </CardContent>
      <CardFooter className="border-t bg-muted/20 px-6 py-4">
        <Link
          to={`/recruiter/jobs/new?company_id=${company.id}`}
          onClick={() => {
            selectWorkspace(company.id)
          }}
          className="w-full sm:w-auto"
        >
          <Button className="w-full sm:w-auto gap-2">
            <Building className="h-4 w-4" aria-hidden="true" />
            Đăng tin tuyển dụng cho công ty này
          </Button>
        </Link>
      </CardFooter>
    </Card>
  )
}
