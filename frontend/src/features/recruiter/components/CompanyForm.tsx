import { useState, type FormEvent } from 'react'
import { createCompany } from '@/api/companies'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
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
    errors.name = 'Tên công ty là bắt buộc'
  }
  if (!values.slug.trim()) {
    errors.slug = 'Slug là bắt buộc'
  } else if (!/^[a-z0-9-]+$/.test(values.slug.trim())) {
    errors.slug =
      'Slug chỉ được chứa chữ thường, chữ số và dấu gạch ngang'
  }
  if (!values.tax_code.trim()) {
    errors.tax_code = 'Mã số thuế là bắt buộc'
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
        setApiError('Mã số thuế đã được đăng ký. Vui lòng kiểm tra lại.')
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
        label="Tên công ty"
        placeholder="Công ty TNHH ABC"
        value={values.name}
        onChange={(e) => setValues((v) => ({ ...v, name: e.target.value }))}
        error={errors.name}
      />
      <Input
        name="slug"
        label="Slug"
        placeholder="abc-corporation"
        value={values.slug}
        onChange={(e) => setValues((v) => ({ ...v, slug: e.target.value }))}
        error={errors.slug}
        helperText="Chỉ gồm chữ thường, chữ số và dấu gạch ngang."
      />
      <Input
        name="tax_code"
        label="Mã số thuế"
        placeholder="0312345678"
        value={values.tax_code}
        onChange={(e) => setValues((v) => ({ ...v, tax_code: e.target.value }))}
        error={errors.tax_code}
      />
      <Select
        name="size"
        label="Quy mô công ty"
        value={values.size}
        onChange={(e) =>
          setValues((v) => ({ ...v, size: e.target.value as CompanySize }))
        }
      >
        {COMPANY_SIZES.map((size) => (
          <option key={size} value={size}>
            {COMPANY_SIZE_LABELS[size]}
          </option>
        ))}
      </Select>

      {apiError ? (
        <p role="alert" className="text-sm font-medium text-destructive">
          {apiError}
        </p>
      ) : null}

      {success ? (
        <p role="status" className="text-sm font-medium text-success">
          Tạo công ty thành công.
        </p>
      ) : null}

      <Button type="submit" className="w-full" isLoading={submitting}>
        Tạo công ty
      </Button>
    </form>
  )
}