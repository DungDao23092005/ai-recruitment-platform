import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Building, FileText, Sparkles } from 'lucide-react'
import { PageHeader } from '@/components/common/PageHeader'
import { Button } from '@/components/ui/button'
import { EmptyState } from '@/components/ui/empty-state'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { JobForm } from '@/features/recruiter/components/JobForm'
import { AIPredictJDModal } from '@/features/recruiter/components/AIPredictJDModal'
import type { ParsedJob } from '@/features/recruiter/components/AIPredictJDModal'

export interface JobCreatePageProps {
  companyId?: string | null
}

export function JobCreatePage({ companyId }: JobCreatePageProps) {
  const [showAiModal, setShowAiModal] = useState(false)
  const [appliedParsed, setAppliedParsed] = useState<ParsedJob | null>(null)

  const companyIdValue = companyId ?? null

  if (!companyIdValue) {
    return (
      <div className="space-y-6">
        <PageHeader
          eyebrow="Nhà tuyển dụng"
          title="Đăng tin tuyển dụng"
          description="Tạo tin tuyển dụng mới với sự hỗ trợ của AI bóc tách kỹ năng JD."
        />
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
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Nhà tuyển dụng"
        title="Đăng tin tuyển dụng"
        description="Tạo tin tuyển dụng mới với sự hỗ trợ của AI bóc tách kỹ năng JD."
        actions={
          <Button variant="outline" onClick={() => setShowAiModal(true)}>
            <Sparkles className="h-4 w-4" aria-hidden="true" />
            Phân tích JD bằng AI
          </Button>
        }
      />

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
            companyId={companyIdValue}
            initialValues={
              appliedParsed
                ? {
                    title: appliedParsed.title ?? '',
                    description:
                      appliedParsed.summary ??
                      appliedParsed.title ??
                      '',
                  }
                : undefined
            }
          />
        </CardContent>
      </Card>

      {showAiModal ? (
        <AIPredictJDModal
          onClose={() => setShowAiModal(false)}
          onApply={(parsed) => {
            setAppliedParsed(parsed)
            setShowAiModal(false)
          }}
        />
      ) : null}
    </div>
  )
}