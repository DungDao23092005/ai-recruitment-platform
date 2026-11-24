import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { Sparkles } from 'lucide-react'
import apiClient from '@/api/client'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { getFriendlyErrorMessage } from '@/utils/errors'
import { cn } from '@/utils/cn'
import {
  JOB_TYPE_LABELS,
  JOB_STATUS_LABELS,
  WORKPLACE_TYPE_LABELS,
} from '@/types/job'
import type {
  Job,
  JobStatus,
  JobType,
  WorkplaceType,
} from '@/types/job'

export interface JobFormProps {
  companyId: string
  onCreated?: (job: Job) => void
  onSaved?: (job: Job) => void
  initialValues?: Partial<FormValues>
  job?: Job
  onOpenAiModal?: () => void
}

interface FormValues {
  title: string
  description: string
  job_type: JobType
  workplace_type: WorkplaceType
  location: string
  status: JobStatus
  required_skills: string
  preferred_skills: string
  minimum_years_experience: string
  education_level: string
  duration_days: number
}

interface FormErrors {
  title?: string
  description?: string
}

function validate(values: FormValues): FormErrors {
  const errors: FormErrors = {}
  if (!values.title.trim()) {
    errors.title = 'Tiêu đề công việc là bắt buộc'
  }
  if (!values.description.trim()) {
    errors.description = 'Mô tả công việc là bắt buộc'
  }
  return errors
}

function parseSkills(skillsInput: string): string[] {
  return skillsInput
    .split(',')
    .map((s) => s.trim())
    .filter((s) => s.length > 0)
}

export interface JobFormErrorState {
  message: string
  showUpgradeAction: boolean
  upgradeUrl: string
}

export const CANONICAL_UPGRADE_URL = '/plans?audience=company'
export const QUOTA_EXHAUSTED_MESSAGE =
  'Gói hiện tại đã hết lượt đăng tin. Vui lòng nâng cấp gói để tiếp tục đăng tin tuyển dụng.'
export const DEFAULT_RBAC_FORBIDDEN_MESSAGE =
  'Bạn không có quyền đăng tin tuyển dụng cho công ty này.'

function isForbiddenError(error: unknown): boolean {
  return (
    typeof error === 'object' &&
    error !== null &&
    'response' in error &&
    (error as { response?: { status?: number } }).response?.status === 403
  )
}

function extractDetail(error: unknown): string {
  if (
    typeof error === 'object' &&
    error !== null &&
    'response' in error
  ) {
    const response = (error as { response?: { data?: { detail?: unknown } } })
      .response
    const detail = response?.data?.detail
    if (typeof detail === 'string') {
      return detail.trim()
    }
  }
  return ''
}

export function getJobFormError(error: unknown): JobFormErrorState {
  if (isForbiddenError(error)) {
    const detail = extractDetail(error)
    const normalized = detail.toLowerCase()

    // A. Job Posting Quota Exhaustion (company or legacy/personal)
    if (normalized.includes('hết lượt đăng tin')) {
      return {
        message: QUOTA_EXHAUSTED_MESSAGE,
        showUpgradeAction: true,
        upgradeUrl: CANONICAL_UPGRADE_URL,
      }
    }

    // C. Missing or Invalid Company / Recruiter Subscription
    if (
      normalized.includes('chưa có gói đăng ký hợp lệ') ||
      normalized.includes('chưa có gói đăng ký')
    ) {
      return {
        message:
          detail ||
          'Công ty chưa có gói đăng ký hợp lệ. Vui lòng đăng ký gói tuyển dụng để sử dụng tính năng này.',
        showUpgradeAction: true,
        upgradeUrl: CANONICAL_UPGRADE_URL,
      }
    }

    // B. Subscription Plan Does Not Include Job Posting / Recruiting Feature
    if (
      normalized.includes('không bao gồm quyền đăng tin') ||
      normalized.includes('không bao gồm quyền sử dụng tính năng') ||
      (normalized.includes('gói đăng ký') && normalized.includes('không bao gồm'))
    ) {
      return {
        message:
          detail || 'Gói đăng ký không bao gồm quyền đăng tin tuyển dụng.',
        showUpgradeAction: true,
        upgradeUrl: CANONICAL_UPGRADE_URL,
      }
    }

    // D. Genuine RBAC / Workspace Permission Denial / Unknown 403
    return {
      message: DEFAULT_RBAC_FORBIDDEN_MESSAGE,
      showUpgradeAction: false,
      upgradeUrl: CANONICAL_UPGRADE_URL,
    }
  }

  // E. Other Errors (non-403 responses)
  return {
    message: getFriendlyErrorMessage(error),
    showUpgradeAction: false,
    upgradeUrl: CANONICAL_UPGRADE_URL,
  }
}

