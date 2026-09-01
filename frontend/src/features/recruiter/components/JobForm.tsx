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
  skills: string
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
    skills: initialValues?.skills ?? job?.skills?.join(', ') ?? '',
  })
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
      const skills = parseSkills(values.skills)

      if (isEditing && job) {
        const updated = await apiClient.patch<Job, Job>(`/jobs/mine/${job.id}`, {
          title: values.title.trim(),
          description: values.description.trim(),
          job_type: values.job_type,
          workplace_type: values.workplace_type,
          location: values.location.trim() || null,
          skills,
        })
        setSuccess(true)
        onSaved?.(updated)
        return
      }

      const created = await apiClient.post<Job, Job>(
        '/jobs',
        {
          company_id: companyId,
          title: values.title.trim(),
          description: values.description.trim(),
          job_type: values.job_type,
          workplace_type: values.workplace_type,
          location: values.location.trim() || null,
          status: values.status,
          skills,
        },
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
          name="skills"
          label="Kỹ năng yêu cầu"
          placeholder="Python, FastAPI, SQL, Docker"
          value={values.skills}
          onChange={(e) => updateField('skills', e.target.value)}
          helperText="Nhập các kỹ năng cách nhau bằng dấu phẩy"
        />
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