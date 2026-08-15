import { useAuth } from '@/contexts/AuthContext'
import { CandidateProfileForm } from '@/features/candidate/components/CandidateProfileForm'
import { RecruiterProfileForm } from '@/features/recruiter/components/RecruiterProfileForm'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { PageHeader } from '@/components/common/PageHeader'
import { Skeleton } from '@/components/ui/skeleton'

export function ProfilePage() {
  const { currentUser, isLoading } = useAuth()

  if (isLoading) {
    return (
      <div className="mx-auto max-w-xl space-y-4">
        <Skeleton className="h-8 w-2/3" />
        <Skeleton className="h-4 w-1/2" />
        <Card className="p-6">
          <Skeleton className="h-6 w-1/2" />
          <Skeleton className="mt-4 h-10 w-full" />
          <Skeleton className="mt-4 h-10 w-full" />
          <Skeleton className="mt-4 h-10 w-full" />
        </Card>
      </div>
    )
  }

  const role = currentUser?.role

  return (
    <div className="mx-auto max-w-xl space-y-6">
      <PageHeader
        eyebrow="Tài khoản"
        title="Hồ sơ của bạn"
        description="Hoàn thiện hồ sơ để cải thiện trải nghiệm đối sánh AI."
      />

      <Card className="border-border/70 shadow-soft">
        <CardHeader>
          <CardTitle className="font-display text-lg font-semibold">
            {role === 'candidate' ? 'Hồ sơ ứng viên' : 'Hồ sơ nhà tuyển dụng'}
          </CardTitle>
          <CardDescription>
            {role === 'candidate'
              ? 'Chia sẻ thông tin nền tảng và kỹ năng của bạn.'
              : 'Chia sẻ thông tin vai trò tuyển dụng và công ty của bạn.'}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {role === 'candidate' ? <CandidateProfileForm /> : null}
          {role === 'recruiter' ? <RecruiterProfileForm /> : null}
        </CardContent>
      </Card>
    </div>
  )
}