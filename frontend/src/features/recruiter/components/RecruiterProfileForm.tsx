import { useState, type FormEvent } from 'react'
import { createRecruiterProfile } from '@/api/auth'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { getFriendlyErrorMessage } from '@/utils/errors'

interface FormValues {
  full_name: string
  position: string
  company_id: string
}

export function RecruiterProfileForm() {
  const [values, setValues] = useState<FormValues>({
    full_name: '',
    position: '',
    company_id: '',
  })
  const [apiError, setApiError] = useState<string | null>(null)
  const [success, setSuccess] = useState(false)
  const [submitting, setSubmitting] = useState(false)

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    setApiError(null)
    setSuccess(false)

    setSubmitting(true)
    try {
      await createRecruiterProfile({
        full_name: values.full_name.trim() || null,
        position: values.position.trim() || null,
        company_id: values.company_id.trim() || null,
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
        label="Họ và tên"
        placeholder="Trần Thị Bích"
        value={values.full_name}
        onChange={(e) =>
          setValues((v) => ({ ...v, full_name: e.target.value }))
        }
      />
      <Input
        name="position"
        label="Vị trí"
        placeholder="Trưởng phòng Tuyển dụng"
        value={values.position}
        onChange={(e) => setValues((v) => ({ ...v, position: e.target.value }))}
      />
      <Input
        name="company_id"
        label="Mã công ty (tùy chọn)"
        placeholder="vd: 3fa85f64-5717-4562-b3fc-2c963f66afa6"
        helperText="Có thể liên kết tài khoản với công ty đã tạo trên nền tảng."
        value={values.company_id}
        onChange={(e) =>
          setValues((v) => ({ ...v, company_id: e.target.value }))
        }
      />

      {apiError ? (
        <p role="alert" className="text-sm font-medium text-destructive">
          {apiError}
        </p>
      ) : null}

      {success ? (
        <p role="status" className="text-sm font-medium text-success">
          Đã lưu hồ sơ nhà tuyển dụng.
        </p>
      ) : null}

      <Button type="submit" className="w-full" isLoading={submitting}>
        Lưu hồ sơ
      </Button>
    </form>
  )
}