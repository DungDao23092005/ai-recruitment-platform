import { CircleHelp, MessageCircleQuestion } from 'lucide-react'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { cn } from '@/utils/cn'

export interface AreasForInquiryCardProps {
  areas: string[]
  className?: string
}

export function AreasForInquiryCard({
  areas,
  className,
}: AreasForInquiryCardProps) {
  return (
    <Card className={cn('border-info/30 bg-info/5', className)}>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 font-display text-base font-semibold">
          <span className="flex h-7 w-7 items-center justify-center rounded-full bg-info/10 text-info">
            <MessageCircleQuestion className="h-4 w-4" aria-hidden="true" />
          </span>
          Gợi ý câu hỏi phỏng vấn
        </CardTitle>
        <CardDescription>
          Các điểm nên làm rõ thêm với ứng viên trong buổi phỏng vấn.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {areas.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Chưa có gợi ý câu hỏi cho ứng viên này.
          </p>
        ) : (
          <ul className="space-y-2.5">
            {areas.map((area, index) => (
              <li
                key={`inquiry-${index}`}
                className="flex items-start gap-2.5 text-sm leading-relaxed text-foreground"
              >
                <CircleHelp
                  className="mt-0.5 h-4 w-4 shrink-0 text-info"
                  aria-hidden="true"
                />
                <span className="min-w-0 break-words">{area}</span>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}
