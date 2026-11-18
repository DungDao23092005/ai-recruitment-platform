import { useState, type FormEvent, useRef, useCallback } from 'react'
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
import { forgotPassword, verifyResetOtp } from '@/api/auth'

interface FormValues {
  otp: string
}

interface FormErrors {
  otp?: string
}

export function validate(values: FormValues) {
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
  const [resendNotice, setResendNotice] = useState<string | null>(null)
  const [success, setSuccess] = useState(false)
  const [resetToken, setResetToken] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [resending, setResending] = useState(false)

  const inputRefs = useRef<(HTMLInputElement | null)[]>([])
  // Synchronous guard: blocks duplicate resend requests before React state
  // updates (and before any await) can re-enable the button.
  const resendInFlightRef = useRef(false)

  const focusInput = useCallback((index: number) => {
    if (index >= 0 && index < 6 && inputRefs.current[index]) {
      inputRefs.current[index]?.focus()
    }
  }, [])

  const handleInputChange = (index: number, value: string) => {
    // Only allow numeric digits
    const numericValue = value.replace(/\D/g, '')
    if (numericValue.length > 1) {
      // If pasting, only take first character for this input
      const newOtp = values.otp.slice(0, index) + numericValue[0] + values.otp.slice(index + 1)
      setValues({ otp: newOtp })
      if (index < 5) {
        focusInput(index + 1)
      }
      return
    }

    const newOtp = values.otp.slice(0, index) + numericValue + values.otp.slice(index + 1)
    setValues({ otp: newOtp })

    if (numericValue && index < 5) {
      focusInput(index + 1)
    }

    // Auto-submit when all 6 digits are filled
    if (newOtp.length === 6 && /^\d{6}$/.test(newOtp)) {
      const form = document.querySelector('form')
      if (form) {
        form.requestSubmit()
      }
    }
  }

  const handleKeyDown = (index: number, event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Backspace') {
      if (!values.otp[index] && index > 0) {
        // Current input is empty, move to previous
        event.preventDefault()
        const newOtp = values.otp.slice(0, index - 1) + values.otp.slice(index)
        setValues({ otp: newOtp })
        focusInput(index - 1)
      }
    } else if (event.key === 'ArrowLeft' && index > 0) {
      event.preventDefault()
      focusInput(index - 1)
    } else if (event.key === 'ArrowRight' && index < 5) {
      event.preventDefault()
      focusInput(index + 1)
    }
  }

  const handlePaste = (index: number, event: React.ClipboardEvent<HTMLInputElement>) => {
    event.preventDefault()
    const pastedText = event.clipboardData.getData('text')
    const numericText = pastedText.replace(/\D/g, '').slice(0, 6 - index)

    if (!numericText) return

    // Distribute pasted digits across inputs starting from current index
    const newOtpChars = values.otp.split('')
    for (let i = 0; i < numericText.length && index + i < 6; i++) {
      newOtpChars[index + i] = numericText[i]
    }
    const newOtp = newOtpChars.join('')
    setValues({ otp: newOtp })

    // Focus the next empty input or the last one
    const nextEmptyIndex = newOtp.indexOf('')
    if (nextEmptyIndex !== -1) {
      focusInput(nextEmptyIndex)
    } else {
      focusInput(5)
      // Auto-submit if all filled
      const form = document.querySelector('form')
      if (form) {
        form.requestSubmit()
      }
    }
  }

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    if (resending) return
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
    // Synchronous guards: ignore duplicate clicks and clicks while an OTP
    // verification is in flight.
    if (resendInFlightRef.current || submitting) return

    if (!email) {
      setResendNotice(null)
      setApiError('Không xác định được email để gửi lại mã OTP. Vui lòng quay lại bước trước.')
      return
    }

    resendInFlightRef.current = true
    setResending(true)
    setApiError(null)
    setResendNotice(null)
    try {
      await forgotPassword(email)
      setValues({ otp: '' })
      // The backend returns the same generic response for unknown accounts,
      // cooldown and transport failures. Never claim delivery was confirmed.
      setResendNotice(
        'Yêu cầu đã được xử lý. Nếu tài khoản tồn tại, bạn sẽ nhận được một mã OTP mới qua email.',
      )
      // Focus first input after resend
      setTimeout(() => focusInput(0), 0)
    } catch (error) {
      setApiError(getFriendlyErrorMessage(error))
    } finally {
      resendInFlightRef.current = false
      setResending(false)
    }
  }

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
                ref={(el) => { inputRefs.current[i] = el }}
                type="text"
                maxLength={1}
                inputMode="numeric"
                pattern="[0-9]*"
                value={values.otp[i] || ''}
                onChange={(e) => handleInputChange(i, e.target.value)}
                onKeyDown={(e) => handleKeyDown(i, e)}
                onPaste={(e) => handlePaste(i, e)}
                className="text-center text-2xl font-mono tracking-widest"
                autoComplete="one-time-code"
                autoFocus={i === 0}
                disabled={submitting || resending}
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

          <Button type="submit" className="w-full" isLoading={submitting} disabled={values.otp.length !== 6 || resending}>
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
            disabled={submitting || resending}
          >
            {resending ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                Đang gửi...
              </>
            ) : (
              <>
                <RotateCcw className="h-4 w-4" aria-hidden="true" />
                Gửi lại mã OTP
              </>
            )}
          </Button>
          {resendNotice && (
            <p role="status" className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
              <CheckCircle className="h-4 w-4" aria-hidden="true" />
              {resendNotice}
            </p>
          )}
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