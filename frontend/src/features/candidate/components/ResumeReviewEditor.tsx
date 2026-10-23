import { useEffect, useState } from 'react'
import {
  AlertCircle,
  CheckCircle2,
  Plus,
  Save,
  Trash2,
} from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import type {
  Education,
  ParsedResume,
  ResumeRead,
  WorkExperience,
} from '@/types/ai'

interface ExperienceDraft {
  company: string
  position: string
  start_date: string
  end_date: string
  is_current: boolean
  description: string
  skillsText: string
}

interface EducationDraft {
  institution: string
  degree: string
  field_of_study: string
  startYearText: string
  endYearText: string
}

interface ResumeFields {
  full_name: string
  email: string
  phone: string
  title: string
  summary: string
  totalYearsText: string
}

interface ResumeEditorState {
  fields: ResumeFields
  skillsText: string
  experiences: ExperienceDraft[]
  education: EducationDraft[]
  certificationsText: string
  languagesText: string
}

export interface ResumeReviewEditorProps {
  resume: ResumeRead
  isSaving: boolean
  isConfirming: boolean
  replacingActive?: boolean
  onSave: (parsed: ParsedResume) => void
  onConfirm: (parsed: ParsedResume) => void
}

const EMPTY_RESUME: ParsedResume = {
  full_name: null,
  email: null,
  phone: null,
  title: null,
  summary: null,
  total_years_experience: null,
  skills: [],
  experiences: [],
  education: [],
  certifications: [],
  languages: [],
}

function splitList(value: string): string[] {
  return value
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean)
}

function nullable(value: string): string | null {
  const trimmed = value.trim()
  return trimmed ? trimmed : null
}

function parseYear(value: string): number | null {
  const trimmed = value.trim()
  if (!trimmed) {
    return null
  }
  const parsed = Number.parseInt(trimmed, 10)
  return Number.isFinite(parsed) ? parsed : null
}

function experienceToDraft(experience: WorkExperience): ExperienceDraft {
  return {
    company: experience.company ?? '',
    position: experience.position ?? '',
    start_date: experience.start_date ?? '',
    end_date: experience.end_date ?? '',
    is_current: experience.is_current,
    description: experience.description ?? '',
    skillsText: experience.skills_used.join(', '),
  }
}

function educationToDraft(education: Education): EducationDraft {
  return {
    institution: education.institution ?? '',
    degree: education.degree ?? '',
    field_of_study: education.field_of_study ?? '',
    startYearText:
      education.start_year != null ? String(education.start_year) : '',
    endYearText:
      education.end_year != null ? String(education.end_year) : '',
  }
}

function buildEditorState(parsed: ParsedResume | null): ResumeEditorState {
  const resume = parsed ?? EMPTY_RESUME
  return {
    fields: {
      full_name: resume.full_name ?? '',
      email: resume.email ?? '',
      phone: resume.phone ?? '',
      title: resume.title ?? '',
      summary: resume.summary ?? '',
      totalYearsText:
        resume.total_years_experience != null
          ? String(resume.total_years_experience)
          : '',
    },
    skillsText: resume.skills.join(', '),
    experiences: resume.experiences.map(experienceToDraft),
    education: resume.education.map(educationToDraft),
    certificationsText: resume.certifications.join(', '),
    languagesText: resume.languages.join(', '),
  }
}

