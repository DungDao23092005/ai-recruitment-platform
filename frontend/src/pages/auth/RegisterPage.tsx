import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { UserPlus } from 'lucide-react'
import { register as registerApi } from '@/api/auth'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { getFriendlyErrorMessage } from '@/utils/errors'
import { USER_ROLES } from '@/types'
import type { UserRole } from '@/types/auth'

interface FormValues {
  email: string
  password: string
  confirmPassword: string
  role: UserRole | ''
}

interface FormErrors {
  email?: string
  password?: string
  confirmPassword?: string
  role?: string
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
  } else if (values.password.length < 8) {
    errors.password = 'Mật khẩu phải có ít nhất 8 ký tự'
  }

  if (!values.confirmPassword) {
    errors.confirmPassword = 'Vui lòng xác nhận mật khẩu'
  } else if (values.confirmPassword !== values.password) {
    errors.confirmPassword = 'Mật khẩu xác nhận không khớp'
  }

  if (!values.role) {
    errors.role = 'Vui lòng chọn vai trò'
  }

  return errors
}

export function RegisterPage() {
  const navigate = useNavigate()
  const [values, setValues] = useState<FormValues>({
    email: '',
    password: '',
    confirmPassword: '',
    role: '',
  })
  const [errors, setErrors] = useState<FormErrors>({})
  const [apiError, setApiError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    setApiError(null)

    const validationErrors = validate(values)
    setErrors(validationErrors)
    if (Object.keys(validationErrors).length > 0) {
      return
    }

    if (values.role !== 'candidate' && values.role !== 'recruiter') {
      setErrors({ role: 'Vui lòng chọn vai trò hợp lệ' })
      return
    }

    setSubmitting(true)
    try {
      await registerApi({
        email: values.email.trim(),
        password: values.password,
        role: values.role,
      })
      navigate('/login', { replace: true, state: { registered: true } })
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
          Tạo tài khoản
        </CardTitle>
        <CardDescription>
          Đăng ký với tư cách ứng viên hoặc nhà tuyển dụng để bắt đầu.
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
          <Input
            type="password"
            name="password"
            label="Mật khẩu"
            autoComplete="new-password"
            value={values.password}
            onChange={(e) =>
              setValues((v) => ({ ...v, password: e.target.value }))
            }
            error={errors.password}
          />
          <Input
            type="password"
            name="confirmPassword"
            label="Xác nhận mật khẩu"
            autoComplete="new-password"
            value={values.confirmPassword}
            onChange={(e) =>
              setValues((v) => ({ ...v, confirmPassword: e.target.value }))
            }
            error={errors.confirmPassword}
          />

          <Select
            id="role"
            name="role"
            label="Vai trò"
            value={values.role}
            onChange={(e) =>
              setValues((v) => ({
                ...v,
                role: e.target.value as UserRole,
              }))
            }
            error={errors.role}
          >
            <option value="">Chọn vai trò</option>
            {USER_ROLES.filter((role) => role.value !== 'admin').map((role) => (
              <option key={role.value} value={role.value}>
                {role.label}
              </option>
            ))}
          </Select>

          {apiError ? (
            <p role="alert" className="text-sm font-medium text-destructive">
              {apiError}
            </p>
          ) : null}

          <Button type="submit" className="w-full" isLoading={submitting}>
            <UserPlus className="h-4 w-4" aria-hidden="true" />
            Tạo tài khoản
          </Button>
        </form>

        <p className="mt-4 text-center text-sm text-muted-foreground">
          Đã có tài khoản?{' '}
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