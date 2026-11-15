import { useRef, useState } from 'react'
import { Building, Info, Save } from 'lucide-react'
import { createAdminPlan, updateAdminPlan, updateAdminPlanStatus } from '@/api/admin'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { Modal } from '@/components/ui/modal'
import { getFriendlyErrorMessage } from '@/utils/errors'
import type {
  AdminPlanAudience,
  AdminPlanRead,
  AdminPlanCreate,
  AdminPlanUpdate,
  AdminPlanStatusUpdate,
} from '@/types/admin'

type FormMode = 'create' | 'edit' | 'status'
type PlanKind = 'company_free' | 'company' | 'candidate_free' | 'candidate_paid'

const PLAN_KIND_OPTIONS: { value: PlanKind; label: string }[] = [
  { value: 'company_free', label: 'Doanh nghiệp — Miễn phí' },
  { value: 'company', label: 'Doanh nghiệp — Trả phí' },
  { value: 'candidate_free', label: 'Ứng viên — Miễn phí' },
  { value: 'candidate_paid', label: 'Ứng viên — Trả phí' },
]

function isCompanyKind(kind: PlanKind): boolean {
  return kind === 'company' || kind === 'company_free'
}

function isFreeKind(kind: PlanKind): boolean {
  return kind === 'company_free' || kind === 'candidate_free'
}

function resolvePlanKind(plan?: AdminPlanRead): PlanKind {
  if (!plan) return 'company'
  if (plan.is_free) {
    return plan.plan_audience === 'company'
      ? 'company_free'
      : 'candidate_free'
  }
  return plan.plan_audience === 'candidate' ? 'candidate_paid' : 'company'
}

function audienceForKind(kind: PlanKind): AdminPlanAudience {
  return isCompanyKind(kind) ? 'company' : 'candidate'
}

interface AdminPlanFormProps {
  defaultPlan?: AdminPlanRead
  onClose: () => void
  onSuccess?: (plan: AdminPlanRead) => void
  mode: FormMode
  planId?: string
  existingActiveCompanyFreePlan?: AdminPlanRead | null
  existingActiveCandidateFreePlan?: AdminPlanRead | null
}

