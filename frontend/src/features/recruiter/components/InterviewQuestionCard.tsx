import { ClipboardList, Target, CheckCircle2 } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import {
  Card,
  CardContent,
  CardHeader,
} from '@/components/ui/card'
import type {
  InterviewQuestion,
  QuestionCategory,
  QuestionDifficulty,
} from '@/types/ai'

export const CATEGORY_LABELS: Record<QuestionCategory, string> = {
  technical: 'Technical',
  behavioral: 'Behavioral',
  experience: 'Experience',
  skill_gap: 'Skill Gap',
}

export const DIFFICULTY_LABELS: Record<QuestionDifficulty, string> = {
  easy: 'Dễ',
  medium: 'Trung bình',
  hard: 'Khó',
}

export interface InterviewQuestionCardProps {
  index: number
  question: InterviewQuestion
}

export function InterviewQuestionCard({
  index,
  question,
}: InterviewQuestionCardProps) {
  return (
    <Card className="flex h-full flex-col">
      <CardHeader className="flex-row items-start justify-between gap-3 space-y-0">
        <div className="flex items-start gap-2">
          <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-secondary text-sm font-bold text-secondary-foreground">
            {index + 1}
          </span>
          <h3 className="text-sm font-semibold leading-relaxed">
            {question.question}
          </h3>
        </div>
        <div className="flex shrink-0 flex-col items-end gap-1">
          <Badge variant="ai-gradient">{CATEGORY_LABELS[question.category]}</Badge>
          <Badge variant="neutral">{DIFFICULTY_LABELS[question.difficulty]}</Badge>
        </div>
      </CardHeader>
      <CardContent className="flex flex-1 flex-col gap-3 text-sm">
        <div className="flex items-start gap-2">
          <Target
            className="mt-0.5 h-4 w-4 shrink-0 text-primary"
            aria-hidden="true"
          />
          <div>
            <p className="text-xs font-medium text-muted-foreground">
              Kỹ năng / chủ đề
            </p>
            <p className="text-muted-foreground">
              {question.target_skill_or_topic}
            </p>
          </div>
        </div>
        <div className="flex items-start gap-2">
          <ClipboardList
            className="mt-0.5 h-4 w-4 shrink-0 text-primary"
            aria-hidden="true"
          />
          <div>
            <p className="text-xs font-medium text-muted-foreground">
              Tiêu chí đánh giá
            </p>
            <p className="text-muted-foreground">
              {question.evaluation_criteria}
            </p>
          </div>
        </div>
        <div className="flex items-start gap-2">
          <CheckCircle2
            className="mt-0.5 h-4 w-4 shrink-0 text-primary"
            aria-hidden="true"
          />
          <div>
            <p className="text-xs font-medium text-muted-foreground">
              Gợi ý câu trả lời
            </p>
            <ul className="list-inside list-disc space-y-0.5 text-muted-foreground">
              {question.sample_answer_points.map((point) => (
                <li key={point}>{point}</li>
              ))}
            </ul>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
