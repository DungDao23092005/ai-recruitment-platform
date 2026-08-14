import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { register as registerApi } from '@/api/auth'
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
    errors.email = 'Email is required'
  } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(values.email.trim())) {
    errors.email = 'Enter a valid email address'
  }

  if (!values.password) {
    errors.password = 'Password is required'
  } else if (values.password.length < 8) {
    errors.password = 'Password must be at least 8 characters'
  }

  if (!values.confirmPassword) {
    errors.confirmPassword = 'Please confirm your password'
  } else if (values.confirmPassword !== values.password) {
    errors.confirmPassword = 'Passwords do not match'
  }

  if (!values.role) {
    errors.role = 'Please select a role'
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
      setErrors({ role: 'Please select a valid role' })
      return
    }

    setSubmitting(true)
    try {
      await registerApi({
        email: values.email.trim(),
        password: values.password,
        role: values.role,
      })
      navigate('/login', { replace: true })
    } catch (error) {
      setApiError(getFriendlyErrorMessage(error))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Card className="w-full">
      <CardHeader>
        <CardTitle>Create account</CardTitle>
        <CardDescription>
          Register as a candidate or recruiter to get started.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-4" noValidate>
          <Input
            type="email"
            name="email"
            label="Email"
            placeholder="you@example.com"
            autoComplete="email"
            value={values.email}
            onChange={(e) => setValues((v) => ({ ...v, email: e.target.value }))}
            error={errors.email}
          />
          <Input
            type="password"
            name="password"
            label="Password"
            autoComplete="new-password"
            value={values.password}
            onChange={(e) => setValues((v) => ({ ...v, password: e.target.value }))}
            error={errors.password}
          />
          <Input
            type="password"
            name="confirmPassword"
            label="Confirm password"
            autoComplete="new-password"
            value={values.confirmPassword}
            onChange={(e) =>
              setValues((v) => ({ ...v, confirmPassword: e.target.value }))
            }
            error={errors.confirmPassword}
          />

          <div className="flex flex-col gap-1.5">
            <label htmlFor="role" className="text-sm font-medium leading-none">
              Role
            </label>
            <select
              id="role"
              name="role"
              value={values.role}
              onChange={(e) =>
                setValues((v) => ({
                  ...v,
                  role: e.target.value as UserRole,
                }))
              }
              aria-invalid={errors.role ? true : undefined}
              className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
            >
              <option value="">Select a role</option>
              <option value="candidate">Candidate</option>
              <option value="recruiter">Recruiter</option>
            </select>
            {errors.role ? (
              <span className="text-xs font-medium text-destructive">
                {errors.role}
              </span>
            ) : null}
          </div>

          {apiError ? (
            <p role="alert" className="text-sm font-medium text-destructive">
              {apiError}
            </p>
          ) : null}

          <Button type="submit" className="w-full" isLoading={submitting}>
            Create account
          </Button>
        </form>

        <p className="mt-4 text-center text-sm text-muted-foreground">
          Already have an account?{' '}
          <Link to="/login" className="text-primary underline underline-offset-4">
            Sign in
          </Link>
        </p>
      </CardContent>
    </Card>
  )
}