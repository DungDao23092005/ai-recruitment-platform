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
import { Spinner } from '@/components/ui/spinner'

export function ProfilePage() {
  const { currentUser, isLoading } = useAuth()

  if (isLoading) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center">
        <Spinner size="lg" />
      </div>
    )
  }

  const role = currentUser?.role

  return (
    <div className="container py-10">
      <PageHeader
        title="Your profile"
        description="Complete your profile to improve your AI matching experience."
      />

      <div className="max-w-xl">
        <Card>
          <CardHeader>
            <CardTitle>
              {role === 'candidate' ? 'Candidate profile' : 'Recruiter profile'}
            </CardTitle>
            <CardDescription>
              {role === 'candidate'
                ? 'Tell us about your background and skills.'
                : 'Tell us about your recruiting role and company.'}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {role === 'candidate' ? <CandidateProfileForm /> : null}
            {role === 'recruiter' ? <RecruiterProfileForm /> : null}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}