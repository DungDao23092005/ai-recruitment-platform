import { useState, type FormEvent } from 'react'
import { Sparkles } from 'lucide-react'
import apiClient from '@/api/client'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Spinner } from '@/components/ui/spinner'
import { getFriendlyErrorMessage } from '@/utils/errors'
import { Badge } from '@/components/ui/badge'

export interface ParsedJob {
  title: string | null
  summary: string | null
  required_skills: string[]
  preferred_skills: string[]
  minimum_years_experience: number | null
  education_level: string | null
}

export interface AIPredictJDModalProps {
  onClose: () => void
  onApply?: (parsed: ParsedJob) => void
}

export function AIPredictJDModal({ onClose, onApply }: AIPredictJDModalProps) {
  const [jobTitle, setJobTitle] = useState('')
  const [rawJd, setRawJd] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [parsed, setParsed] = useState<ParsedJob | null>(null)

  const handleParse = async (event: FormEvent) => {
    event.preventDefault()
    if (!rawJd.trim()) {
      setError('Please paste the job description first.')
      return
    }
    setIsLoading(true)
    setError(null)
    setParsed(null)
    try {
      const result = await apiClient.post<ParsedJob, ParsedJob>(
        '/ai/parse-jd',
        {
          job_title: jobTitle.trim(),
          job_description: rawJd,
          job_id: null,
        },
      )
      setParsed(result)
    } catch (err) {
      setError(getFriendlyErrorMessage(err))
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      role="dialog"
      aria-modal="true"
      aria-label="AI job description parser"
      onClick={onClose}
    >
      <div
        className="flex max-h-full w-full max-w-2xl flex-col overflow-hidden rounded-lg border bg-background shadow-lg"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="border-b p-5">
          <h2 className="flex items-center gap-2 text-lg font-semibold">
            <Sparkles className="h-5 w-5 text-primary" aria-hidden="true" />
            AI Bóc Tách Kỹ Năng
          </h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Paste your job description and let AI extract skills and
            requirements.
          </p>
        </div>

        <div className="flex-1 space-y-4 overflow-y-auto p-5">
          <Input
            name="job_title"
            label="Job title (optional)"
            placeholder="Senior Frontend Engineer"
            value={jobTitle}
            onChange={(e) => setJobTitle(e.target.value)}
          />
          <div className="flex flex-col gap-1.5">
            <label
              htmlFor="raw-jd"
              className="text-sm font-medium leading-none"
            >
              Raw job description
            </label>
            <textarea
              id="raw-jd"
              name="job_description"
              rows={8}
              value={rawJd}
              onChange={(e) => setRawJd(e.target.value)}
              className="flex w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-sm transition-colors placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              placeholder="Paste the full job description here..."
            />
          </div>

          <Button
            type="button"
            onClick={handleParse}
            disabled={isLoading}
            isLoading={isLoading}
          >
            <Sparkles className="h-4 w-4" aria-hidden="true" />
            AI Bóc Tách Kỹ Năng
          </Button>

          {error ? (
            <p role="alert" className="text-sm font-medium text-destructive">
              {error}
            </p>
          ) : null}

          {isLoading ? (
            <div className="flex items-center gap-3 text-sm text-muted-foreground">
              <Spinner size="sm" />
              <span>Đang phân tích JD...</span>
            </div>
          ) : null}

          {parsed ? (
            <div className="space-y-3 rounded-lg border bg-muted/20 p-4">
              {parsed.title ? (
                <p className="text-sm">
                  <span className="font-medium">Title: </span>
                  {parsed.title}
                </p>
              ) : null}
              {parsed.summary ? (
                <p className="text-sm">
                  <span className="font-medium">Summary: </span>
                  {parsed.summary}
                </p>
              ) : null}
              {parsed.required_skills.length > 0 ? (
                <div className="space-y-1">
                  <p className="text-sm font-medium">Required skills</p>
                  <div className="flex flex-wrap gap-2">
                    {parsed.required_skills.map((skill) => (
                      <Badge key={skill} variant="neutral">
                        {skill}
                      </Badge>
                    ))}
                  </div>
                </div>
              ) : null}
              {parsed.preferred_skills.length > 0 ? (
                <div className="space-y-1">
                  <p className="text-sm font-medium">Preferred skills</p>
                  <div className="flex flex-wrap gap-2">
                    {parsed.preferred_skills.map((skill) => (
                      <Badge key={skill} variant="warning">
                        {skill}
                      </Badge>
                    ))}
                  </div>
                </div>
              ) : null}
              {parsed.minimum_years_experience != null ? (
                <p className="text-sm">
                  <span className="font-medium">Min experience: </span>
                  {parsed.minimum_years_experience} years
                </p>
              ) : null}
              {parsed.education_level ? (
                <p className="text-sm">
                  <span className="font-medium">Education: </span>
                  {parsed.education_level}
                </p>
              ) : null}
            </div>
          ) : null}
        </div>

        <div className="flex items-center justify-end gap-2 border-t p-4">
          <Button variant="ghost" onClick={onClose} disabled={isLoading}>
            Close
          </Button>
          <Button
            disabled={!parsed}
            onClick={() => {
              if (parsed) onApply?.(parsed)
            }}
          >
            Áp dụng vào Form
          </Button>
        </div>
      </div>
    </div>
  )
}