import { Mail, Phone, Award, Briefcase } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import type { ParsedResume } from '@/types/ai'

export interface ParsedResumeViewProps {
  resume: ParsedResume
}

export function ParsedResumeView({ resume }: ParsedResumeViewProps) {
  const hasExperiences = resume.experiences.length > 0
  const hasEducation = resume.education.length > 0
  const hasCertifications = resume.certifications.length > 0
  const hasLanguages = resume.languages.length > 0

  return (
    <Card>
      <CardHeader>
        <CardTitle>{resume.full_name ?? 'Unnamed candidate'}</CardTitle>
        <CardDescription>{resume.title ?? 'No title'}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        <div className="flex flex-wrap gap-x-6 gap-y-2 text-sm text-muted-foreground">
          {resume.email ? (
            <span className="flex items-center gap-1">
              <Mail className="h-4 w-4" aria-hidden="true" />
              {resume.email}
            </span>
          ) : null}
          {resume.phone ? (
            <span className="flex items-center gap-1">
              <Phone className="h-4 w-4" aria-hidden="true" />
              {resume.phone}
            </span>
          ) : null}
          {resume.total_years_experience != null ? (
            <span className="flex items-center gap-1">
              <Briefcase className="h-4 w-4" aria-hidden="true" />
              {resume.total_years_experience} years experience
            </span>
          ) : null}
        </div>

        {resume.summary ? (
          <p className="text-sm leading-relaxed text-muted-foreground">
            {resume.summary}
          </p>
        ) : null}

        {resume.skills.length > 0 ? (
          <div>
            <h3 className="mb-2 text-sm font-semibold">Skills</h3>
            <div className="flex flex-wrap gap-2">
              {resume.skills.map((skill) => (
                <Badge key={skill} variant="ai-gradient">
                  {skill}
                </Badge>
              ))}
            </div>
          </div>
        ) : null}

        {hasExperiences ? (
          <div>
            <h3 className="mb-2 text-sm font-semibold">Experience</h3>
            <ul className="space-y-3">
              {resume.experiences.map((exp, index) => (
                <li key={index} className="rounded-md border p-3 text-sm">
                  <p className="font-medium">
                    {exp.position ?? 'Position'}
                    {exp.company ? ` at ${exp.company}` : ''}
                  </p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {exp.start_date ?? ''}
                    {exp.start_date && exp.end_date ? ' - ' : ''}
                    {exp.end_date ?? (exp.is_current ? 'Present' : '')}
                  </p>
                  {exp.description ? (
                    <p className="mt-1 text-muted-foreground">
                      {exp.description}
                    </p>
                  ) : null}
                  {exp.skills_used.length > 0 ? (
                    <div className="mt-2 flex flex-wrap gap-1">
                      {exp.skills_used.map((skill) => (
                        <Badge key={skill} variant="neutral">
                          {skill}
                        </Badge>
                      ))}
                    </div>
                  ) : null}
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        {hasEducation ? (
          <div>
            <h3 className="mb-2 text-sm font-semibold">Education</h3>
            <ul className="space-y-3">
              {resume.education.map((edu, index) => (
                <li key={index} className="rounded-md border p-3 text-sm">
                  <p className="font-medium">
                    {edu.degree ?? 'Degree'}
                    {edu.field_of_study ? ` in ${edu.field_of_study}` : ''}
                  </p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {edu.institution ?? 'Institution'}
                    {edu.start_year ? `, ${edu.start_year}` : ''}
                    {edu.end_year ? ` - ${edu.end_year}` : ''}
                  </p>
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        {hasCertifications ? (
          <div>
            <h3 className="mb-2 flex items-center gap-1 text-sm font-semibold">
              <Award className="h-4 w-4" aria-hidden="true" />
              Certifications
            </h3>
            <ul className="flex flex-wrap gap-2">
              {resume.certifications.map((cert) => (
                <li key={cert}>
                  <Badge variant="neutral">{cert}</Badge>
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        {hasLanguages ? (
          <div>
            <h3 className="mb-2 text-sm font-semibold">Languages</h3>
            <div className="flex flex-wrap gap-2">
              {resume.languages.map((lang) => (
                <Badge key={lang} variant="neutral">
                  {lang}
                </Badge>
              ))}
            </div>
          </div>
        ) : null}

        {!hasExperiences &&
        !hasEducation &&
        resume.skills.length === 0 &&
        !hasCertifications &&
        !hasLanguages ? (
          <p className="text-sm text-muted-foreground">
            No additional details were extracted from this resume.
          </p>
        ) : null}
      </CardContent>
    </Card>
  )
}