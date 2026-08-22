import { useState, type FormEvent, useEffect } from 'react'
import { Link, useNavigate, useLocation } from 'react-router-dom'
import { Loader2, AlertCircle, CheckCircle, Mail, RotateCcw } from 'lucide-react'
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
import { verifyResetOtp } from '@/api/auth'

interface FormValues {
  otp: string
}

interface FormErrors {
  otp?: string
}

function validate(values: FormValues) {
  const errors: FormErrors = {}
  if (!values.otp) {
    errors.otp = 'Mã OTP không được để trống'
  } else if (!/^\d{6}$/.test(values.otp)) {
    errors.otp = 'Mã OTP phải là 6 chữ số'
  }
  return errors
}

export function VerifyResetOtpPage() {
  const navigate = useNavigate()
  const location = useLocation()

  const email = (location.state as { email?: string } | null)?.email ?? ''

  const [values, setValues] = useState<FormValues>({ otp: '' })
  const [errors, setErrors] = useState<FormErrors>({})
  const [apiError, setApiError] = useState<string | null>(null)
  const [success, setSuccess] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [cooldown, setCooldown] = useState(0)
  const [resetToken, setResetToken] = useState<string | null>(null)

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    setApiError(null)

    const validationErrors = validate(values)
    setErrors(validationErrors)
    if (Object.keys(validationErrors).length > 0) {
      return
    }

    setSubmitting(true)
    try {
      const result = await verifyResetOtp(email, values.otp)
      setResetToken(result.reset_token)
      setSuccess(true)
    } catch (error) {
      setApiError(getFriendlyErrorMessage(error))
    } finally {
      setSubmitting(false)
    }
  }

  const handleResend = async () => {
    if (cooldown > 0) return
    
    setApiError(null)
    setSubmitting(true)
    try {
      // The actual resend logic would be handled by navigating back to forgot password
      // For now, we just reset the form
      setValues({ otp: '' })
      setApiError(null)
      setCooldown(60)
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
            return 0
          }
          return prev - 1
        })
      }, 1000)
      return () => clearInterval(timer)
    }
  }, [cooldown])

  if (success && resetToken) {
    return (
      <Card className="w-full shadow-soft">
        <CardHeader>
          <CardTitle className="font-display text-xl font-bold flex items-center gap-2">
            <CheckCircle className="h-5 w-5 text-success" aria-hidden="true" />
            Xác thực thành công
          </CardTitle>
          <CardDescription>
            Mã OTP hợp lệ. Đang chuyển hướng đến trang đặt lại mật khẩu...
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="p-4 rounded-md bg-muted/50 font-mono text-sm break-all">
            {resetToken}
          </div>
          <p className="text-sm text-muted-foreground">
            Mã đặt lại mật khẩu có hiệu lực trong 15 phút. Vui lòng không chia sẻ mã này.
          </p>
          <Button
            className="w-full"
            onClick={() =>
              navigate('/reset-password', {
                state: { resetToken, email },
              })
            }
          >
            Tiếp tục đặt lại mật khẩu
          </Button>
        </CardContent>
      </Card>
    )
  }

  const handleAutoSubmit = (index: number, value: string) => {
    const newOtp = values.otp.slice(0, index) + value + values.otp.slice(index + 1)
    setValues({ otp: newOtp })
    
    if (newOtp.length === 6 && /^\d{6}$/.test(newOtp)) {
      // Use form.submit() instead of synthetic event
      const form = document.querySelector('form')
      if (form) {
        form.requestSubmit()
      }
    }
  }

  return (
    <Card className="w-full shadow-soft">
      <CardHeader>
        <CardTitle className="font-display text-xl font-bold flex items-center gap-2">
          <Mail className="h-5 w-5" aria-hidden="true" />
          Xác thực mã OTP
        </CardTitle>
        <CardDescription>
          Nhập mã OTP 6 chữ số đã được gửi đến email của bạn.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <p className="mb-4 text-sm text-muted-foreground">
          Mã OTP đã được gửi đến <strong>{email || 'email của bạn'}</strong>. Mã có hiệu lực trong 5 phút.
        </p>

        <form onSubmit={handleSubmit} className="space-y-4" noValidate>
          <div className="grid grid-cols-6 gap-3" role="group" aria-label="Mã OTP 6 chữ số">
            {Array.from({ length: 6 }).map((_, i) => (
              <Input
                key={i}
                type="text"
                maxLength={1}
                inputMode="numeric"
                pattern="[0-9]*"
                value={values.otp[i] || ''}
                onChange={(e) => handleAutoSubmit(i, e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Backspace' && !values.otp[i] && i > 0) {
                    // Allow backspace to move to previous input
                  }
                }}
                className="text-center text-2xl font-mono tracking-widest"
                autoComplete="one-time-code"
                autoFocus={i === 0}
              />
            ))}
          </div>

          {errors.otp && (
            <p role="alert" className="flex items-center gap-2 text-sm font-medium text-destructive">
              <AlertCircle className="h-4 w-4" aria-hidden="true" />
              {errors.otp}
            </p>
          )}

          {apiError && (
            <p role="alert" className="flex items-center gap-2 text-sm font-medium text-destructive">
              <AlertCircle className="h-4 w-4" aria-hidden="true" />
              {apiError}
            </p>
          )}

          <Button type="submit" className="w-full" isLoading={submitting} disabled={values.otp.length !== 6}>
            {submitting ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                Đang xác thực...
              </>
            ) : (
              <>
                <Mail className="h-4 w-4" aria-hidden="true" />
                Xác thực
              </>
            )}
          </Button>
        </form>

        <div className="mt-6 pt-4 border-t space-y-3">
          <p className="text-sm text-muted-foreground text-center">
            Không nhận được mã OTP?
          </p>
          <Button
            variant="outline"
            className="w-full"
            onClick={handleResend}
            disabled={cooldown > 0 || submitting}
          >
            {cooldown > 0 ? (
              <>
                <RotateCcw className="h-4 w-4" aria-hidden="true" />
                Gửi lại sau {cooldown}s
              </>
            ) : (
              <>
                <RotateCcw className="h-4 w-4" aria-hidden="true" />
                Gửi lại mã OTP
              </>
            )}
          </Button>
        </div>

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