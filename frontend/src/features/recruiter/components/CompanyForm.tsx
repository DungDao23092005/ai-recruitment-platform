import { useState, type FormEvent } from 'react'
import { AlertCircle, CheckCircle2 } from 'lucide-react'
import { createCompany, updateCompany } from '@/api/companies'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import { getFriendlyErrorMessage } from '@/utils/errors'
import { cn } from '@/utils/cn'
import { COMPANY_SIZE_LABELS, COMPANY_SIZES } from '@/types/company'
import type { Company, CompanySize } from '@/types/company'

export interface CompanyFormProps {
  onCreated?: (company: Company) => void
  mode?: 'create' | 'edit'
  company?: Company
  onUpdated?: (company: Company) => void
  onCancelEdit?: () => void
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

export function CompanyForm({
  onCreated,
  mode = 'create',
  company,
  onUpdated,
  onCancelEdit,
}: CompanyFormProps) {
  const isEdit = mode === 'edit'
  const [values, setValues] = useState<FormValues>({
    name: company?.name ?? '',
    slug: company?.slug ?? '',
    tax_code: company?.tax_code ?? '',
    size: company?.size ?? 'startup',
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
      const payload = {
        name: values.name.trim(),
        slug: values.slug.trim(),
        tax_code: values.tax_code.trim(),
        size: values.size,
      }
      if (isEdit && company) {
        const updated = await updateCompany(company.id, payload)
        setSuccess(true)
        onUpdated?.(updated)
      } else {
        const created = await createCompany(payload)
        setSuccess(true)
        onCreated?.(created)
      }
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
      <div className="space-y-1.5">
        <Input
          name="slug"
          label="Slug"
          placeholder="abc-corporation"
          value={values.slug}
          onChange={(e) => setValues((v) => ({ ...v, slug: e.target.value }))}
          error={errors.slug}
          helperText="Chỉ gồm chữ thường, chữ số và dấu gạch ngang."
        />
        <div className="flex items-center gap-1.5 text-xs text-muted-foreground pt-0.5">
          <span>Xem trước:</span>
          <span className="font-mono font-medium text-foreground bg-muted/80 px-2 py-0.5 rounded text-[11px] border border-border/40">
            @{values.slug.trim() || 'slug'}
          </span>
        </div>
      </div>
      <Input
        name="tax_code"
        label="Mã số thuế"
        placeholder="0312345678"
        value={values.tax_code}
        onChange={(e) => setValues((v) => ({ ...v, tax_code: e.target.value }))}
        error={errors.tax_code}
      />
      <div className="space-y-2">
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

        <div
          className="grid grid-cols-2 gap-2 sm:grid-cols-4 pt-1"
          role="group"
          aria-label="Lựa chọn nhanh quy mô công ty"
        >
          {COMPANY_SIZES.map((size) => {
            const isSelected = values.size === size
            return (
              <button
                key={size}
                type="button"
                onClick={() => setValues((v) => ({ ...v, size }))}
                className={cn(
                  'flex items-center justify-center rounded-lg border px-3 py-2 text-xs font-medium transition-all text-center',
                  isSelected
                    ? 'border-primary bg-primary/10 text-primary shadow-xs ring-1 ring-primary'
                    : 'border-border/70 bg-card hover:border-primary/40 hover:bg-muted/40 text-muted-foreground hover:text-foreground',
                )}
                aria-pressed={isSelected}
              >
                <span>{COMPANY_SIZE_LABELS[size]}</span>
              </button>
            )
          })}
        </div>
      </div>

      {apiError ? (
        <div
          role="alert"
          className="flex items-start gap-2.5 rounded-lg border border-destructive/20 bg-destructive/10 p-3 text-sm font-medium text-destructive"
        >
          <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" aria-hidden="true" />
          <span>{apiError}</span>
        </div>
      ) : null}

      {success ? (
        <div
          role="status"
          className="flex items-start gap-2.5 rounded-lg border border-success/20 bg-success/10 p-3 text-sm font-medium text-success"
        >
          <CheckCircle2 className="h-4 w-4 shrink-0 mt-0.5" aria-hidden="true" />
          <span>
            {isEdit
              ? 'Cập nhật công ty thành công.'
              : 'Tạo công ty thành công.'}
          </span>
        </div>
      ) : null}

      <div className="flex flex-col gap-2.5 sm:flex-row pt-2">
        <Button type="submit" className="w-full sm:flex-1" isLoading={submitting}>
          {isEdit ? 'Lưu thay đổi' : 'Tạo công ty'}
        </Button>
        {isEdit ? (
          <Button
            type="button"
            variant="outline"
            className="w-full sm:w-auto"
            onClick={onCancelEdit}
          >
            Hủy chỉnh sửa
          </Button>
        ) : null}
      </div>
    </form>
  )
}
