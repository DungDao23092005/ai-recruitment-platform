import { Link } from 'react-router-dom'
import { Sparkles } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { PageHeader } from '@/components/common/PageHeader'

export function HomePage() {
  return (
    <div className="container py-10">
      <PageHeader
        title="AI Recruitment Platform"
        description="Smart AI-powered matching between candidates and job opportunities."
        actions={
          <>
<Button variant="outline" className="hidden sm:inline-flex">
            Learn more
          </Button>
          <Button variant="default">
            Get started
          </Button>
          </>
        }
      />

      <div className="grid gap-6 md:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Sparkles className="h-5 w-5 text-primary" />
              AI Matching
            </CardTitle>
            <CardDescription>
              Semantic resume parsing and job matching powered by embeddings.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Badge variant="ai-gradient">AI Powered</Badge>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Candidate Hub</CardTitle>
            <CardDescription>
              Upload your CV and discover jobs that fit your profile.
            </CardDescription>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Recruiter Tools</CardTitle>
            <CardDescription>
              Post jobs and rank applicants by match score.
            </CardDescription>
          </CardHeader>
        </Card>
      </div>

      <p className="mt-8 text-sm text-muted-foreground">
        Check the backend health:{' '}
        <Link to="/health" className="text-primary underline underline-offset-4">
          /health
        </Link>
      </p>
    </div>
  )
}