import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { SemanticSearchBar } from '@/features/ai/components/SemanticSearchBar'
import { searchCandidates } from '@/api/ai'
import { PageHeader } from '@/components/common/PageHeader'
import { CandidatePreviewModal } from '@/features/recruiter/components/CandidatePreviewModal'

export function SemanticCandidateSearchPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const qParam = searchParams.get('q') || ''
  const sessionIdParam = searchParams.get('session_id') || ''
  const [selectedCandidateId, setSelectedCandidateId] = useState<string | null>(null)

  const handleSearch = (query: string, isRetry = false) => {
    let activeSessionId = sessionIdParam
    if (!isRetry || !activeSessionId) {
      activeSessionId = crypto.randomUUID()
      setSearchParams(
        { q: query, session_id: activeSessionId },
        { replace: isRetry },
      )
    }
    return searchCandidates({ q: query }, activeSessionId)
  }

  return (
    <div className="container py-10">
      <PageHeader
        title="Tìm kiếm ứng viên ngữ nghĩa"
        description="Mô tả ứng viên bạn cần bằng ngôn ngữ tự nhiên — AI sẽ tìm hồ sơ phù hợp theo ngữ nghĩa."
      />
      <SemanticSearchBar
        placeholder="Ví dụ: react developer với 5 năm kinh nghiệm..."
        initialQuery={qParam}
        autoSearchOnMount={Boolean(qParam && sessionIdParam)}
        searchFn={handleSearch}
        onResultClick={(result) => setSelectedCandidateId(result.id)}
      />
      {selectedCandidateId ? (
        <CandidatePreviewModal
          candidateId={selectedCandidateId}
          onClose={() => setSelectedCandidateId(null)}
        />
      ) : null}
    </div>
  )
}