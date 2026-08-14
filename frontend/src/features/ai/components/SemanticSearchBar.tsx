import { useState, type FormEvent } from 'react'
import { Search, RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Spinner } from '@/components/ui/spinner'
import { getFriendlyErrorMessage } from '@/utils/errors'
import type { SemanticSearchResult } from '@/types/ai'

export interface SemanticSearchBarProps {
  placeholder?: string
  searchFn: (query: string) => Promise<SemanticSearchResult[]>
}

export function formatSearchScore(score: number): string {
  if (Number.isNaN(score)) {
    return '0%'
  }
  return `${Math.round(score * 100)}%`
}

export function SemanticSearchBar({
  placeholder = 'Nhập từ khóa tìm kiếm...',
  searchFn,
}: SemanticSearchBarProps) {
  const [query, setQuery] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [results, setResults] = useState<SemanticSearchResult[] | null>(null)

  const runSearch = async (q: string) => {
    if (!q.trim()) {
      return
    }
    setIsLoading(true)
    setError(null)
    try {
      const data = await searchFn(q.trim())
      setResults(data)
    } catch (err) {
      setError(getFriendlyErrorMessage(err))
      setResults(null)
    } finally {
      setIsLoading(false)
    }
  }

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault()
    void runSearch(query)
  }

  return (
    <div className="space-y-4">
      <form onSubmit={handleSubmit} className="flex gap-2">
        <input
          type="search"
          name="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={placeholder}
          aria-label="Semantic search query"
          className="flex h-10 w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-sm transition-colors placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
        />
        <Button
          type="submit"
          disabled={isLoading || !query.trim()}
          isLoading={isLoading}
          loadingText="Đang tìm..."
        >
          <Search className="h-4 w-4" aria-hidden="true" />
          Tìm kiếm
        </Button>
      </form>

      {error ? (
        <div role="alert" className="space-y-2">
          <p className="text-sm font-medium text-destructive">{error}</p>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => void runSearch(query)}
          >
            <RefreshCw className="h-4 w-4" aria-hidden="true" />
            Thử lại
          </Button>
        </div>
      ) : null}

      {isLoading ? (
        <div className="flex items-center gap-3 text-sm text-muted-foreground">
          <Spinner size="sm" />
          <span>Đang tìm kiếm ngữ nghĩa...</span>
        </div>
      ) : null}

      {results !== null && !isLoading && !error ? (
        results.length > 0 ? (
          <ul className="space-y-2">
            {results.map((result) => (
              <li
                key={result.id}
                className="flex items-start justify-between gap-3 rounded-lg border bg-card p-3"
              >
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium">{result.id}</p>
                  {result.skills.length > 0 ? (
                    <div className="mt-1 flex flex-wrap gap-1">
                      {result.skills.map((skill) => (
                        <Badge key={skill} variant="neutral">
                          {skill}
                        </Badge>
                      ))}
                    </div>
                  ) : null}
                </div>
                <Badge
                  variant="neutral"
                  className="shrink-0 text-sm font-bold"
                  aria-label={`Semantic score ${formatSearchScore(result.score)}`}
                >
                  {formatSearchScore(result.score)}
                </Badge>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted-foreground">
            Không tìm thấy kết quả phù hợp.
          </p>
        )
      ) : null}
    </div>
  )
}
