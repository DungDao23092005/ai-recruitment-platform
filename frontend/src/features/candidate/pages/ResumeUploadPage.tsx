import { useState } from 'react'
import { ResumeUpload } from '@/features/candidate/components/ResumeUpload'
import { ParsedResumeView } from '@/features/candidate/components/ParsedResumeView'
import { PageHeader } from '@/components/common/PageHeader'
import type { ParsedResume } from '@/types/ai'

export function ResumeUploadPage() {
  const [parsedResume, setParsedResume] = useState<ParsedResume | null>(null)

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Hồ sơ"
        title="Tải lên CV"
        description="Tải lên CV PDF và để AI trích xuất hồ sơ chuyên môn của bạn."
      />

      <div className="max-w-2xl space-y-6">
        <ResumeUpload onParsed={setParsedResume} />

        {parsedResume ? <ParsedResumeView resume={parsedResume} /> : null}
      </div>
    </div>
  )
}