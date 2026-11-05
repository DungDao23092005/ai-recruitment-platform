import { AuthProvider } from '@/contexts/AuthContext'
import { WorkspaceProvider } from '@/contexts/WorkspaceContext'
import { AppRouter } from '@/routes'

export default function App() {
  return (
    <AuthProvider>
      <WorkspaceProvider>
        <AppRouter />
      </WorkspaceProvider>
    </AuthProvider>
  )
}