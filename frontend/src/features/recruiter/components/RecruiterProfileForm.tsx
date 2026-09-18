import { useEffect, useState, type FormEvent } from 'react'
import {
  getRecruiterProfile,
  updateRecruiterProfile,
} from '@/api/auth'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { ErrorBanner } from '@/components/ui/error-banner'
import { getFriendlyErrorMessage } from '@/utils/errors'

interface FormValues {
  full_name: string
  position: string
}

function isNotFoundError(error: unknown): boolean {
  return (
    typeof error === 'object' &&
    error !== null &&
    'response' in error &&
    (error as { response?: { status?: number } }).response?.status === 404
  )
}

export function RecruiterProfileForm() {
  const [values, setValues] = useState<FormValues>({
    full_name: '',
    position: '',
  })
  const [isLoading, setIsLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [apiError, setApiError] = useState<string | null>(null)
  const [success, setSuccess] = useState(false)
  const [submitting, setSubmitting] = useState(false)

  const loadProfile = async () => {
    setIsLoading(true)
    setLoadError(null)
    try {
      const profile = await getRecruiterProfile()
      setValues({
        full_name: profile.full_name ?? '',
        position: profile.position ?? '',
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

    setSubmitting(true)
    try {
      await updateRecruiterProfile({
        full_name: values.full_name.trim() || null,
        position: values.position.trim() || null,
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
        placeholder="Trần Thị Bích"
        value={values.full_name}
        onChange={(e) =>
          setValues((v) => ({ ...v, full_name: e.target.value }))
        }
      />
      <Input
        name="position"
        label="Vị trí"
        placeholder="Trưởng phòng Tuyển dụng"
        value={values.position}
        onChange={(e) => setValues((v) => ({ ...v, position: e.target.value }))}
      />

      {apiError ? (
        <p role="alert" className="text-sm font-medium text-destructive">
          {apiError}
        </p>
      ) : null}

      {success ? (
        <p role="status" className="text-sm font-medium text-success">
          Đã lưu hồ sơ nhà tuyển dụng.
        </p>
      ) : null}

      <Button type="submit" className="w-full" isLoading={submitting}>
        Lưu hồ sơ
      </Button>
    </form>
  )
}