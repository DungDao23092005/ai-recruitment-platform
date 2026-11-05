import { Building2 } from 'lucide-react'
import { Select } from '@/components/ui/select'
import { useAuth } from '@/contexts/AuthContext'
import { useWorkspace } from '@/contexts/WorkspaceContext'
import { cn } from '@/utils/cn'

interface WorkspaceSwitcherProps {
  className?: string
}

export function WorkspaceSwitcher({ className }: WorkspaceSwitcherProps) {
  const { currentUser } = useAuth()
  const { workspaces, selectedCompanyId, isLoading, selectWorkspace, error } =
    useWorkspace()

  if (
    !currentUser ||
    currentUser.role === 'candidate' ||
    (workspaces.length === 0 && !isLoading && !error)
  ) {
    return null
  }

  return (
    <div className={cn('flex min-w-0 items-center gap-2', className)}>
      <Building2
        className="hidden h-4 w-4 shrink-0 text-muted-foreground sm:block"
        aria-hidden="true"
      />
      <Select
        aria-label="Chọn công ty làm việc"
        value={selectedCompanyId ?? ''}
        onChange={(event) =>
          selectWorkspace(event.target.value || null)
        }
        disabled={isLoading}
        className="h-9 w-full min-w-0 sm:w-56"
      >
        {currentUser.role === 'admin' ? (
          <option value="">Toàn hệ thống</option>
        ) : null}
        {workspaces.map((workspace) => (
          <option
            key={workspace.company_id}
            value={workspace.company_id}
          >
            {workspace.company_name}
            {workspace.role === 'admin' ? ' (Quản trị)' : ''}
          </option>
        ))}
      </Select>
    </div>
  )
}
