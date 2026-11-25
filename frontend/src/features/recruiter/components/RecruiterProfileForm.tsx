import { useEffect, useState, type FormEvent } from 'react'
import {
  getRecruiterProfile,
  updateRecruiterProfile,
} from '@/api/auth'
import { useAuth } from '@/contexts/AuthContext'
import { useOptionalWorkspace } from '@/contexts/WorkspaceContext'
import { MEMBERSHIP_ROLE_LABELS } from '@/types/workspace'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { ErrorBanner } from '@/components/ui/error-banner'
import { getFriendlyErrorMessage } from '@/utils/errors'
import { cn } from '@/utils/cn'

export const POSITION_PRESETS = [
  'Talent Acquisition',
  'HR Manager',
  'Technical Recruiter',
  'Hiring Manager',
  'Business Owner',
] as const

interface FormValues {
  full_name: string
  position: string
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

export function RecruiterProfileForm() {
  const { currentUser } = useAuth()
  const workspace = useOptionalWorkspace()
  const selectedWorkspace = workspace?.selectedWorkspace ?? null

  const [values, setValues] = useState<FormValues>({
    full_name: '',
    position: '',
  })
  const [initialValues, setInitialValues] = useState<FormValues>({
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
      const loaded: FormValues = {
        full_name: profile.full_name ?? '',
        position: profile.position ?? '',
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

    setSubmitting(true)
    try {
      const trimmedFullName = values.full_name.trim()
      const trimmedPosition = values.position.trim()

      await updateRecruiterProfile({
        full_name: trimmedFullName || null,
        position: trimmedPosition || null,
      })

      const saved: FormValues = {
        full_name: trimmedFullName,
        position: trimmedPosition,
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
    values.position !== initialValues.position

  const userEmail = currentUser?.email || '—'
  const companyName =
    selectedWorkspace?.company_name || 'Chưa liên kết doanh nghiệp'
  const roleName = selectedWorkspace?.role
    ? MEMBERSHIP_ROLE_LABELS[selectedWorkspace.role] || selectedWorkspace.role
    : 'Chưa có vai trò'

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
      {/* Identity Summary Card */}
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
              Nhà tuyển dụng
            </Badge>
            {selectedWorkspace?.company_name ? (
              <Badge variant="neutral" className="text-xs">
                {selectedWorkspace.company_name}
              </Badge>
            ) : null}
            {selectedWorkspace?.role ? (
              <Badge variant="outline-ai" className="text-xs">
                {roleName}
              </Badge>
            ) : null}
          </div>
          <p className="text-sm font-medium text-muted-foreground truncate">
            {values.position.trim() || 'Chưa cập nhật vị trí'}
          </p>
          <p className="text-xs text-muted-foreground truncate">
            {userEmail}
          </p>
        </div>
      </div>

      {/* Section 1: Account & Workspace Context */}
      <div className="space-y-3 pt-1">
        <h4 className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
          THÔNG TIN TÀI KHOẢN & DOANH NGHIỆP
        </h4>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 md:grid-cols-3">
          <div className="rounded-xl border border-border/60 bg-muted/20 p-3.5 space-y-1">
            <span className="text-xs font-medium text-muted-foreground">Email công việc</span>
            <p className="text-sm font-semibold text-foreground truncate" title={userEmail}>
              {userEmail}
            </p>
            <p className="text-xs text-muted-foreground">
              Email dùng để đăng nhập và nhận thông báo từ hệ thống.
            </p>
          </div>

          <div className="rounded-xl border border-border/60 bg-muted/20 p-3.5 space-y-1">
            <span className="text-xs font-medium text-muted-foreground">Doanh nghiệp trực thuộc</span>
            <p className="text-sm font-semibold text-foreground truncate" title={companyName}>
              {companyName}
            </p>
            <p className="text-xs text-muted-foreground">
              Doanh nghiệp trong workspace bạn đang sử dụng.
            </p>
          </div>

          <div className="rounded-xl border border-border/60 bg-muted/20 p-3.5 space-y-1 sm:col-span-2 md:col-span-1">
            <span className="text-xs font-medium text-muted-foreground">Vai trò trong workspace</span>
            <p className="text-sm font-semibold text-foreground truncate" title={roleName}>
              {roleName}
            </p>
            <p className="text-xs text-muted-foreground">
              Quyền hạn hiện tại của bạn trong workspace.
            </p>
          </div>
        </div>
      </div>

      {/* Section 2: Professional Information */}
      <form onSubmit={handleSubmit} className="space-y-5 pt-1" noValidate>
        <div className="space-y-4">
          <h4 className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
            THÔNG TIN CHUYÊN MÔN
          </h4>

          <Input
            name="full_name"
            label="Họ và tên"
            placeholder="Trần Thị Bích"
            helperText="Tên hiển thị với đồng nghiệp và trong các hoạt động tuyển dụng."
            required
            maxLength={255}
            value={values.full_name}
            onChange={(e) => {
              setValues((v) => ({ ...v, full_name: e.target.value }))
              setSuccess(false)
              setApiError(null)
            }}
          />

          <div className="space-y-2">
            <Input
              name="position"
              label="Vị trí"
              placeholder="Trưởng phòng Tuyển dụng"
              helperText="Chức danh chuyên môn hiện tại của bạn trong hoạt động tuyển dụng."
              maxLength={255}
              value={values.position}
              onChange={(e) => {
                setValues((v) => ({ ...v, position: e.target.value }))
                setSuccess(false)
                setApiError(null)
              }}
            />

            <div className="space-y-1.5 pt-1">
              <span className="text-xs font-medium text-muted-foreground">
                Gợi ý chức danh:
              </span>
              <div className="flex flex-wrap gap-2" role="group" aria-label="Gợi ý chức danh">
                {POSITION_PRESETS.map((preset) => {
                  const isSelected = values.position.trim() === preset
                  return (
                    <button
                      key={preset}
                      type="button"
                      onClick={() => {
                        setValues((v) => ({ ...v, position: preset }))
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

        <div className="flex flex-col-reverse gap-3 pt-2 sm:flex-row sm:justify-end">
          <Button
            type="button"
            variant="outline"
            disabled={!isDirty || submitting}
            onClick={() => {
              setValues(initialValues)
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