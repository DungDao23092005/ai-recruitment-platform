import { useState, type FormEvent } from 'react'
import { createCandidateProfile } from '@/api/auth'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { getFriendlyErrorMessage } from '@/utils/errors'

interface FormValues {
  full_name: string
  phone: string
  title: string
}

interface FormErrors {
  phone?: string
}

function validate(values: FormValues): FormErrors {
  const errors: FormErrors = {}
  if (values.phone && !/^[0-9+\-() ]+$/.test(values.phone)) {
    errors.phone = 'Enter a valid phone number'
  }
  return errors
}

export function CandidateProfileForm() {
  const [values, setValues] = useState<FormValues>({
    full_name: '',
    phone: '',
    title: '',
  })
  const [errors, setErrors] = useState<FormErrors>({})
  const [apiError, setApiError] = useState<string | null>(null)
  const [success, setSuccess] = useState(false)
  const [submitting, setSubmitting] = useState(false)

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
      await createCandidateProfile({
        full_name: values.full_name.trim() || null,
        phone: values.phone.trim() || null,
        title: values.title.trim() || null,
      })
      setSuccess(true)
    } catch (error) {
      setApiError(getFriendlyErrorMessage(error))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4" noValidate>
      <Input
        name="full_name"
        label="Full name"
        placeholder="John Doe"
        value={values.full_name}
        onChange={(e) => setValues((v) => ({ ...v, full_name: e.target.value }))}
      />
      <Input
        name="phone"
        label="Phone"
        placeholder="+84 900 123 456"
        value={values.phone}
        onChange={(e) => setValues((v) => ({ ...v, phone: e.target.value }))}
        error={errors.phone}
      />
      <Input
        name="title"
        label="Title"
        placeholder="Senior Frontend Engineer"
        value={values.title}
        onChange={(e) => setValues((v) => ({ ...v, title: e.target.value }))}
      />

      {apiError ? (
        <p role="alert" className="text-sm font-medium text-destructive">
          {apiError}
        </p>
      ) : null}

      {success ? (
        <p role="status" className="text-sm font-medium text-green-600">
          Candidate profile saved successfully.
        </p>
      ) : null}

      <Button type="submit" className="w-full" isLoading={submitting}>
        Save profile
      </Button>
    </form>
  )
}