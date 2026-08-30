import { useState, type FormEvent } from 'react'
import { Search, RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Spinner } from '@/components/ui/spinner'
import { getFriendlyErrorMessage } from '@/utils/errors'
import { cn } from '@/utils/cn'
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

function scoreVariant(score: number): 'success' | 'warning' | 'neutral' {
  if (score >= 0.75) return 'success'
  if (score >= 0.5) return 'warning'
  return 'neutral'
}

function getDisplayName(result: SemanticSearchResult): string {
  // Priority: full_name (candidates) > title (jobs) > id (fallback)
  if (result.full_name) {
    return result.full_name
  }
  if (result.title) {
    return result.title
  }
  return result.id
}

function getSubtitle(result: SemanticSearchResult): string | null {
  // Candidate: full_name + title → show title as subtitle
  if (result.full_name && result.title) {
    return result.title
  }

  // Job: company_name + location → show "Company • Location"
  if (result.company_name) {
    const parts = [result.company_name]

    if (result.location) {
      parts.push(result.location)
    }

    return parts.join(' • ')
  }

  return null
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
        <Input
          type="search"
          name="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={placeholder}
          aria-label="Từ khóa tìm kiếm ngữ nghĩa"
          className="h-10"
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
                className="flex items-start justify-between gap-3 rounded-lg border bg-card p-3.5 transition-shadow hover:shadow-soft"
              >
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium">{getDisplayName(result)}</p>
                  {getSubtitle(result) ? (
                    <p className="truncate text-xs text-muted-foreground mt-0.5">
                      {getSubtitle(result)}
                    </p>
                  ) : null}
                  {result.skills.length > 0 ? (
                    <div className="mt-1.5 flex flex-wrap gap-1">
                      {result.skills.map((skill) => (
                        <Badge key={skill} variant="neutral">
                          {skill}
                        </Badge>
                      ))}
                    </div>
                  ) : null}
                </div>
                <Badge
                  variant={scoreVariant(result.score)}
                  className={cn(
                    'shrink-0 text-sm font-bold',
                    result.score >= 0.75 && 'text-success',
                    result.score >= 0.5 && result.score < 0.75 && 'text-warning',
                  )}
                  aria-label={`Độ phù hợp ${formatSearchScore(result.score)}`}
                >
                  {formatSearchScore(result.score)}
                </Badge>
              </li>
            ))}
          </ul>
        ) : (
          <p className="rounded-lg border border-dashed bg-muted/30 px-4 py-6 text-center text-sm text-muted-foreground">
            Không tìm thấy kết quả phù hợp.
          </p>
        )
      ) : null}
    </div>
  )
}