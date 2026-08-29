import { useState, type FormEvent } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { LogIn, AlertCircle } from 'lucide-react'
import { useAuth } from '@/contexts/AuthContext'
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

interface FormValues {
  email: string
  password: string
}

interface FormErrors {
  email?: string
  password?: string
}

function validate(values: FormValues): FormErrors {
  const errors: FormErrors = {}
  if (!values.email.trim()) {
    errors.email = 'Email không được để trống'
  } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(values.email.trim())) {
    errors.email = 'Vui lòng nhập địa chỉ email hợp lệ'
  }
  if (!values.password) {
    errors.password = 'Mật khẩu không được để trống'
  }
  return errors
}

function homeForRole(role: string): string {
  if (role === 'candidate') return '/candidate/portal'
  if (role === 'recruiter') return '/recruiter/portal'
  return '/admin/dashboard'
}

export function LoginPage() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()

  const [values, setValues] = useState<FormValues>({ email: '', password: '' })
  const [errors, setErrors] = useState<FormErrors>({})
  const [apiError, setApiError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const from = (location.state as { from?: string } | null)?.from
  const justRegistered = (location.state as { registered?: boolean } | null)
    ?.registered

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
      const user = await login({
        email: values.email.trim(),
        password: values.password,
      })
      navigate(from ?? homeForRole(user.role), { replace: true })
    } catch (error) {
      setApiError(getFriendlyErrorMessage(error))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Card className="w-full shadow-soft">
      <CardHeader>
        <CardTitle className="font-display text-xl font-bold">
          Đăng nhập
        </CardTitle>
        <CardDescription>
          Đăng nhập để tiếp tục sử dụng nền tảng tuyển dụng AI.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {justRegistered ? (
          <p
            role="status"
            className="mb-4 rounded-md bg-success/10 px-3 py-2 text-sm font-medium text-success"
          >
            Tạo tài khoản thành công. Vui lòng đăng nhập để tiếp tục.
          </p>
        ) : null}

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
          <Input
            type="password"
            name="password"
            label="Mật khẩu"
            autoComplete="current-password"
            value={values.password}
            onChange={(e) =>
              setValues((v) => ({ ...v, password: e.target.value }))
            }
            error={errors.password}
          />

          {apiError ? (
            <div role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm font-medium text-destructive">
              <div className="flex items-center gap-2">
                <AlertCircle className="h-4 w-4" aria-hidden="true" />
                <span>{apiError}</span>
              </div>
            </div>
          ) : null}

          <Button type="submit" className="w-full" isLoading={submitting}>
            <LogIn className="h-4 w-4" aria-hidden="true" />
            Đăng nhập
          </Button>
        </form>

        <div className="mt-4 space-y-2 text-center text-sm text-muted-foreground">
          <p>
            Chưa có tài khoản?{' '}
            <Link
              to="/register"
              className="font-medium text-primary underline underline-offset-4"
            >
              Đăng ký ngay
            </Link>
          </p>
          <p>
            <Link
              to="/forgot-password"
              className="font-medium text-primary underline underline-offset-4"
            >
              Quên mật khẩu?
            </Link>
          </p>
        </div>
      </CardContent>
    </Card>
  )
}