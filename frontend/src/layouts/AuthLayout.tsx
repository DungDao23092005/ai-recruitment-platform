import { Outlet } from 'react-router-dom'

export function AuthLayout() {
  return (
    <div className="flex min-h-screen items-center justify-center ai-gradient p-4">
      <div className="w-full max-w-md rounded-xl bg-card p-8 shadow-lg">
        <Outlet />
      </div>
    </div>
  )
}