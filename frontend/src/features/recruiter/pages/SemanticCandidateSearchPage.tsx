import { SemanticSearchBar } from '@/features/ai/components/SemanticSearchBar'
import { searchCandidates } from '@/api/ai'
import { PageHeader } from '@/components/common/PageHeader'

export function SemanticCandidateSearchPage() {
  return (
    <div className="container py-10">
      <PageHeader
        title="Tìm kiếm ứng viên ngữ nghĩa"
        description="Mô tả ứng viên bạn cần bằng ngôn ngữ tự nhiên — AI sẽ tìm hồ sơ phù hợp theo ngữ nghĩa."
      />
      <SemanticSearchBar
        placeholder="Ví dụ: react developer với 5 năm kinh nghiệm..."
        searchFn={(query) => searchCandidates({ q: query })}
      />
    </div>
  )
}