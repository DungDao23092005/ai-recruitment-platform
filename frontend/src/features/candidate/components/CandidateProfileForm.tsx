import { useEffect, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { FileText, ArrowRight } from 'lucide-react'
import { getCandidateProfile, updateCandidateProfile } from '@/api/auth'
import { useAuth } from '@/contexts/AuthContext'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { ErrorBanner } from '@/components/ui/error-banner'
import { getFriendlyErrorMessage } from '@/utils/errors'
import { cn } from '@/utils/cn'

export const TITLE_PRESETS = [
  'Frontend Developer',
  'Backend Developer',
  'Full Stack Developer',
  'DevOps Engineer',
  'Data / AI Engineer',
] as const

interface FormValues {
  full_name: string
  phone: string
  title: string
}

interface FormErrors {
  full_name?: string
  phone?: string
}

export function getInitials(name?: string | null, email?: string | null): string {
  const trimmedName = name?.trim()
  if (trimmedName) {
    const parts = trimmedName.split(/\s+/).filter(Boolean)
    if (parts.length >= 2) {
      const firstChar = Array.from(parts[0])[0] || ''
      const lastChar = Array.from(parts[parts.length - 1])[0] || ''
      return (firstChar + lastChar).toUpperCase()
    }
    if (parts.length === 1 && parts[0].length > 0) {
      return (Array.from(parts[0])[0] || '').toUpperCase()
    }
  }
  const trimmedEmail = email?.trim()
  if (trimmedEmail && trimmedEmail.length > 0) {
    const localPart = trimmedEmail.split('@')[0]
    if (localPart.length > 0) {
      return (Array.from(localPart)[0] || '').toUpperCase()
    }
  }
  return '?'
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
  if (!values.full_name.trim()) {
    errors.full_name = 'Vui lòng nhập họ và tên'
  }
  if (values.phone && !/^[0-9+\-() ]+$/.test(values.phone)) {
    errors.phone = 'Vui lòng nhập số điện thoại hợp lệ'
  }
  return errors
}

export function CandidateProfileForm() {
  const { currentUser } = useAuth()

  const [values, setValues] = useState<FormValues>({
    full_name: '',
    phone: '',
    title: '',
  })
  const [initialValues, setInitialValues] = useState<FormValues>({
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
      const loaded: FormValues = {
        full_name: profile.full_name ?? '',
        phone: profile.phone ?? '',
        title: profile.title ?? '',
      }
      setValues(loaded)
      setInitialValues(loaded)
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
      const trimmedFullName = values.full_name.trim()
      const trimmedPhone = values.phone.trim()
      const trimmedTitle = values.title.trim()

      await updateCandidateProfile({
        full_name: trimmedFullName || null,
        phone: trimmedPhone || null,
        title: trimmedTitle || null,
      })

      const saved: FormValues = {
        full_name: trimmedFullName,
        phone: trimmedPhone,
        title: trimmedTitle,
      }
      setValues(saved)
      setInitialValues(saved)
      setSuccess(true)
    } catch (error) {
      setApiError(getFriendlyErrorMessage(error))
    } finally {
      setSubmitting(false)
    }
  }

  const isDirty =
    values.full_name !== initialValues.full_name ||
    values.phone !== initialValues.phone ||
    values.title !== initialValues.title

  const userEmail = currentUser?.email || '—'
  const roleName =
    currentUser?.role === 'candidate'
      ? 'Ứng viên'
      : currentUser?.role || 'Ứng viên'

  const initials = getInitials(values.full_name, currentUser?.email)

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-20 w-full rounded-xl" />
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
    <div className="space-y-6">
      {/* Candidate Identity Summary Card */}
      <div className="flex flex-col sm:flex-row items-center sm:items-start gap-4 rounded-xl border border-border/70 bg-muted/30 p-5">
        <div
          className="flex h-16 w-16 shrink-0 items-center justify-center rounded-full border border-primary/20 bg-primary/10 font-display text-xl font-bold text-primary select-none shadow-xs"
          aria-label={`Ảnh đại diện viết tắt: ${initials}`}
          data-testid="initials-avatar"
        >
          {initials}
        </div>
        <div className="flex-1 space-y-1.5 text-center sm:text-left min-w-0">
          <div className="flex flex-wrap items-center justify-center sm:justify-start gap-2">
            <h3 className="font-display text-lg font-bold text-foreground truncate">
              {values.full_name.trim() || 'Chưa cập nhật họ tên'}
            </h3>
            <Badge variant="outline-ai" className="text-xs">
              Ứng viên
            </Badge>
          </div>
          <p className="text-sm font-medium text-muted-foreground truncate">
            {values.title.trim() || 'Chưa cập nhật chức danh mục tiêu'}
          </p>
          <p className="text-xs text-muted-foreground truncate">
            {userEmail}
          </p>
        </div>
      </div>

      {/* Section 1: Account Information (Read-Only) */}
      <div className="space-y-3 pt-1">
        <h4 className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
          THÔNG TIN TÀI KHOẢN
        </h4>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div className="rounded-xl border border-border/60 bg-muted/20 p-3.5 space-y-1">
            <span className="text-xs font-medium text-muted-foreground">Email đăng nhập</span>
            <p className="text-sm font-semibold text-foreground truncate" title={userEmail}>
              {userEmail}
            </p>
            <p className="text-xs text-muted-foreground">
              Email dùng để đăng nhập và nhận thông báo từ hệ thống.
            </p>
          </div>

          <div className="rounded-xl border border-border/60 bg-muted/20 p-3.5 space-y-1">
            <span className="text-xs font-medium text-muted-foreground">Vai trò tài khoản</span>
            <p className="text-sm font-semibold text-foreground truncate" title={roleName}>
              {roleName}
            </p>
            <p className="text-xs text-muted-foreground">
              Vai trò hiện tại của tài khoản trên nền tảng.
            </p>
          </div>
        </div>
      </div>

      {/* Form Sections */}
      <form onSubmit={handleSubmit} className="space-y-6 pt-1" noValidate>
        {/* Section 2: Personal Information */}
        <div className="space-y-4">
          <h4 className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
            THÔNG TIN CÁ NHÂN & LIÊN HỆ
          </h4>

          <Input
            name="full_name"
            label="Họ và tên"
            placeholder="Nguyễn Văn An"
            helperText="Tên hiển thị với nhà tuyển dụng trong hồ sơ ứng tuyển."
            required
            maxLength={255}
            value={values.full_name}
            onChange={(e) => {
              setValues((v) => ({ ...v, full_name: e.target.value }))
              setErrors((err) => ({ ...err, full_name: undefined }))
              setSuccess(false)
              setApiError(null)
            }}
            error={errors.full_name}
          />

          <Input
            name="phone"
            label="Số điện thoại"
            placeholder="+84 900 123 456"
            helperText="Số điện thoại để nhà tuyển dụng liên hệ khi cần trao đổi hoặc mời phỏng vấn."
            maxLength={50}
            value={values.phone}
            onChange={(e) => {
              setValues((v) => ({ ...v, phone: e.target.value }))
              setErrors((err) => ({ ...err, phone: undefined }))
              setSuccess(false)
              setApiError(null)
            }}
            error={errors.phone}
          />
        </div>

        {/* Section 3: Career Orientation */}
        <div className="space-y-4">
          <h4 className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
            ĐỊNH HƯỚNG NGHỀ NGHIỆP
          </h4>

          <div className="space-y-2">
            <Input
              name="title"
              label="Vị trí / Chức danh mục tiêu"
              placeholder="Frontend Developer"
              helperText="Chức danh chuyên môn hoặc vị trí bạn đang tìm kiếm."
              maxLength={255}
              value={values.title}
              onChange={(e) => {
                setValues((v) => ({ ...v, title: e.target.value }))
                setSuccess(false)
                setApiError(null)
              }}
            />

            <div className="space-y-1.5 pt-1">
              <span className="text-xs font-medium text-muted-foreground">
                Gợi ý chức danh:
              </span>
              <div
                className="flex flex-wrap gap-2"
                role="group"
                aria-label="Gợi ý chức danh mục tiêu"
              >
                {TITLE_PRESETS.map((preset) => {
                  const isSelected = values.title.trim() === preset
                  return (
                    <button
                      key={preset}
                      type="button"
                      onClick={() => {
                        setValues((v) => ({ ...v, title: preset }))
                        setSuccess(false)
                        setApiError(null)
                      }}
                      className={cn(
                        'inline-flex items-center rounded-full px-3 py-1 text-xs font-medium transition-colors cursor-pointer select-none',
                        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
                        isSelected
                          ? 'bg-primary text-primary-foreground shadow-xs font-semibold'
                          : 'border border-border/80 bg-muted/50 text-muted-foreground hover:bg-muted hover:text-foreground',
                      )}
                      aria-pressed={isSelected}
                    >
                      {preset}
                    </button>
                  )
                })}
              </div>
            </div>
          </div>
        </div>

        {/* Section 4: CV and AI Matching Context Card */}
        <div className="rounded-xl border border-primary/20 bg-primary/5 p-4 sm:p-5 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div className="flex items-start gap-3 min-w-0">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <FileText className="h-5 w-5" aria-hidden="true" />
            </div>
            <div className="space-y-1 min-w-0">
              <h4 className="text-sm font-semibold text-foreground">
                Quản lý CV & Hồ sơ ứng tuyển
              </h4>
              <p className="text-xs text-muted-foreground leading-relaxed">
                Tải lên CV để hệ thống phân tích kỹ năng, kinh nghiệm và đề xuất các vị trí tuyển dụng phù hợp.
              </p>
            </div>
          </div>
          <Link
            to="/candidate/cv-upload"
            className="inline-flex items-center gap-1.5 whitespace-nowrap rounded-lg bg-primary px-3.5 py-2 text-xs font-semibold text-primary-foreground shadow-xs hover:bg-primary/90 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 shrink-0 self-start sm:self-auto"
          >
            <span>Quản lý CV</span>
            <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
          </Link>
        </div>

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

        <div className="flex flex-col-reverse gap-3 pt-2 sm:flex-row sm:justify-end">
          <Button
            type="button"
            variant="outline"
            disabled={!isDirty || submitting}
            onClick={() => {
              setValues(initialValues)
              setErrors({})
              setApiError(null)
              setSuccess(false)
            }}
          >
            Hủy thay đổi
          </Button>
          <Button
            type="submit"
            isLoading={submitting}
            disabled={submitting}
          >
            Lưu hồ sơ
          </Button>
        </div>
      </form>
    </div>
  )
}