export function AdminPlanForm({
  defaultPlan,
  onClose,
  onSuccess,
  mode,
  planId,
  existingActiveCompanyFreePlan,
  existingActiveCandidateFreePlan,
}: AdminPlanFormProps) {
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const isCreate = mode === 'create'
  const isEdit = mode === 'edit'
  const isStatus = mode === 'status'

  // Resolve plan ID: use explicit planId, fallback to defaultPlan.id
  const targetPlanId = planId ?? defaultPlan?.id

  const [planKind, setPlanKind] = useState<PlanKind>(() =>
    resolvePlanKind(defaultPlan),
  )
  const planAudience = audienceForKind(planKind)
  const isCompany = isCompanyKind(planKind)
  const isCompanyFree = planKind === 'company_free'
  const isCandidateFree = planKind === 'candidate_free'
  const isFree = isFreeKind(planKind)
  const freePlanConflict =
    isCreate &&
    ((isCompanyFree && existingActiveCompanyFreePlan != null) ||
      (isCandidateFree && existingActiveCandidateFreePlan != null))
  const freePlanConflictName = isCompanyFree
    ? existingActiveCompanyFreePlan?.name
    : existingActiveCandidateFreePlan?.name
  const freePlanConflictLabel = isCompanyFree
    ? 'Doanh nghiệp Miễn phí'
    : 'Ứng viên Miễn phí'

  // The canonical Company Free row must stay active so workspaces always have
  // a fallback entitlement. Editing its quotas/name is allowed; deactivation is
  // blocked both here and by the backend.
  const isCanonicalCompanyFree =
    isCompanyFree && defaultPlan?.is_active === true

  // Initialize form state from defaultPlan when in edit mode, otherwise use defaults
  const [name, setName] = useState(defaultPlan?.name ?? '')
  const [description, setDescription] = useState(defaultPlan?.description ?? '')
  const [price, setPrice] = useState(defaultPlan?.price ?? 0)
  const [currency, setCurrency] = useState(defaultPlan?.currency ?? 'VND')
  const [durationDays, setDurationDays] = useState(defaultPlan?.duration_days ?? 30)
  const [maxJobPosts, setMaxJobPosts] = useState(defaultPlan?.max_job_posts ?? 10)
  const [maxCandidateSearches, setMaxCandidateSearches] = useState(defaultPlan?.max_candidate_searches ?? 50)
  const [maxAiFeatures, setMaxAiFeatures] = useState(defaultPlan?.max_ai_features ?? 10)
  const [displayOrder, setDisplayOrder] = useState(defaultPlan?.display_order ?? 0)
  const [isActive, setIsActive] = useState(defaultPlan?.is_active ?? true)

  // Remember Company quota values so switching to a Candidate plan (which
  // stores zero for recruitment quotas) does not discard them.
  const companyQuotasRef = useRef<{
    maxJobPosts: number
    maxCandidateSearches: number
  } | null>(null)

  const handlePlanKindChange = (kind: PlanKind) => {
    if (isCompanyKind(planKind) && !isCompanyKind(kind)) {
      companyQuotasRef.current = { maxJobPosts, maxCandidateSearches }
    }

    if (!isCompanyKind(kind)) {
      setMaxJobPosts(0)
      setMaxCandidateSearches(0)
    } else if (!isCompanyKind(planKind)) {
      const restored = companyQuotasRef.current ?? {
        maxJobPosts: 10,
        maxCandidateSearches: 50,
      }
      setMaxJobPosts(restored.maxJobPosts)
      setMaxCandidateSearches(restored.maxCandidateSearches)
    }

    setPlanKind(kind)
    if (isFreeKind(kind)) {
      setPrice(0)
    }
    if (kind === 'company_free') {
      setCurrency('VND')
      setDurationDays(30)
      if (planKind !== 'company_free') {
        setMaxJobPosts(1)
        setMaxCandidateSearches(10)
        setMaxAiFeatures(5)
      }
    }
  }

  // Candidate plans always submit zero recruitment quotas; their shared AI
  // quota is mapped through max_ai_features.
  const effectiveMaxJobPosts = isCompany ? maxJobPosts : 0
  const effectiveMaxCandidateSearches = isCompany ? maxCandidateSearches : 0

  const aiQuotaLabel = isCompany
    ? 'Lượt AI tuyển dụng'
    : 'Hạn mức AI ứng viên (Lượt AI dùng chung)'
  const aiQuotaHelper = isCompany
    ? 'Hạn mức lượt dùng cho các tính năng AI phục vụ tuyển dụng.'
    : 'Một hạn mức AI dùng chung cho Phân tích CV, Gợi ý việc làm và Trò chuyện AI.'

  const validateForm = (): boolean => {
    if (!name.trim()) {
      setError('Tên gói là bắt buộc')
      return false
    }
    if (isFree && price !== 0) {
      setError('Gói Ứng viên Miễn phí phải có giá 0')
      return false
    }
    if (!isFree && price <= 0) {
      setError('Gói trả phí phải có giá lớn hơn 0')
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
    if (freePlanConflict) {
      setError(
        `Đã có gói ${freePlanConflictLabel} đang hoạt động${
          freePlanConflictName ? ` (${freePlanConflictName})` : ''
        }. Hãy chỉnh sửa gói đó thay vì tạo gói mới.`,
      )
      return false
    }
    if (isCompany && maxJobPosts < 0) {
      setError('Số lượng bài đăng không được âm')
      return false
    }
    if (isCompany && maxCandidateSearches < 0) {
      setError('Số tìm kiếm ứng viên không được âm')
      return false
    }
    if (maxAiFeatures < 0) {
      setError('Lượt AI không được âm')
      return false
    }
    if (displayOrder < 0) {
      setError('Thứ tự hiển thị không được âm')
      return false
    }
    return true
  }

  const handleSubmit = async () => {
    if (isStatus && isCanonicalCompanyFree && !isActive) {
      setError('Không thể khóa gói Doanh nghiệp Miễn phí mặc định của hệ thống.')
      return
    }

    // Only validate full form for create/edit modes
    if (!isStatus && !validateForm()) return

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
          max_job_posts: effectiveMaxJobPosts,
          max_candidate_searches: effectiveMaxCandidateSearches,
          max_ai_features: maxAiFeatures,
          plan_audience: planAudience,
          is_free: isFree,
          display_order: displayOrder,
        }
        result = await createAdminPlan(payload)
      } else if (isEdit) {
        if (!targetPlanId) {
          setError('Thiếu ID gói để cập nhật')
          setSubmitting(false)
          return
        }
        const payload: AdminPlanUpdate = {
          name: name.trim() || undefined,
          description: description.trim() || null,
          price: price >= 0 ? price : undefined,
          currency: currency || undefined,
          duration_days: durationDays > 0 ? durationDays : undefined,
          max_job_posts: effectiveMaxJobPosts,
          max_candidate_searches: effectiveMaxCandidateSearches,
          max_ai_features: maxAiFeatures >= 0 ? maxAiFeatures : undefined,
          plan_audience: planAudience,
          is_free: isFree,
          display_order: displayOrder >= 0 ? displayOrder : undefined,
          is_active: isActive,
        }
        result = await updateAdminPlan(targetPlanId!, payload)
      } else if (isStatus) {
        if (!targetPlanId) {
          setError('Thiếu ID gói để thay đổi trạng thái')
          setSubmitting(false)
          return
        }
        const payload: AdminPlanStatusUpdate = {
          is_active: isActive,
        }
        result = await updateAdminPlanStatus(targetPlanId!, payload)
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
            disabled={submitting || freePlanConflict}
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
          {isCanonicalCompanyFree ? (
            <div
              role="alert"
              className="flex items-start gap-2 rounded-md border border-info/40 bg-info/10 px-3 py-2 text-sm text-foreground"
            >
              <Info className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
              <span>
                Gói Doanh nghiệp Miễn phí mặc định không thể khóa để đảm bảo quyền lợi tuyển dụng cho doanh nghiệp.
              </span>
            </div>
          ) : null}
          <div>
            <label htmlFor="status" className="block text-sm font-medium mb-1">
              Trạng thái mới <span className="text-destructive">*</span>
            </label>
            <Select
              id="status"
              name="status"
              value={isActive.toString()}
              onChange={(e) => setIsActive(e.target.value === 'true')}
              disabled={isCanonicalCompanyFree}
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

          <div>
            <label htmlFor="planKind" className="block text-sm font-medium mb-1">
              Loại gói <span className="text-destructive">*</span>
            </label>
            <Select
              id="planKind"
              name="planKind"
              value={planKind}
              onChange={(e) => handlePlanKindChange(e.target.value as PlanKind)}
              disabled={submitting}
            >
              {PLAN_KIND_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </Select>
            {isFree ? (
              <p className="mt-1 text-xs text-muted-foreground">
                Gói Ứng viên Miễn phí không hết hạn. Thời lượng chỉ là thông tin
                metadata; hạn mức AI được đặt lại hằng tháng.
              </p>
            ) : null}
          </div>

          {freePlanConflict ? (
            <div
              role="alert"
              className="flex items-start gap-2 rounded-md border border-warning/40 bg-warning/10 px-3 py-2 text-sm text-foreground"
            >
              <Info className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
              <span>
                Đã có gói {freePlanConflictLabel} đang hoạt động
                {freePlanConflictName ? `: ${freePlanConflictName}` : ''}. Hãy
                chỉnh sửa gói hiện có thay vì tạo gói mới.
              </span>
            </div>
          ) : null}

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label htmlFor="price" className="block text-sm font-medium mb-1">
                Giá (VND) <span className="text-destructive">*</span>
              </label>
              <Input
                id="price"
                type="number"
                value={isFree ? 0 : price}
                onChange={(e) => setPrice(Number(e.target.value) || 0)}
                placeholder="0"
                min={0}
                disabled={submitting || isFree}
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
                disabled={submitting || isFree}
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
                value={isCompanyFree ? 30 : durationDays}
                onChange={(e) => setDurationDays(Number(e.target.value) || 0)}
                placeholder="30"
                min={1}
                disabled={submitting || isCompanyFree}
              />
            </div>

            {isCompany ? (
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
            ) : null}
          </div>

          <div className={isCompany ? 'grid grid-cols-2 gap-4' : 'space-y-4'}>
            {isCompany ? (
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
            ) : null}

            <div>
              <label htmlFor="maxAiFeatures" className="block text-sm font-medium mb-1">
                {aiQuotaLabel} <span className="text-destructive">*</span>
              </label>
              <Input
                id="maxAiFeatures"
                type="number"
                value={maxAiFeatures}
                onChange={(e) => setMaxAiFeatures(Number(e.target.value) || 0)}
                placeholder="10"
                min={0}
                disabled={submitting}
                aria-describedby="maxAiFeatures-helper"
              />
              <p id="maxAiFeatures-helper" className="mt-1 text-xs text-muted-foreground">
                {aiQuotaHelper}
              </p>
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