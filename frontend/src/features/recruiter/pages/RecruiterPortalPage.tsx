import { Link } from 'react-router-dom'
import { Building, Briefcase, PlusCircle } from 'lucide-react'
import { PageHeader } from '@/components/common/PageHeader'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'

export function RecruiterPortalPage() {
  return (
    <div className="container py-10">
      <PageHeader
        title="Recruiter Portal"
        description="Manage your companies, job postings and applicants."
      />

      <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Building className="h-5 w-5 text-primary" aria-hidden="true" />
              Manage company
            </CardTitle>
            <CardDescription>
              Create and view your company profile.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Link to="/recruiter/company">
              <Button variant="outline">Manage company</Button>
            </Link>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Briefcase className="h-5 w-5 text-primary" aria-hidden="true" />
              Job postings
            </CardTitle>
            <CardDescription>
              View and manage your job postings.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Link to="/recruiter/jobs">
              <Button variant="outline">View jobs</Button>
            </Link>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <PlusCircle className="h-5 w-5 text-primary" aria-hidden="true" />
              Post a job
            </CardTitle>
            <CardDescription>
              Create a new job posting with AI-assisted JD parsing.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Link to="/recruiter/jobs/new">
              <Button>Post a job</Button>
            </Link>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
