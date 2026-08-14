import { useState, type FormEvent } from 'react'
import apiClient from '@/api/client'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
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
  initialValues?: Partial<FormValues>
}

interface FormValues {
  title: string
  description: string
  job_type: JobType
  workplace_type: WorkplaceType
  location: string
  status: JobStatus
}

interface FormErrors {
  title?: string
  description?: string
}

function validate(values: FormValues): FormErrors {
  const errors: FormErrors = {}
  if (!values.title.trim()) {
    errors.title = 'Job title is required'
  }
  if (!values.description.trim()) {
    errors.description = 'Job description is required'
  }
  return errors
}

export function JobForm({
  companyId,
  onCreated,
  initialValues,
}: JobFormProps) {
  const [values, setValues] = useState<FormValues>({
    title: initialValues?.title ?? '',
    description: initialValues?.description ?? '',
    job_type: initialValues?.job_type ?? 'full_time',
    workplace_type: initialValues?.workplace_type ?? 'on_site',
    location: initialValues?.location ?? '',
    status: initialValues?.status ?? 'draft',
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
      const job = await apiClient.post<Job, Job>('/jobs', {
        company_id: companyId,
        title: values.title.trim(),
        description: values.description.trim(),
        job_type: values.job_type,
        workplace_type: values.workplace_type,
        location: values.location.trim() || null,
        status: values.status,
      })
      setSuccess(true)
      onCreated?.(job)
    } catch (error) {
      setApiError(getFriendlyErrorMessage(error))
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
    <form onSubmit={handleSubmit} className="space-y-4" noValidate>
      <Input
        name="title"
        label="Job title"
        placeholder="Senior Frontend Engineer"
        value={values.title}
        onChange={(e) => updateField('title', e.target.value)}
        error={errors.title}
      />
      <div className="flex flex-col gap-1.5">
        <label
          htmlFor="job-description"
          className="text-sm font-medium leading-none"
        >
          Description
        </label>
        <textarea
          id="job-description"
          name="description"
          rows={6}
          value={values.description}
          onChange={(e) => updateField('description', e.target.value)}
          aria-invalid={errors.description ? true : undefined}
          className="flex w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-sm transition-colors placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
          placeholder="Describe the role, responsibilities and requirements..."
        />
        {errors.description ? (
          <span className="text-xs font-medium text-destructive">
            {errors.description}
          </span>
        ) : null}
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div className="flex flex-col gap-1.5">
          <label
            htmlFor="job-type"
            className="text-sm font-medium leading-none"
          >
            Job type
          </label>
          <select
            id="job-type"
            name="job_type"
            value={values.job_type}
            onChange={(e) =>
              updateField('job_type', e.target.value as JobType)
            }
            className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
          >
            {(Object.keys(JOB_TYPE_LABELS) as JobType[]).map((type) => (
              <option key={type} value={type}>
                {JOB_TYPE_LABELS[type]}
              </option>
            ))}
          </select>
        </div>

        <div className="flex flex-col gap-1.5">
          <label
            htmlFor="workplace-type"
            className="text-sm font-medium leading-none"
          >
            Workplace type
          </label>
          <select
            id="workplace-type"
            name="workplace_type"
            value={values.workplace_type}
            onChange={(e) =>
              updateField('workplace_type', e.target.value as WorkplaceType)
            }
            className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
          >
            {(Object.keys(WORKPLACE_TYPE_LABELS) as WorkplaceType[]).map(
              (type) => (
                <option key={type} value={type}>
                  {WORKPLACE_TYPE_LABELS[type]}
                </option>
              ),
            )}
          </select>
        </div>

        <div className="flex flex-col gap-1.5">
          <label
            htmlFor="job-location"
            className="text-sm font-medium leading-none"
          >
            Location
          </label>
          <Input
            id="job-location"
            name="location"
            placeholder="Ho Chi Minh City"
            value={values.location}
            onChange={(e) => updateField('location', e.target.value)}
          />
        </div>

        <div className="flex flex-col gap-1.5">
          <label
            htmlFor="job-status"
            className="text-sm font-medium leading-none"
          >
            Status
          </label>
          <select
            id="job-status"
            name="status"
            value={values.status}
            onChange={(e) =>
              updateField('status', e.target.value as JobStatus)
            }
            className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
          >
            <option value="draft">{JOB_STATUS_LABELS.draft}</option>
            <option value="published">{JOB_STATUS_LABELS.published}</option>
          </select>
        </div>
      </div>

      {apiError ? (
        <p role="alert" className="text-sm font-medium text-destructive">
          {apiError}
        </p>
      ) : null}

      {success ? (
        <p role="status" className="text-sm font-medium text-green-600">
          Job created successfully.
        </p>
      ) : null}

      <Button type="submit" className="w-full" isLoading={submitting}>
        Create job
      </Button>
    </form>
  )
}
