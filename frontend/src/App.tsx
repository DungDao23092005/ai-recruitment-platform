import { AuthProvider } from '@/contexts/AuthContext'
import { AppRouter } from '@/routes'

export default function App() {
  return (
    <AuthProvider>
      <AppRouter />
    </AuthProvider>
  )
}