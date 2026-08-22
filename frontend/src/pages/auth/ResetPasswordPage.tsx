import { useState, type FormEvent } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { Loader2, AlertCircle, CheckCircle, Eye, EyeOff, Mail, Lock } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { getFriendlyErrorMessage } from '@/utils/errors'
import { resetPassword } from '@/api/auth'
import { cn } from '@/utils/cn'

interface FormValues {
  new_password: string
  confirm_password: string
}

interface FormErrors {
  new_password?: string
  confirm_password?: string
}

function validate(values: FormValues) {
  const errors: FormErrors = {}
  if (!values.new_password) {
    errors.new_password = 'Mật khẩu mới không được để trống'
  } else if (values.new_password.length < 8) {
    errors.new_password = 'Mật khẩu phải có ít nhất 8 ký tự'
  }
  if (!values.confirm_password) {
    errors.confirm_password = 'Vui lòng xác nhận mật khẩu'
  } else if (values.new_password !== values.confirm_password) {
    errors.confirm_password = 'Mật khẩu xác nhận không khớp'
  }
  return errors
}

export function ResetPasswordPage() {
  const location = useLocation()

  // Get reset_token and email from navigation state
  const resetToken = (location.state as { resetToken?: string } | null)?.resetToken ?? ''
  const email = (location.state as { email?: string } | null)?.email ?? ''

  const [values, setValues] = useState<FormValues>({ new_password: '', confirm_password: '' })
  const [errors, setErrors] = useState<FormErrors>({})
  const [apiError, setApiError] = useState<string | null>(null)
  const [success, setSuccess] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [showPassword, setShowPassword] = useState(false)

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    setApiError(null)

    const validationErrors = validate(values)
    setErrors(validationErrors)
    if (Object.keys(validationErrors).length > 0) {
      return
    }

    if (!resetToken) {
      setApiError('Mã đặt lại mật khẩu không hợp lệ. Vui lòng thử lại từ đầu.')
      return
    }

    setSubmitting(true)
    try {
      await resetPassword(email, resetToken, values.new_password)
      setSuccess(true)
    } catch (error) {
      setApiError(getFriendlyErrorMessage(error))
    } finally {
      setSubmitting(false)
    }
  }

  if (success) {
    return (
      <Card className="w-full shadow-soft">
        <CardHeader>
          <CardTitle className="font-display text-xl font-bold flex items-center gap-2">
            <CheckCircle className="h-5 w-5 text-success" aria-hidden="true" />
            Đặt lại mật khẩu thành công
          </CardTitle>
          <CardDescription>
            Mật khẩu của bạn đã được cập nhật. Vui lòng đăng nhập lại với mật khẩu mới.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">
            Mật khẩu cũ của bạn không còn hoạt động. Tất cả các phiên đăng nhập khác đã bị đăng xuất.
          </p>
          <Link to="/login" className="block text-center">
            <Button className="w-full">
              <Mail className="h-4 w-4 mr-2" aria-hidden="true" />
              Đăng nhập ngay
            </Button>
          </Link>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card className="w-full shadow-soft">
      <CardHeader>
        <CardTitle className="font-display text-xl font-bold flex items-center gap-2">
          <Lock className="h-5 w-5" aria-hidden="true" />
          Đặt lại mật khẩu
        </CardTitle>
        <CardDescription>
          Nhập mật khẩu mới cho tài khoản của bạn.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-4" noValidate>
          <div className="relative">
            <Input
              type={showPassword ? 'text' : 'password'}
              name="new_password"
              label="Mật khẩu mới"
              placeholder="Nhập mật khẩu mới"
              autoComplete="new-password"
              value={values.new_password}
              onChange={(e) => setValues((v) => ({ ...v, new_password: e.target.value }))}
              error={errors.new_password}
            />
            <button
              type="button"
              onClick={() => setShowPassword(!showPassword)}
              className={cn('absolute right-3 top-[38px] text-muted-foreground hover:text-foreground', showPassword && 'text-primary')}
              aria-label={showPassword ? 'Ẩn mật khẩu' : 'Hiện mật khẩu'}
            >
              {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
            </button>
          </div>

          <div className="relative">
            <Input
              type={showPassword ? 'text' : 'password'}
              name="confirm_password"
              label="Xác nhận mật khẩu mới"
              placeholder="Nhập lại mật khẩu mới"
              autoComplete="new-password"
              value={values.confirm_password}
              onChange={(e) => setValues((v) => ({ ...v, confirm_password: e.target.value }))}
              error={errors.confirm_password}
            />
            <button
              type="button"
              onClick={() => setShowPassword(!showPassword)}
              className={cn('absolute right-3 top-[38px] text-muted-foreground hover:text-foreground', showPassword && 'text-primary')}
              aria-label={showPassword ? 'Ẩn mật khẩu' : 'Hiện mật khẩu'}
            >
              {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
            </button>
          </div>

          {apiError && (
            <p role="alert" className="flex items-center gap-2 text-sm font-medium text-destructive">
              <AlertCircle className="h-4 w-4" aria-hidden="true" />
              {apiError}
            </p>
          )}

          <Button type="submit" className="w-full" isLoading={submitting}>
            {submitting ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                Đang cập nhật...
              </>
            ) : (
              <>
                <Lock className="h-4 w-4" aria-hidden="true" />
                Cập nhật mật khẩu
              </>
            )}
          </Button>
        </form>

        <p className="mt-4 text-center text-sm text-muted-foreground">
          Nhớ mật khẩu?{' '}
          <Link
            to="/login"
            className="font-medium text-primary underline underline-offset-4"
          >
            Đăng nhập
          </Link>
        </p>
      </CardContent>
    </Card>
  )
}

interface FormValues {
  new_password: string
  confirm_password: string
}

interface FormErrors {
  new_password?: string
  confirm_password?: string
}