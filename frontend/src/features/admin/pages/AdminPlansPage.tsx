import { useCallback, useEffect, useState } from 'react'
import { Plus, RefreshCw } from 'lucide-react'
import { getAdminPlans } from '@/api/admin'
import { AdminPlanForm } from '@/features/admin/components/AdminPlanForm'
import { AdminPlanList } from '@/features/admin/components/AdminPlanList'
import { Button } from '@/components/ui/button'
import type { AdminPlanRead } from '@/types/admin'

export function AdminPlansPage() {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [editingPlan, setEditingPlan] = useState<AdminPlanRead | null>(null)
  const [statusPlan, setStatusPlan] = useState<AdminPlanRead | null>(null)
  const [isStatusModalOpen, setIsStatusModalOpen] = useState(false)
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false)

  const loadPlans = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      await getAdminPlans({
        skip: 0,
        limit: 100,
      })
      // AdminPlanList loads its own data
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Không thể tải danh sách gói'
      setError(message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadPlans()
  }, [loadPlans])

  const handleCreate = () => {
    setIsCreateModalOpen(true)
  }

  const handleEdit = (plan: AdminPlanRead) => {
    setEditingPlan(plan)
  }

  const handleStatus = (plan: AdminPlanRead) => {
    setStatusPlan(plan)
    setIsStatusModalOpen(true)
  }

  const handlePlanCreated = () => {
    setIsCreateModalOpen(false)
    loadPlans()
  }

  const handlePlanUpdated = () => {
    setEditingPlan(null)
    loadPlans()
  }

  const handlePlanStatusToggled = () => {
    setIsStatusModalOpen(false)
    loadPlans()
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="flex flex-col items-center gap-4">
          <RefreshCw className="h-8 w-8 text-muted-foreground animate-spin" />
          <span className="text-muted-foreground">Đang tải danh sách gói...</span>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Gói tuyển dụng</h1>
          <p className="text-muted-foreground mt-1">Quản lý các gói tuyển dụng cho nhà tuyển dụng</p>
        </div>
        <Button
          onClick={handleCreate}
          aria-label="Tạo gói tuyển dụng mới"
        >
          <Plus className="h-4 w-4 mr-2" aria-hidden="true" />
          Tạo gói mới
        </Button>
      </div>

      {error ? (
        <div
          role="alert"
          className="rounded-md bg-destructive/10 p-3 text-sm font-medium text-destructive"
        >
          {error}
        </div>
      ) : null}

      {editingPlan && (
        <AdminPlanForm
          mode="edit"
          defaultPlan={editingPlan}
          onClose={() => setEditingPlan(null)}
          onSuccess={handlePlanUpdated}
        />
      )}

      {isCreateModalOpen && (
        <AdminPlanForm
          mode="create"
          onClose={() => setIsCreateModalOpen(false)}
          onSuccess={handlePlanCreated}
        />
      )}

      {statusPlan && isStatusModalOpen && (
        <AdminPlanForm
          mode="status"
          defaultPlan={statusPlan}
          onClose={() => setIsStatusModalOpen(false)}
          onSuccess={handlePlanStatusToggled}
        />
      )}

      <AdminPlanList
        onEdit={handleEdit}
        onStatus={handleStatus}
      />
    </div>
  )
}