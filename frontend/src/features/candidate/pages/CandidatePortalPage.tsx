import { Link } from 'react-router-dom'
import { FileUp, Search } from 'lucide-react'
import { PageHeader } from '@/components/common/PageHeader'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'

export function CandidatePortalPage() {
  return (
    <div className="container py-10">
      <PageHeader
        title="Candidate Portal"
        description="Manage your job discovery and application workflow."
      />

      <div className="grid gap-6 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Search className="h-5 w-5 text-primary" aria-hidden="true" />
              Explore jobs
            </CardTitle>
            <CardDescription>
              Search, filter and discover job opportunities.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Link to="/jobs">
              <Button variant="outline">Browse jobs</Button>
            </Link>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <FileUp className="h-5 w-5 text-primary" aria-hidden="true" />
              Upload CV
            </CardTitle>
            <CardDescription>
              Upload your resume to parse your professional profile with AI.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Link to="/candidate/cv-upload">
              <Button>Upload CV</Button>
            </Link>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}