import { useState } from 'react'
import { Link } from 'react-router-dom'
import { PageHeader } from '@/components/common/PageHeader'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { CompanyForm } from '@/features/recruiter/components/CompanyForm'
import { CompanyCard } from '@/features/recruiter/components/CompanyCard'
import type { Company } from '@/types/company'

export function RecruiterCompanyPage() {
  const [company, setCompany] = useState<Company | null>(null)

  return (
    <div className="container py-10">
      <PageHeader
        title="Company Management"
        description="Create and view your company information."
      />

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Create company</CardTitle>
            <CardDescription>
              Register your company before posting jobs.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <CompanyForm onCreated={setCompany} />
          </CardContent>
        </Card>

        <div className="space-y-4">
          {company ? (
            <div className="space-y-4">
              <h2 className="text-lg font-semibold">Your company</h2>
              <CompanyCard company={company} />
              <Link to="/recruiter/jobs/new">
                <Button className="w-full sm:w-auto">
                  Post a job for this company
                </Button>
              </Link>
            </div>
          ) : (
            <Card>
              <CardContent className="py-8 text-center text-sm text-muted-foreground">
                No company created yet. Use the form to create one.
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </div>
  )
}
