import { Outlet } from 'react-router-dom'

export function AuthLayout() {
  return (
    <div className="flex min-h-screen items-center justify-center ai-gradient p-4">
      <div className="w-full max-w-md">
        <Outlet />
      </div>
    </div>
  )
}