import { Mail, Phone, Award, Briefcase, GraduationCap } from 'lucide-react'
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
    <Card className="border-border/70 shadow-soft">
      <CardHeader>
        <CardTitle className="font-display text-xl font-bold">
          {resume.full_name ?? 'Ứng viên chưa có tên'}
        </CardTitle>
        <CardDescription>{resume.title ?? 'Chưa có chức danh'}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        <div className="flex flex-wrap gap-x-6 gap-y-2 text-sm text-muted-foreground">
          {resume.email ? (
            <span className="flex items-center gap-1.5">
              <Mail className="h-4 w-4" aria-hidden="true" />
              {resume.email}
            </span>
          ) : null}
          {resume.phone ? (
            <span className="flex items-center gap-1.5">
              <Phone className="h-4 w-4" aria-hidden="true" />
              {resume.phone}
            </span>
          ) : null}
          {resume.total_years_experience != null ? (
            <span className="flex items-center gap-1.5">
              <Briefcase className="h-4 w-4" aria-hidden="true" />
              {resume.total_years_experience} năm kinh nghiệm
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
            <h3 className="mb-2 font-display text-sm font-semibold">Kỹ năng</h3>
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
            <h3 className="mb-2 font-display text-sm font-semibold">
              Kinh nghiệm
            </h3>
            <ul className="space-y-3">
              {resume.experiences.map((exp, index) => (
                <li
                  key={index}
                  className="rounded-xl border bg-muted/20 p-4 text-sm"
                >
                  <p className="font-medium text-foreground">
                    {exp.position ?? 'Vị trí'}
                    {exp.company ? ` tại ${exp.company}` : ''}
                  </p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {exp.start_date ?? ''}
                    {exp.start_date && exp.end_date ? ' — ' : ''}
                    {exp.end_date ?? (exp.is_current ? 'Hiện tại' : '')}
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
            <h3 className="mb-2 font-display text-sm font-semibold">Học vấn</h3>
            <ul className="space-y-3">
              {resume.education.map((edu, index) => (
                <li
                  key={index}
                  className="rounded-xl border bg-muted/20 p-4 text-sm"
                >
                  <p className="flex items-center gap-1.5 font-medium text-foreground">
                    <GraduationCap
                      className="h-4 w-4 text-primary"
                      aria-hidden="true"
                    />
                    {edu.degree ?? 'Bằng cấp'}
                    {edu.field_of_study ? ` — ${edu.field_of_study}` : ''}
                  </p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {edu.institution ?? 'Cơ sở đào tạo'}
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
            <h3 className="mb-2 flex items-center gap-1 font-display text-sm font-semibold">
              <Award className="h-4 w-4 text-primary" aria-hidden="true" />
              Chứng chỉ
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
            <h3 className="mb-2 font-display text-sm font-semibold">
              Ngôn ngữ
            </h3>
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
            Không có thông tin chi tiết nào khác được trích xuất từ CV này.
          </p>
        ) : null}
      </CardContent>
    </Card>
  )
}