export function ResumeReviewEditor({
  resume,
  isSaving,
  isConfirming,
  replacingActive = false,
  onSave,
  onConfirm,
}: ResumeReviewEditorProps) {
  const [initialState] = useState(() =>
    buildEditorState(resume.parsed_data),
  )
  const [fields, setFields] = useState<ResumeFields>(initialState.fields)
  const [skillsText, setSkillsText] = useState(initialState.skillsText)
  const [experiences, setExperiences] = useState<ExperienceDraft[]>(
    initialState.experiences,
  )
  const [education, setEducation] = useState<EducationDraft[]>(
    initialState.education,
  )
  const [certificationsText, setCertificationsText] = useState(
    initialState.certificationsText,
  )
  const [languagesText, setLanguagesText] = useState(
    initialState.languagesText,
  )
  const [validationError, setValidationError] = useState<string | null>(null)

  useEffect(() => {
    const nextState = buildEditorState(resume.parsed_data)
    setFields(nextState.fields)
    setSkillsText(nextState.skillsText)
    setExperiences(nextState.experiences)
    setEducation(nextState.education)
    setCertificationsText(nextState.certificationsText)
    setLanguagesText(nextState.languagesText)
    setValidationError(null)
  }, [resume.id, resume.updated_at, resume.parsed_data])

  const busy = isSaving || isConfirming

  const updateExperience = (
    index: number,
    patch: Partial<ExperienceDraft>,
  ) => {
    setExperiences((current) =>
      current.map((experience, itemIndex) =>
        itemIndex === index ? { ...experience, ...patch } : experience,
      ),
    )
  }

  const updateEducation = (index: number, patch: Partial<EducationDraft>) => {
    setEducation((current) =>
      current.map((item, itemIndex) =>
        itemIndex === index ? { ...item, ...patch } : item,
      ),
    )
  }

  const buildPayload = (): ParsedResume => {
    const base = resume.parsed_data ?? EMPTY_RESUME
    const totalYears = fields.totalYearsText.trim()
      ? Number(fields.totalYearsText)
      : null

    return {
      ...base,
      full_name: nullable(fields.full_name),
      email: nullable(fields.email),
      phone: nullable(fields.phone),
      title: nullable(fields.title),
      summary: nullable(fields.summary),
      total_years_experience:
        totalYears != null && Number.isFinite(totalYears) ? totalYears : null,
      skills: splitList(skillsText),
      experiences: experiences.map((experience) => ({
        company: nullable(experience.company),
        position: nullable(experience.position),
        start_date: nullable(experience.start_date),
        end_date: experience.is_current
          ? null
          : nullable(experience.end_date),
        is_current: experience.is_current,
        description: nullable(experience.description),
        skills_used: splitList(experience.skillsText),
      })),
      education: education.map((item) => ({
        institution: nullable(item.institution),
        degree: nullable(item.degree),
        field_of_study: nullable(item.field_of_study),
        start_year: parseYear(item.startYearText),
        end_year: parseYear(item.endYearText),
      })),
      certifications: splitList(certificationsText),
      languages: splitList(languagesText),
    }
  }

  const validate = (): string | null => {
    const email = fields.email.trim()
    if (email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      return 'Email chưa đúng định dạng.'
    }

    const totalYears = fields.totalYearsText.trim()
    if (totalYears) {
      const parsed = Number(totalYears)
      if (!Number.isFinite(parsed) || parsed < 0) {
        return 'Số năm kinh nghiệm phải là số không âm.'
      }
    }

    return null
  }

  const submit = (action: (parsed: ParsedResume) => void) => {
    const error = validate()
    if (error) {
      setValidationError(error)
      return
    }
    setValidationError(null)
    action(buildPayload())
  }

  return (
    <Card className="border-primary/30 shadow-soft">
      <CardHeader>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <CardTitle className="font-display text-xl font-bold">
              Xem lại và xác nhận CV
            </CardTitle>
            <CardDescription className="mt-1">
              Kiểm tra thông tin AI đã trích xuất, chỉnh sửa nếu cần rồi xác
              nhận để dùng CV này.
            </CardDescription>
          </div>
          <Badge variant="warning">Chưa xác nhận</Badge>
        </div>
        {resume.title ? (
          <p className="text-xs text-muted-foreground">{resume.title}</p>
        ) : null}
      </CardHeader>

      <CardContent className="space-y-6">
        <div className="rounded-xl border border-primary/20 bg-primary/5 p-4 text-sm text-muted-foreground">
          <p className="flex items-start gap-2">
            <AlertCircle
              className="mt-0.5 h-4 w-4 shrink-0 text-primary"
              aria-hidden="true"
            />
            {replacingActive
              ? 'CV hiện tại vẫn được dùng để ghép nối và tìm kiếm cho đến khi bạn xác nhận CV mới.'
              : 'CV này chưa được dùng để ghép nối hoặc tìm kiếm cho đến khi bạn xác nhận.'}
          </p>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <Input
            label="Họ và tên"
            name="resume-full-name"
            value={fields.full_name}
            onChange={(event) =>
              setFields((current) => ({
                ...current,
                full_name: event.target.value,
              }))
            }
            disabled={busy}
          />
          <Input
            label="Chức danh"
            name="resume-title"
            value={fields.title}
            onChange={(event) =>
              setFields((current) => ({
                ...current,
                title: event.target.value,
              }))
            }
            disabled={busy}
          />
          <Input
            label="Email"
            name="resume-email"
            type="email"
            value={fields.email}
            onChange={(event) =>
              setFields((current) => ({
                ...current,
                email: event.target.value,
              }))
            }
            disabled={busy}
          />
          <Input
            label="Số điện thoại"
            name="resume-phone"
            value={fields.phone}
            onChange={(event) =>
              setFields((current) => ({
                ...current,
                phone: event.target.value,
              }))
            }
            disabled={busy}
          />
          <Input
            label="Số năm kinh nghiệm"
            name="resume-total-years"
            type="number"
            min="0"
            step="0.5"
            value={fields.totalYearsText}
            onChange={(event) =>
              setFields((current) => ({
                ...current,
                totalYearsText: event.target.value,
              }))
            }
            disabled={busy}
          />
        </div>

        <Textarea
          label="Giới thiệu"
          name="resume-summary"
          value={fields.summary}
          onChange={(event) =>
            setFields((current) => ({
              ...current,
              summary: event.target.value,
            }))
          }
          disabled={busy}
        />

        <Textarea
          label="Kỹ năng"
          name="resume-skills"
          value={skillsText}
          onChange={(event) => setSkillsText(event.target.value)}
          helperText="Phân tách các kỹ năng bằng dấu phẩy."
          disabled={busy}
        />

        <section className="space-y-3">
          <div className="flex items-center justify-between gap-3">
            <h3 className="font-display text-sm font-semibold">
              Kinh nghiệm
            </h3>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() =>
                setExperiences((current) => [
                  ...current,
                  {
                    company: '',
                    position: '',
                    start_date: '',
                    end_date: '',
                    is_current: false,
                    description: '',
                    skillsText: '',
                  },
                ])
              }
              disabled={busy}
            >
              <Plus aria-hidden="true" />
              Thêm kinh nghiệm
            </Button>
          </div>

          {experiences.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              Chưa có kinh nghiệm nào được trích xuất.
            </p>
          ) : null}

          {experiences.map((experience, index) => (
            <div
              key={index}
              className="space-y-3 rounded-xl border bg-muted/20 p-4"
            >
              <div className="grid gap-3 sm:grid-cols-2">
                <Input
                  label="Công ty"
                  name={`resume-experience-company-${index}`}
                  value={experience.company}
                  onChange={(event) =>
                    updateExperience(index, { company: event.target.value })
                  }
                  disabled={busy}
                />
                <Input
                  label="Vị trí"
                  name={`resume-experience-position-${index}`}
                  value={experience.position}
                  onChange={(event) =>
                    updateExperience(index, { position: event.target.value })
                  }
                  disabled={busy}
                />
                <Input
                  label="Bắt đầu"
                  name={`resume-experience-start-${index}`}
                  value={experience.start_date}
                  onChange={(event) =>
                    updateExperience(index, {
                      start_date: event.target.value,
                    })
                  }
                  placeholder="MM/YYYY"
                  disabled={busy}
                />
                <Input
                  label="Kết thúc"
                  name={`resume-experience-end-${index}`}
                  value={experience.end_date}
                  onChange={(event) =>
                    updateExperience(index, { end_date: event.target.value })
                  }
                  placeholder="MM/YYYY"
                  disabled={busy || experience.is_current}
                />
              </div>

              <label className="flex items-center gap-2 text-sm text-muted-foreground">
                <input
                  type="checkbox"
                  checked={experience.is_current}
                  onChange={(event) =>
                    updateExperience(index, {
                      is_current: event.target.checked,
                    })
                  }
                  disabled={busy}
                  className="h-4 w-4 rounded border-input"
                />
                Đang làm việc tại đây
              </label>

              <Textarea
                label="Mô tả"
                name={`resume-experience-description-${index}`}
                value={experience.description}
                onChange={(event) =>
                  updateExperience(index, {
                    description: event.target.value,
                  })
                }
                disabled={busy}
              />

              <Textarea
                label="Kỹ năng sử dụng"
                name={`resume-experience-skills-${index}`}
                value={experience.skillsText}
                onChange={(event) =>
                  updateExperience(index, {
                    skillsText: event.target.value,
                  })
                }
                helperText="Phân tách bằng dấu phẩy."
                disabled={busy}
              />

              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() =>
                  setExperiences((current) =>
                    current.filter((_, itemIndex) => itemIndex !== index),
                  )
                }
                disabled={busy}
                aria-label={`Xóa kinh nghiệm ${index + 1}`}
              >
                <Trash2 aria-hidden="true" />
                Xóa
              </Button>
            </div>
          ))}
        </section>

        <section className="space-y-3">
          <div className="flex items-center justify-between gap-3">
            <h3 className="font-display text-sm font-semibold">Học vấn</h3>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() =>
                setEducation((current) => [
                  ...current,
                  {
                    institution: '',
                    degree: '',
                    field_of_study: '',
                    startYearText: '',
                    endYearText: '',
                  },
                ])
              }
              disabled={busy}
            >
              <Plus aria-hidden="true" />
              Thêm học vấn
            </Button>
          </div>

          {education.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              Chưa có học vấn nào được trích xuất.
            </p>
          ) : null}

          {education.map((item, index) => (
            <div
              key={index}
              className="space-y-3 rounded-xl border bg-muted/20 p-4"
            >
              <div className="grid gap-3 sm:grid-cols-2">
                <Input
                  label="Trường"
                  name={`resume-education-institution-${index}`}
                  value={item.institution}
                  onChange={(event) =>
                    updateEducation(index, {
                      institution: event.target.value,
                    })
                  }
                  disabled={busy}
                />
                <Input
                  label="Bằng cấp"
                  name={`resume-education-degree-${index}`}
                  value={item.degree}
                  onChange={(event) =>
                    updateEducation(index, { degree: event.target.value })
                  }
                  disabled={busy}
                />
                <Input
                  label="Chuyên ngành"
                  name={`resume-education-field-${index}`}
                  value={item.field_of_study}
                  onChange={(event) =>
                    updateEducation(index, {
                      field_of_study: event.target.value,
                    })
                  }
                  disabled={busy}
                />
                <div className="grid grid-cols-2 gap-3">
                  <Input
                    label="Năm bắt đầu"
                    name={`resume-education-start-${index}`}
                    type="number"
                    value={item.startYearText}
                    onChange={(event) =>
                      updateEducation(index, {
                        startYearText: event.target.value,
                      })
                    }
                    disabled={busy}
                  />
                  <Input
                    label="Năm kết thúc"
                    name={`resume-education-end-${index}`}
                    type="number"
                    value={item.endYearText}
                    onChange={(event) =>
                      updateEducation(index, {
                        endYearText: event.target.value,
                      })
                    }
                    disabled={busy}
                  />
                </div>
              </div>

              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() =>
                  setEducation((current) =>
                    current.filter((_, itemIndex) => itemIndex !== index),
                  )
                }
                disabled={busy}
                aria-label={`Xóa học vấn ${index + 1}`}
              >
                <Trash2 aria-hidden="true" />
                Xóa
              </Button>
            </div>
          ))}
        </section>

        <div className="grid gap-4 sm:grid-cols-2">
          <Textarea
            label="Chứng chỉ"
            name="resume-certifications"
            value={certificationsText}
            onChange={(event) => setCertificationsText(event.target.value)}
            helperText="Phân tách bằng dấu phẩy."
            disabled={busy}
          />
          <Textarea
            label="Ngôn ngữ"
            name="resume-languages"
            value={languagesText}
            onChange={(event) => setLanguagesText(event.target.value)}
            helperText="Phân tách bằng dấu phẩy."
            disabled={busy}
          />
        </div>

        {validationError ? (
          <p role="alert" className="text-sm font-medium text-destructive">
            {validationError}
          </p>
        ) : null}

        <div className="flex flex-wrap gap-3 border-t pt-5">
          <Button
            type="button"
            variant="outline"
            onClick={() => submit(onSave)}
            isLoading={isSaving}
            loadingText="Đang lưu..."
            disabled={isConfirming}
          >
            <Save aria-hidden="true" />
            Lưu nháp
          </Button>
          <Button
            type="button"
            onClick={() => submit(onConfirm)}
            isLoading={isConfirming}
            loadingText="Đang xác nhận..."
            disabled={isSaving}
          >
            <CheckCircle2 aria-hidden="true" />
            Xác nhận và sử dụng CV
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}
