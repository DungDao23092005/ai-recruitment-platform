import { useState } from 'react'
import { Building, Save } from 'lucide-react'
import { createAdminPlan, updateAdminPlan, updateAdminPlanStatus } from '@/api/admin'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { Modal } from '@/components/ui/modal'
import { getFriendlyErrorMessage } from '@/utils/errors'
import type { AdminPlanRead, AdminPlanCreate, AdminPlanUpdate, AdminPlanStatusUpdate } from '@/types/admin'

type FormMode = 'create' | 'edit' | 'status'

interface AdminPlanFormProps {
  defaultPlan?: AdminPlanRead
  onClose: () => void
  onSuccess?: (plan: AdminPlanRead) => void
  mode: FormMode
  planId?: string
}

export function AdminPlanForm({
  defaultPlan,
  onClose,
  onSuccess,
  mode,
  planId,
}: AdminPlanFormProps) {
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [price, setPrice] = useState(0)
  const [currency, setCurrency] = useState('VND')
  const [durationDays, setDurationDays] = useState(30)
  const [maxJobPosts, setMaxJobPosts] = useState(10)
  const [maxCandidateSearches, setMaxCandidateSearches] = useState(50)
  const [maxAiFeatures, setMaxAiFeatures] = useState(10)
  const [displayOrder, setDisplayOrder] = useState(0)
  const [isActive, setIsActive] = useState(true)

  const isCreate = mode === 'create'
  const isEdit = mode === 'edit'
  const isStatus = mode === 'status'

  const validateForm = (): boolean => {
    if (!name.trim()) {
      setError('Tên gói là bắt buộc')
      return false
    }
    if (price < 0) {
      setError('Giá không được âm')
      return false
    }
    if (durationDays <= 0) {
      setError('Thời lượng phải lớn hơn 0')
      return false
    }
    if (maxJobPosts < 0) {
      setError('Số lượng bài đăng không được âm')
      return false
    }
    if (maxCandidateSearches < 0) {
      setError('Số tìm kiếm ứng viên không được âm')
      return false
    }
    if (maxAiFeatures < 0) {
      setError('AI features không được âm')
      return false
    }
    if (displayOrder < 0) {
      setError('Thứ tự hiển thị không được âm')
      return false
    }
    return true
  }

  const handleSubmit = async () => {
    if (!validateForm()) return

    setSubmitting(true)
    setError(null)

    try {
      let result: AdminPlanRead

      if (isCreate) {
        const payload: AdminPlanCreate = {
          name: name.trim(),
          description: description.trim() || null,
          price,
          currency,
          duration_days: durationDays,
          max_job_posts: maxJobPosts,
          max_candidate_searches: maxCandidateSearches,
          max_ai_features: maxAiFeatures,
          display_order: displayOrder,
        }
        result = await createAdminPlan(payload)
      } else if (isEdit && planId) {
        const payload: AdminPlanUpdate = {
          name: name.trim() || undefined,
          description: description.trim() || null,
          price: price > 0 ? price : undefined,
          currency: currency || undefined,
          duration_days: durationDays > 0 ? durationDays : undefined,
          max_job_posts: maxJobPosts >= 0 ? maxJobPosts : undefined,
          max_candidate_searches: maxCandidateSearches >= 0 ? maxCandidateSearches : undefined,
          max_ai_features: maxAiFeatures >= 0 ? maxAiFeatures : undefined,
          display_order: displayOrder >= 0 ? displayOrder : undefined,
          is_active: isActive,
        }
        result = await updateAdminPlan(planId, payload)
      } else if (isStatus && planId) {
        const payload: AdminPlanStatusUpdate = {
          is_active: isActive,
        }
        result = await updateAdminPlanStatus(planId, payload)
        onClose()
        onSuccess?.(result)
        setSubmitting(false)
        return
      } else {
        throw new Error('Invalid mode or missing planId')
      }

      onSuccess?.(result)
      onClose()
    } catch (err) {
      setError(getFriendlyErrorMessage(err))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Modal
      onClose={onClose}
      size="lg"
      ariaLabel={isCreate ? 'Tạo gói tuyển dụng mới' : isEdit ? 'Sửa gói tuyển dụng' : 'Thay đổi trạng thái gói'}
      title={
        <span className="flex items-center gap-2">
          <Building className="h-5 w-5 text-primary" aria-hidden="true" />
          {isCreate ? 'Tạo gói mới' : isEdit ? 'Sửa gói' : 'Thay đổi trạng thái'}
        </span>
      }
      description={isCreate ? 'Điền thông tin gói tuyển dụng mới' : isEdit ? `Cập nhật gói: ${defaultPlan?.name}` : `Thay đổi trạng thái: ${defaultPlan?.name}`}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={submitting}>
            Hủy
          </Button>
          <Button
            variant="default"
            onClick={handleSubmit}
            isLoading={submitting}
            disabled={submitting}
          >
            <Save className="h-4 w-4 mr-2" aria-hidden="true" />
            {isCreate ? 'Tạo gói' : isEdit ? 'Cập nhật' : 'Lưu thay đổi'}
          </Button>
        </>
      }
    >
      {isStatus ? (
        <div className="space-y-4">
          <p className="text-sm text-muted-foreground">
            Gói: <span className="font-medium">{defaultPlan?.name}</span>
          </p>
          <p className="text-sm text-muted-foreground">
            Trạng thái hiện tại: <span className="font-medium">{defaultPlan?.is_active ? 'Hoạt động' : 'Khóa'}</span>
          </p>
          <div>
            <label htmlFor="status" className="block text-sm font-medium mb-1">
              Trạng thái mới <span className="text-destructive">*</span>
            </label>
            <Select
              id="status"
              name="status"
              value={isActive.toString()}
              onChange={(e) => setIsActive(e.target.value === 'true')}
            >
              <option value="true">Hoạt động</option>
              <option value="false">Khóa</option>
            </Select>
          </div>
        </div>
      ) : (
        <div className="space-y-4">
          <div>
            <label htmlFor="name" className="block text-sm font-medium mb-1">
              Tên gói <span className="text-destructive">*</span>
            </label>
            <Input
              id="name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Tên gói tuyển dụng"
              disabled={submitting}
              aria-invalid={error ? true : undefined}
            />
            {error && (
              <p role="alert" className="mt-1 text-sm text-destructive">
                {error}
              </p>
            )}
          </div>

          <div>
            <label htmlFor="description" className="block text-sm font-medium mb-1">
              Mô tả
            </label>
            <Textarea
              id="description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Mô tả gói (tùy chọn)"
              rows={3}
              disabled={submitting}
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label htmlFor="price" className="block text-sm font-medium mb-1">
                Giá (VND) <span className="text-destructive">*</span>
              </label>
              <Input
                id="price"
                type="number"
                value={price}
                onChange={(e) => setPrice(Number(e.target.value) || 0)}
                placeholder="0"
                min={0}
                disabled={submitting}
              />
            </div>

            <div>
              <label htmlFor="currency" className="block text-sm font-medium mb-1">
                Hộ tiền tệ <span className="text-destructive">*</span>
              </label>
              <Select
                id="currency"
                name="currency"
                value={currency}
                onChange={(e) => setCurrency(e.target.value)}
              >
                <option value="VND">VND (Vietnamese Dong)</option>
                <option value="USD">USD (US Dollar)</option>
              </Select>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label htmlFor="durationDays" className="block text-sm font-medium mb-1">
                Thời lượng (ngày) <span className="text-destructive">*</span>
              </label>
              <Input
                id="durationDays"
                type="number"
                value={durationDays}
                onChange={(e) => setDurationDays(Number(e.target.value) || 0)}
                placeholder="30"
                min={1}
                disabled={submitting}
              />
            </div>

            <div>
              <label htmlFor="maxJobPosts" className="block text-sm font-medium mb-1">
                Số lượng bài đăng <span className="text-destructive">*</span>
              </label>
              <Input
                id="maxJobPosts"
                type="number"
                value={maxJobPosts}
                onChange={(e) => setMaxJobPosts(Number(e.target.value) || 0)}
                placeholder="10"
                min={0}
                disabled={submitting}
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label htmlFor="maxCandidateSearches" className="block text-sm font-medium mb-1">
                Số tìm kiếm ứng viên <span className="text-destructive">*</span>
              </label>
              <Input
                id="maxCandidateSearches"
                type="number"
                value={maxCandidateSearches}
                onChange={(e) => setMaxCandidateSearches(Number(e.target.value) || 0)}
                placeholder="50"
                min={0}
                disabled={submitting}
              />
            </div>

            <div>
              <label htmlFor="maxAiFeatures" className="block text-sm font-medium mb-1">
                AI features <span className="text-destructive">*</span>
              </label>
              <Input
                id="maxAiFeatures"
                type="number"
                value={maxAiFeatures}
                onChange={(e) => setMaxAiFeatures(Number(e.target.value) || 0)}
                placeholder="10"
                min={0}
                disabled={submitting}
              />
            </div>
          </div>

          <div>
            <label htmlFor="displayOrder" className="block text-sm font-medium mb-1">
              Thứ tự hiển thị <span className="text-destructive">*</span>
            </label>
            <Input
              id="displayOrder"
              type="number"
              value={displayOrder}
              onChange={(e) => setDisplayOrder(Number(e.target.value) || 0)}
              placeholder="0"
              min={0}
              disabled={submitting}
            />
          </div>

          {isEdit && (
            <div>
              <label htmlFor="isActive" className="block text-sm font-medium mb-1">
                Trạng thái
              </label>
              <Select
                id="isActive"
                name="isActive"
                value={isActive.toString()}
                onChange={(e) => setIsActive(e.target.value === 'true')}
              >
                <option value="true">Hoạt động</option>
                <option value="false">Khóa</option>
              </Select>
            </div>
          )}
        </div>
      )}

      {error && (
        <p role="alert" className="mt-3 rounded-md bg-destructive/10 px-3 py-2 text-sm font-medium text-destructive">
          {error}
        </p>
      )}
    </Modal>
  )
}