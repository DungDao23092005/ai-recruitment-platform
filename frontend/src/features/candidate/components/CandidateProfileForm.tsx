import { useEffect, useState, type FormEvent } from 'react'
import { getCandidateProfile, updateCandidateProfile } from '@/api/auth'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { ErrorBanner } from '@/components/ui/error-banner'
import { getFriendlyErrorMessage } from '@/utils/errors'

interface FormValues {
  full_name: string
  phone: string
  title: string
}

interface FormErrors {
  phone?: string
}

function isNotFoundError(error: unknown): boolean {
  return (
    typeof error === 'object' &&
    error !== null &&
    'response' in error &&
    (error as { response?: { status?: number } }).response?.status === 404
  )
}

function validate(values: FormValues): FormErrors {
  const errors: FormErrors = {}
  if (values.phone && !/^[0-9+\-() ]+$/.test(values.phone)) {
    errors.phone = 'Vui lòng nhập số điện thoại hợp lệ'
  }
  return errors
}

export function CandidateProfileForm() {
  const [values, setValues] = useState<FormValues>({
    full_name: '',
    phone: '',
    title: '',
  })
  const [errors, setErrors] = useState<FormErrors>({})
  const [isLoading, setIsLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [apiError, setApiError] = useState<string | null>(null)
  const [success, setSuccess] = useState(false)
  const [submitting, setSubmitting] = useState(false)

  const loadProfile = async () => {
    setIsLoading(true)
    setLoadError(null)
    try {
      const profile = await getCandidateProfile()
      setValues({
        full_name: profile.full_name ?? '',
        phone: profile.phone ?? '',
        title: profile.title ?? '',
      })
    } catch (error) {
      if (!isNotFoundError(error)) {
        setLoadError(getFriendlyErrorMessage(error))
      }
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    void loadProfile()
  }, [])

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
      await updateCandidateProfile({
        full_name: values.full_name.trim() || null,
        phone: values.phone.trim() || null,
        title: values.title.trim() || null,
      })
      setSuccess(true)
    } catch (error) {
      setApiError(getFriendlyErrorMessage(error))
    } finally {
      setSubmitting(false)
    }
  }

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-10 w-full" />
      </div>
    )
  }

  if (loadError != null) {
    return (
      <ErrorBanner
        message={loadError}
        onRetry={() => void loadProfile()}
      />
    )
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4" noValidate>
      <Input
        name="full_name"
        label="Họ và tên"
        placeholder="Nguyễn Văn An"
        value={values.full_name}
        onChange={(e) =>
          setValues((v) => ({ ...v, full_name: e.target.value }))
        }
      />
      <Input
        name="phone"
        label="Số điện thoại"
        placeholder="+84 900 123 456"
        value={values.phone}
        onChange={(e) => setValues((v) => ({ ...v, phone: e.target.value }))}
        error={errors.phone}
      />
      <Input
        name="title"
        label="Vị trí / Chức danh"
        placeholder="Senior Frontend Engineer"
        value={values.title}
        onChange={(e) => setValues((v) => ({ ...v, title: e.target.value }))}
      />

      {apiError ? (
        <p role="alert" className="text-sm font-medium text-destructive">
          {apiError}
        </p>
      ) : null}

      {success ? (
        <p role="status" className="text-sm font-medium text-success">
          Đã lưu hồ sơ ứng viên.
        </p>
      ) : null}

      <Button type="submit" className="w-full" isLoading={submitting}>
        Lưu hồ sơ
      </Button>
    </form>
  )
}