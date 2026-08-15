import { Search } from 'lucide-react'
import { SemanticSearchBar } from '@/features/ai/components/SemanticSearchBar'
import { searchJobs } from '@/api/ai'
import { PageHeader } from '@/components/common/PageHeader'

export function SemanticJobSearchPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Ứng viên"
        title="Tìm kiếm việc làm ngữ nghĩa"
        description="Mô tả công việc bạn muốn bằng ngôn ngữ tự nhiên — AI sẽ tìm việc phù hợp theo ngữ nghĩa."
      />
      <SemanticSearchBar
        placeholder="Tìm kiếm bằng mô tả tự nhiên..."
        searchFn={(query) => searchJobs({ q: query })}
      />
      <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
        <Search className="h-3.5 w-3.5" aria-hidden="true" />
        Ví dụ: Tôi muốn tìm công việc Python Backend tại TP.HCM
      </p>
    </div>
  )
}