export function getJobCreateErrorMessage(error: unknown): string {
  return getJobFormError(error).message
}

export function JobForm({
  companyId,
  onCreated,
  onSaved,
  initialValues,
  job,
  onOpenAiModal,
}: JobFormProps) {
  const isEditing = job != null
  const [values, setValues] = useState<FormValues>({
    title: job?.title ?? initialValues?.title ?? '',
    description: job?.description ?? initialValues?.description ?? '',
    job_type: job?.job_type ?? initialValues?.job_type ?? 'full_time',
    workplace_type:
      job?.workplace_type ?? initialValues?.workplace_type ?? 'on_site',
    location: job?.location ?? initialValues?.location ?? '',
    status: initialValues?.status ?? job?.status ?? 'draft',
    required_skills:
      initialValues?.required_skills ??
      (job?.required_skills?.length
        ? job.required_skills.join(', ')
        : job?.skills?.join(', ') ?? ''),
    preferred_skills:
      initialValues?.preferred_skills ??
      (job?.preferred_skills?.join(', ') ?? ''),
    minimum_years_experience:
      initialValues?.minimum_years_experience ??
      (job?.minimum_years_experience != null
        ? String(job.minimum_years_experience)
        : ''),
    education_level:
      initialValues?.education_level ?? (job?.education_level ?? ''),
    duration_days: initialValues?.duration_days ?? 30,
  })
  const [selectedExtensionDays, setSelectedExtensionDays] = useState<number | null>(null)
  const [errors, setErrors] = useState<FormErrors>({})
  const [apiError, setApiError] = useState<JobFormErrorState | null>(null)
  const [success, setSuccess] = useState(false)
  const [submitting, setSubmitting] = useState(false)

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    setApiError(null)
    setSuccess(false)

    const validationErrors = validate(values)
    setErrors(validationErrors)
    if (Object.keys(validationErrors).length > 0) {
      return
    }

    setSubmitting(true)
    try {
      const requiredSkills = parseSkills(values.required_skills)
      const preferredSkills = parseSkills(values.preferred_skills)
      const minimumYearsExperience = values.minimum_years_experience
        ? parseFloat(values.minimum_years_experience)
        : null
      const educationLevel = values.education_level.trim() || null

      if (isEditing && job) {
        const updatePayload: Record<string, unknown> = {
          title: values.title.trim(),
          description: values.description.trim(),
          job_type: values.job_type,
          workplace_type: values.workplace_type,
          location: values.location.trim() || null,
          required_skills: requiredSkills,
          preferred_skills: preferredSkills,
          minimum_years_experience: minimumYearsExperience,
          education_level: educationLevel,
        }
        if (job.status === 'published' && selectedExtensionDays != null) {
          updatePayload.duration_days = selectedExtensionDays
        }
        const updated = await apiClient.patch<Job, Job>(
          `/jobs/mine/${job.id}`,
          updatePayload,
        )
        setSuccess(true)
        onSaved?.(updated)
        return
      }

      const createPayload: Record<string, unknown> = {
        company_id: companyId,
        title: values.title.trim(),
        description: values.description.trim(),
        job_type: values.job_type,
        workplace_type: values.workplace_type,
        location: values.location.trim() || null,
        status: values.status,
        required_skills: requiredSkills,
        preferred_skills: preferredSkills,
        minimum_years_experience: minimumYearsExperience,
        education_level: educationLevel,
      }
      if (values.duration_days) {
        createPayload.duration_days = values.duration_days
      }

      const created = await apiClient.post<Job, Job>(
        '/jobs',
        createPayload,
        { timeout: 45000 }
      )
      setSuccess(true)
      onCreated?.(created)
    } catch (error) {
      setApiError(getJobFormError(error))
    } finally {
      setSubmitting(false)
    }
  }

  const updateField = <K extends keyof FormValues>(
    key: K,
    value: FormValues[K],
  ) => {
    setValues((v) => ({ ...v, [key]: value }))
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-8" noValidate>
      {/* Section 1: Thông tin cơ bản */}
      <div className="space-y-4">
        <div className="border-b border-border/60 pb-2">
          <h3 className="font-display text-sm font-semibold uppercase tracking-wider text-muted-foreground">
            Thông tin cơ bản
          </h3>
        </div>

        <Input
          name="title"
          label="Tiêu đề công việc"
          placeholder="Kỹ sư Frontend cấp cao"
          value={values.title}
          onChange={(e) => updateField('title', e.target.value)}
          error={errors.title}
        />

        {/* Contextual AI Assistant Card */}
        <div className="flex flex-col gap-3 rounded-xl border border-primary/20 bg-primary/5 p-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-start gap-3">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <Sparkles className="h-4 w-4" aria-hidden="true" />
            </div>
            <div className="space-y-0.5">
              <p className="text-xs font-semibold text-foreground">
                Trợ lý AI bóc tách JD
              </p>
              <p className="text-xs text-muted-foreground">
                Tự động trích xuất kỹ năng và yêu cầu ứng viên từ bản mô tả công việc để tiết kiệm thời gian điền form.
              </p>
            </div>
          </div>
          {onOpenAiModal ? (
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={onOpenAiModal}
              className="shrink-0 gap-1.5 border-primary/30 text-xs font-medium hover:bg-primary/10 hover:text-primary"
            >
              <Sparkles className="h-3.5 w-3.5 text-primary" aria-hidden="true" />
              Bóc tách kỹ năng bằng AI
            </Button>
          ) : null}
        </div>

        <Textarea
          name="description"
          label="Mô tả công việc"
          rows={6}
          value={values.description}
          onChange={(e) => updateField('description', e.target.value)}
          error={errors.description}
          placeholder="Mô tả vai trò, trách nhiệm và yêu cầu công việc..."
        />
      </div>

      {/* Section 2: Hình thức & Địa điểm */}
      <div className="space-y-4">
        <div className="border-b border-border/60 pb-2">
          <h3 className="font-display text-sm font-semibold uppercase tracking-wider text-muted-foreground">
            Hình thức & Địa điểm
          </h3>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <Select
            name="job_type"
            label="Loại công việc"
            value={values.job_type}
            onChange={(e) =>
              updateField('job_type', e.target.value as JobType)
            }
          >
            {(Object.keys(JOB_TYPE_LABELS) as JobType[]).map((type) => (
              <option key={type} value={type}>
                {JOB_TYPE_LABELS[type]}
              </option>
            ))}
          </Select>

          <Select
            name="workplace_type"
            label="Hình thức làm việc"
            value={values.workplace_type}
            onChange={(e) =>
              updateField('workplace_type', e.target.value as WorkplaceType)
            }
          >
            {(Object.keys(WORKPLACE_TYPE_LABELS) as WorkplaceType[]).map(
              (type) => (
                <option key={type} value={type}>
                  {WORKPLACE_TYPE_LABELS[type]}
                </option>
              ),
            )}
          </Select>

          <Input
            name="location"
            label="Địa điểm"
            placeholder="Hồ Chí Minh"
            value={values.location}
            onChange={(e) => updateField('location', e.target.value)}
          />

          {!isEditing ? (
            <Select
              name="status"
              label="Trạng thái"
              value={values.status}
              onChange={(e) =>
                updateField('status', e.target.value as JobStatus)
              }
            >
              <option value="draft">{JOB_STATUS_LABELS.draft}</option>
              <option value="published">{JOB_STATUS_LABELS.published}</option>
            </Select>
          ) : null}
        </div>
      </div>

      {/* Section 3: Yêu cầu ứng viên */}
      <div className="space-y-4">
        <div className="border-b border-border/60 pb-2">
          <h3 className="font-display text-sm font-semibold uppercase tracking-wider text-muted-foreground">
            Yêu cầu ứng viên
          </h3>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <div className="sm:col-span-2">
            <Input
              name="required_skills"
              label="Kỹ năng bắt buộc"
              placeholder="Python, FastAPI, SQL, Docker"
              value={values.required_skills}
              onChange={(e) => updateField('required_skills', e.target.value)}
              helperText="Nhập các kỹ năng bắt buộc cách nhau bằng dấu phẩy"
            />
          </div>

          <div className="sm:col-span-2">
            <Input
              name="preferred_skills"
              label="Kỹ năng ưu tiên"
              placeholder="React, TypeScript, AWS"
              value={values.preferred_skills}
              onChange={(e) => updateField('preferred_skills', e.target.value)}
              helperText="Nhập các kỹ năng ưu tiên (tùy chọn), cách nhau bằng dấu phẩy"
            />
          </div>

          <Input
            name="minimum_years_experience"
            label="Kinh nghiệm tối thiểu (năm)"
            placeholder="3"
            value={values.minimum_years_experience}
            onChange={(e) => updateField('minimum_years_experience', e.target.value)}
            type="number"
            min="0"
            step="0.5"
            helperText="Số năm kinh nghiệm tối thiểu (tùy chọn)"
          />

          <Input
            name="education_level"
            label="Yêu cầu học vấn"
            placeholder="Bachelor, Master, etc."
            value={values.education_level}
            onChange={(e) => updateField('education_level', e.target.value)}
            helperText="Yêu cầu trình độ học vấn (tùy chọn)"
          />
        </div>
      </div>

      {/* Section 4: Thời hạn tuyển dụng */}
      <div className="space-y-4">
        <div className="border-b border-border/60 pb-2">
          <h3 className="font-display text-sm font-semibold uppercase tracking-wider text-muted-foreground">
            Thời hạn tuyển dụng
          </h3>
        </div>

        {!isEditing ? (
          <div className="space-y-2">
            <label className="text-sm font-medium leading-none">
              Thời hạn đăng tin
            </label>
            <div
              className="grid grid-cols-3 gap-3 sm:max-w-md"
              role="group"
              aria-label="Thời hạn đăng tin"
            >
              {[14, 30, 60].map((days) => {
                const isSelected = values.duration_days === days
                return (
                  <button
                    key={days}
                    type="button"
                    aria-label={`${days} ngày`}
                    onClick={() => updateField('duration_days', days)}
                    className={cn(
                      'relative flex flex-col items-center justify-center rounded-lg border p-3 text-sm font-medium transition-all text-center',
                      isSelected
                        ? 'border-primary bg-primary/10 text-primary shadow-xs ring-1 ring-primary'
                        : 'border-border/70 bg-card hover:border-primary/40 hover:bg-muted/40 text-muted-foreground hover:text-foreground',
                    )}
                    aria-pressed={isSelected}
                  >
                    <span className="font-medium">{days} ngày</span>
                    {days === 30 ? (
                      <span
                        aria-hidden="true"
                        className="mt-1 rounded-full bg-primary/15 px-1.5 py-0.5 text-[10px] font-semibold text-primary"
                      >
                        Khuyên dùng
                      </span>
                    ) : null}
                  </button>
                )
              })}
            </div>
            <p className="text-xs text-muted-foreground">
              Mặc định 30 ngày. Thời gian đăng tối đa 90 ngày.
            </p>
          </div>
        ) : job && (job.status === 'published' || job.status === 'expired') ? (
          (() => {
            const isJobExpired =
              job.status === 'expired' ||
              Boolean(job.expires_at && new Date(job.expires_at) <= new Date())

            if (isJobExpired) {
              return (
                <div className="rounded-lg border border-destructive/20 bg-destructive/5 p-4 space-y-1.5">
                  <p className="text-sm font-semibold text-foreground">
                    Gia hạn thời gian tuyển dụng
                  </p>
                  <p className="text-xs font-medium text-destructive">
                    Tin tuyển dụng này đã hết hạn, không thể gia hạn.
                  </p>
                </div>
              )
            }

            const basePubDate = job.published_at
              ? new Date(job.published_at)
              : job.created_at
                ? new Date(job.created_at)
                : new Date()
            const maxExpiryDate = new Date(
              basePubDate.getTime() + 90 * 24 * 60 * 60 * 1000,
            )
            const currentExpiryDate = job.expires_at
              ? new Date(job.expires_at)
              : new Date()

            const getResultingExpiry = (days: number) => {
              return new Date(
                currentExpiryDate.getTime() + days * 24 * 60 * 60 * 1000,
              )
            }

            const canExtend14 = getResultingExpiry(14) <= maxExpiryDate
            const canExtend30 = getResultingExpiry(30) <= maxExpiryDate

            return (
              <div className="rounded-lg border border-border/70 bg-card p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <p className="text-sm font-semibold text-foreground">
                    Gia hạn thời gian tuyển dụng
                  </p>
                  {job.expires_at ? (
                    <span className="text-xs font-medium text-muted-foreground">
                      Hạn hiện tại:{' '}
                      {new Date(job.expires_at).toLocaleDateString('vi-VN')}
                    </span>
                  ) : null}
                </div>
                <div className="flex flex-wrap items-center gap-2.5">
                  {[14, 30].map((days) => {
                    const canExtend = days === 14 ? canExtend14 : canExtend30
                    const isSelected = selectedExtensionDays === days
                    return (
                      <Button
                        key={days}
                        type="button"
                        variant={isSelected ? 'default' : 'outline'}
                        size="sm"
                        disabled={!canExtend}
                        onClick={() =>
                          setSelectedExtensionDays(isSelected ? null : days)
                        }
                        title={
                          !canExtend
                            ? 'Vượt quá giới hạn tối đa 90 ngày'
                            : undefined
                        }
                        className={cn(
                          isSelected && 'ring-1 ring-primary shadow-xs',
                        )}
                      >
                        +{days} ngày
                      </Button>
                    )
                  })}
                </div>
                {selectedExtensionDays != null ? (
                  <p className="text-xs font-medium text-primary">
                    Hạn mới dự kiến:{' '}
                    {getResultingExpiry(selectedExtensionDays).toLocaleDateString(
                      'vi-VN',
                    )}
                  </p>
                ) : null}
                {(!canExtend14 || !canExtend30) && (
                  <p className="text-xs text-muted-foreground">
                    Thời hạn đăng tối đa là 90 ngày kể từ ngày đăng tin lần đầu.
                  </p>
                )}
              </div>
            )
          })()
        ) : null}
      </div>

      {isEditing ? (
        <div className="rounded-lg border border-border/60 bg-muted/30 px-3.5 py-2.5 text-xs text-muted-foreground">
          Trạng thái được quản lý từ danh sách tin tuyển dụng.
        </div>
      ) : null}

      {apiError ? (
        <div className="space-y-2 rounded-lg border border-destructive/20 bg-destructive/10 p-3.5">
          <p role="alert" className="text-sm font-medium text-destructive">
            {apiError.message}
          </p>
          {apiError.showUpgradeAction ? (
            <div className="pt-1">
              <Link to={apiError.upgradeUrl}>
                <Button type="button" variant="default" size="sm">
                  Nâng cấp gói
                </Button>
              </Link>
            </div>
          ) : null}
        </div>
      ) : null}

      {success ? (
        <div
          role="status"
          className="rounded-lg border border-success/20 bg-success/10 p-3 text-sm font-medium text-success"
        >
          {isEditing
            ? 'Cập nhật tin tuyển dụng thành công.'
            : 'Tạo tin tuyển dụng thành công.'}
        </div>
      ) : null}

      <Button type="submit" className="w-full" size="lg" isLoading={submitting}>
        {isEditing ? 'Lưu thay đổi' : 'Tạo tin tuyển dụng'}
      </Button>
    </form>
  )
}
