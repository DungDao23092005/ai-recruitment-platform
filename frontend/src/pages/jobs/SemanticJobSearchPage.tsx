import { SemanticSearchBar } from '@/features/ai/components/SemanticSearchBar'
import { searchJobs } from '@/api/ai'
import { PageHeader } from '@/components/common/PageHeader'

export function SemanticJobSearchPage() {
  return (
    <div className="container py-10">
      <PageHeader
        title="Tìm kiếm việc làm ngữ nghĩa"
        description="Mô tả công việc bạn muốn bằng ngôn ngữ tự nhiên — AI sẽ tìm việc phù hợp theo ngữ nghĩa."
      />
      <SemanticSearchBar
        placeholder="Ví dụ: python backend developer với FastAPI..."
        searchFn={(query) => searchJobs({ q: query })}
      />
    </div>
  )
}