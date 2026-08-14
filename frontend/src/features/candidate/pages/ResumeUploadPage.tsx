import { useState } from 'react'
import { ResumeUpload } from '@/features/candidate/components/ResumeUpload'
import { ParsedResumeView } from '@/features/candidate/components/ParsedResumeView'
import { PageHeader } from '@/components/common/PageHeader'
import type { ParsedResume } from '@/types/ai'

export function ResumeUploadPage() {
  const [parsedResume, setParsedResume] = useState<ParsedResume | null>(null)

  return (
    <div className="container py-10">
      <PageHeader
        title="Upload CV"
        description="Upload your PDF resume and let AI extract your professional profile."
      />

      <div className="max-w-2xl space-y-6">
        <ResumeUpload onParsed={setParsedResume} />

        {parsedResume ? (
          <ParsedResumeView resume={parsedResume} />
        ) : null}
      </div>
    </div>
  )
}