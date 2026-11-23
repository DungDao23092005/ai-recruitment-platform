import { useState, type FormEvent } from 'react'
import apiClient from '@/api/client'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { getFriendlyErrorMessage } from '@/utils/errors'
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

function isForbiddenError(error: unknown): boolean {
  return (
    typeof error === 'object' &&
    error !== null &&
    'response' in error &&
    (error as { response?: { status?: number } }).response?.status === 403
  )
}

function getJobCreateErrorMessage(error: unknown): string {
  if (isForbiddenError(error)) {
    return 'Bạn không có quyền đăng tin tuyển dụng cho công ty này.'
  }
  return getFriendlyErrorMessage(error)
}

export function JobForm({
  companyId,
  onCreated,
  onSaved,
  initialValues,
  job,
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
  const [apiError, setApiError] = useState<string | null>(null)
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
      setApiError(getJobCreateErrorMessage(error))
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
    <form onSubmit={handleSubmit} className="space-y-6" noValidate>
      <div className="space-y-4">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          Thông tin cơ bản
        </h3>
        <Input
          name="title"
          label="Tiêu đề công việc"
          placeholder="Kỹ sư Frontend cấp cao"
          value={values.title}
          onChange={(e) => updateField('title', e.target.value)}
          error={errors.title}
        />
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

        <Input
          name="required_skills"
          label="Kỹ năng bắt buộc"
          placeholder="Python, FastAPI, SQL, Docker"
          value={values.required_skills}
          onChange={(e) => updateField('required_skills', e.target.value)}
          helperText="Nhập các kỹ năng bắt buộc cách nhau bằng dấu phẩy"
        />

        <Input
          name="preferred_skills"
          label="Kỹ năng ưu tiên"
          placeholder="React, TypeScript, AWS"
          value={values.preferred_skills}
          onChange={(e) => updateField('preferred_skills', e.target.value)}
          helperText="Nhập các kỹ năng ưu tiên (tùy chọn), cách nhau bằng dấu phẩy"
        />

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

        {!isEditing ? (
          <div className="space-y-2">
            <label className="text-sm font-medium leading-none">
              Thời hạn đăng tin
            </label>
            <div className="flex flex-wrap items-center gap-2">
              {[14, 30, 60].map((days) => (
                <Button
                  key={days}
                  type="button"
                  variant={values.duration_days === days ? 'default' : 'outline'}
                  size="sm"
                  onClick={() => updateField('duration_days', days)}
                >
                  {days} ngày
                </Button>
              ))}
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
                <div className="rounded-md border p-3 space-y-2">
                  <p className="text-sm font-medium">Gia hạn thời gian tuyển dụng</p>
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
              <div className="rounded-md border p-3 space-y-3">
                <div className="flex items-center justify-between">
                  <p className="text-sm font-medium">
                    Gia hạn thời gian tuyển dụng
                  </p>
                  {job.expires_at ? (
                    <span className="text-xs text-muted-foreground">
                      Hạn hiện tại:{' '}
                      {new Date(job.expires_at).toLocaleDateString('vi-VN')}
                    </span>
                  ) : null}
                </div>
                <div className="flex flex-wrap items-center gap-2">
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
        <p className="rounded-md bg-muted/40 px-3 py-2 text-sm text-muted-foreground">
          Trạng thái được quản lý từ danh sách tin tuyển dụng.
        </p>
      ) : null}

      {apiError ? (
        <p role="alert" className="text-sm font-medium text-destructive">
          {apiError}
        </p>
      ) : null}

      {success ? (
        <p role="status" className="text-sm font-medium text-success">
          {isEditing
            ? 'Cập nhật tin tuyển dụng thành công.'
            : 'Tạo tin tuyển dụng thành công.'}
        </p>
      ) : null}

      <Button type="submit" className="w-full" isLoading={submitting}>
        {isEditing ? 'Lưu thay đổi' : 'Tạo tin tuyển dụng'}
      </Button>
    </form>
  )
}