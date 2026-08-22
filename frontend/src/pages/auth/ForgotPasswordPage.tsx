import { useState, type FormEvent, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { Mail, Loader2, AlertCircle, CheckCircle } from 'lucide-react'
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
import { forgotPassword } from '@/api/auth'

interface FormValues {
  email: string
}

interface FormErrors {
  email?: string
}

function validate(values: FormValues) {
  const errors: FormErrors = {}
  if (!values.email.trim()) {
    errors.email = 'Email không được để trống'
  } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(values.email.trim())) {
    errors.email = 'Vui lòng nhập địa chỉ email hợp lệ'
  }
  return errors
}

export function ForgotPasswordPage() {
  const [values, setValues] = useState<FormValues>({ email: '' })
  const [errors, setErrors] = useState<FormErrors>({})
  const [apiError, setApiError] = useState<string | null>(null)
  const [success, setSuccess] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [cooldown, setCooldown] = useState(0)

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    setApiError(null)

    const validationErrors = validate(values)
    setErrors(validationErrors)
    if (Object.keys(validationErrors).length > 0) {
      return
    }

    if (cooldown > 0) {
      return
    }

    setSubmitting(true)
    try {
      await forgotPassword(values.email.trim())
      setSuccess(true)
      setCooldown(60)
      const timer = setInterval(() => {
        setCooldown((prev) => {
          if (prev <= 1) {
            clearInterval(timer)
            return 0
          }
          return prev - 1
        })
      }, 1000)
    } catch (error) {
      setApiError(getFriendlyErrorMessage(error))
    } finally {
      setSubmitting(false)
    }
  }

  useEffect(() => {
    if (cooldown > 0) {
      const timer = setInterval(() => {
        setCooldown((prev) => {
          if (prev <= 1) {
            clearInterval(timer)
            return 0
          }
          return prev - 1
        })
      }, 1000)
      return () => clearInterval(timer)
    }
  }, [cooldown])

  if (success) {
    return (
      <Card className="w-full shadow-soft">
        <CardHeader>
          <CardTitle className="font-display text-xl font-bold flex items-center gap-2">
            <CheckCircle className="h-5 w-5 text-success" aria-hidden="true" />
            Đã gửi email
          </CardTitle>
          <CardDescription>
            Nếu tài khoản tồn tại, mã OTP đã được gửi đến email của bạn.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">
            Vui lòng kiểm tra hộp thư đến (và thư rác) để lấy mã OTP 6 chữ số.
          </p>
          <p className="text-sm text-muted-foreground">
            Mã OTP có hiệu lực trong 5 phút.
          </p>
          <Link to="/verify-reset-otp" state={{ email: values.email }} className="block text-center">
            <Button variant="outline" className="w-full">
              Tiếp tục đến trang xác thực OTP
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
          <Mail className="h-5 w-5" aria-hidden="true" />
          Quên mật khẩu
        </CardTitle>
        <CardDescription>
          Nhập email đăng ký để nhận mã OTP đặt lại mật khẩu.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-4" noValidate>
          <Input
            type="email"
            name="email"
            label="Email"
            placeholder="ban@example.com"
            autoComplete="email"
            value={values.email}
            onChange={(e) => setValues((v) => ({ ...v, email: e.target.value }))}
            error={errors.email}
          />

          {cooldown > 0 && (
            <p className="text-sm text-muted-foreground">
              Vui lòng đợi {cooldown}s trước khi gửi lại
            </p>
          )}

          {apiError && (
            <p role="alert" className="flex items-center gap-2 text-sm font-medium text-destructive">
              <AlertCircle className="h-4 w-4" aria-hidden="true" />
              {apiError}
            </p>
          )}

          <Button type="submit" className="w-full" isLoading={submitting} disabled={cooldown > 0}>
            {submitting ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                Đang gửi...
              </>
            ) : cooldown > 0 ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                Gửi lại sau {cooldown}s
              </>
            ) : (
              <>
                <Mail className="h-4 w-4" aria-hidden="true" />
                Gửi mã OTP
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