import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Sparkles } from 'lucide-react'
import { PageHeader } from '@/components/common/PageHeader'
import { Button } from '@/components/ui/button'
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
      <div className="container py-10">
        <PageHeader
          title="Post a Job"
          description="Create a new job posting with AI-assisted JD parsing."
        />
        <Card>
          <CardContent className="flex min-h-[30vh] flex-col items-center justify-center gap-3 py-10 text-center">
            <p className="text-sm font-medium text-muted-foreground">
              Bạn cần tạo company trước khi đăng tin tuyển dụng.
            </p>
            <Link to="/recruiter/company">
              <Button>Create a company</Button>
            </Link>
          </CardContent>
        </Card>
      </div>
    )
  }

  return (
    <div className="container py-10">
      <PageHeader
        title="Post a Job"
        description="Create a new job posting with AI-assisted JD parsing."
        actions={
          <Button variant="outline" onClick={() => setShowAiModal(true)}>
            <Sparkles className="h-4 w-4" aria-hidden="true" />
            AI Bóc Tách Kỹ Năng
          </Button>
        }
      />

      <Card>
        <CardHeader>
          <CardTitle>Job details</CardTitle>
          <CardDescription>
            Fill in the job information. You can use AI to extract skills from
            a job description.
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
