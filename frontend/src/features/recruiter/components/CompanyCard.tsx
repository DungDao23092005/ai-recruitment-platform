import { Building, FileText } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { COMPANY_SIZE_LABELS } from '@/types/company'
import type { Company } from '@/types/company'

export interface CompanyCardProps {
  company: Company
}

export function CompanyCard({ company }: CompanyCardProps) {
  return (
    <Card className="h-full transition-shadow hover:shadow-md">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Building className="h-5 w-5 text-primary" aria-hidden="true" />
          {company.name}
        </CardTitle>
        <CardDescription className="flex items-center gap-1">
          <span className="text-xs uppercase text-muted-foreground">
            @{company.slug}
          </span>
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <p className="flex items-center gap-1 text-muted-foreground">
          <FileText className="h-4 w-4" aria-hidden="true" />
          Mã số thuế: {company.tax_code}
        </p>
        <Badge variant="neutral">{COMPANY_SIZE_LABELS[company.size]}</Badge>
      </CardContent>
    </Card>
  )
}
