import { useState, type FormEvent } from 'react'
import { createCompany } from '@/api/companies'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { getFriendlyErrorMessage } from '@/utils/errors'
import { COMPANY_SIZE_LABELS, COMPANY_SIZES } from '@/types/company'
import type { Company, CompanySize } from '@/types/company'

export interface CompanyFormProps {
  onCreated?: (company: Company) => void
}

interface FormValues {
  name: string
  slug: string
  tax_code: string
  size: CompanySize
}

interface FormErrors {
  name?: string
  slug?: string
  tax_code?: string
}

function validate(values: FormValues): FormErrors {
  const errors: FormErrors = {}
  if (!values.name.trim()) {
    errors.name = 'Company name is required'
  }
  if (!values.slug.trim()) {
    errors.slug = 'Slug is required'
  } else if (!/^[a-z0-9-]+$/.test(values.slug.trim())) {
    errors.slug = 'Slug can only contain lowercase letters, numbers and hyphens'
  }
  if (!values.tax_code.trim()) {
    errors.tax_code = 'Tax code is required'
  }
  return errors
}

export function CompanyForm({ onCreated }: CompanyFormProps) {
  const [values, setValues] = useState<FormValues>({
    name: '',
    slug: '',
    tax_code: '',
    size: 'startup',
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
      const company = await createCompany({
        name: values.name.trim(),
        slug: values.slug.trim(),
        tax_code: values.tax_code.trim(),
        size: values.size,
      })
      setSuccess(true)
      onCreated?.(company)
    } catch (error) {
      const message = getFriendlyErrorMessage(error)
      if (
        error instanceof Error &&
        (error as Error & { response?: { status?: number } }).response
          ?.status === 400 &&
        /tax_code|already exists|duplicate/i.test(message)
      ) {
        setApiError('Tax code already registered. Please check and try again.')
      } else {
        setApiError(message)
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4" noValidate>
      <Input
        name="name"
        label="Company name"
        placeholder="Acme Corporation"
        value={values.name}
        onChange={(e) => setValues((v) => ({ ...v, name: e.target.value }))}
        error={errors.name}
      />
      <Input
        name="slug"
        label="Slug"
        placeholder="acme-corporation"
        value={values.slug}
        onChange={(e) => setValues((v) => ({ ...v, slug: e.target.value }))}
        error={errors.slug}
        helperText="Lowercase letters, numbers and hyphens only."
      />
      <Input
        name="tax_code"
        label="Tax code"
        placeholder="0312345678"
        value={values.tax_code}
        onChange={(e) => setValues((v) => ({ ...v, tax_code: e.target.value }))}
        error={errors.tax_code}
      />
      <div className="flex flex-col gap-1.5">
        <label
          htmlFor="company-size"
          className="text-sm font-medium leading-none"
        >
          Company size
        </label>
        <select
          id="company-size"
          name="size"
          value={values.size}
          onChange={(e) =>
            setValues((v) => ({ ...v, size: e.target.value as CompanySize }))
          }
          className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
        >
          {COMPANY_SIZES.map((size) => (
            <option key={size} value={size}>
              {COMPANY_SIZE_LABELS[size]}
            </option>
          ))}
        </select>
      </div>

      {apiError ? (
        <p role="alert" className="text-sm font-medium text-destructive">
          {apiError}
        </p>
      ) : null}

      {success ? (
        <p role="status" className="text-sm font-medium text-green-600">
          Company created successfully.
        </p>
      ) : null}

      <Button type="submit" className="w-full" isLoading={submitting}>
        Create company
      </Button>
    </form>
  )
}
