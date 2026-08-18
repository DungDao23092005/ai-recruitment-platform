import { Link, useNavigate } from 'react-router-dom'
import {
  ArrowRight,
  BrainCircuit,
  Briefcase,
  CheckCircle2,
  ClipboardList,
  FileText,
  MessageSquareText,
  Search,
  Sparkles,
  Upload,
  Users,
} from 'lucide-react'
import { Button, buttonVariants } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { cn } from '@/utils/cn'
import { Progress } from '@/components/ui/progress'
import { ScoreRing } from '@/components/ui/score-ring'
import { Skeleton } from '@/components/ui/skeleton'
import { ErrorBanner } from '@/components/ui/error-banner'
import { EmptyState } from '@/components/ui/empty-state'
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { useJobs } from '@/features/jobs/hooks/useJobs'
import { JobCard } from '@/features/jobs/components/JobCard'

const HERO_HIGHLIGHTS = [
  'Đối sánh ngữ nghĩa',
  'Trợ lý AI 24/7',
  'Bộ câu hỏi phỏng vấn tự động',
]

const STEPS = [
  {
    icon: Upload,
    title: 'Tạo hồ sơ & Upload CV',
    description:
      'Đăng ký tài khoản, điền thông tin và tải lên CV PDF. AI tự động phân tích kỹ năng và kinh nghiệm của bạn.',
  },
  {
    icon: BrainCircuit,
    title: 'AI đối sánh theo ngữ nghĩa',
    description:
      'Hệ thống đối sánh hồ sơ với tin tuyển dụng dựa trên ý nghĩa thực sự của kỹ năng, không chỉ từ khóa.',
  },
  {
    icon: Users,
    title: 'Kết nối đúng người — đúng việc',
    description:
      'Nhận gợi ý việc làm phù hợp hoặc danh sách ứng viên tiềm năng kèm điểm đối sánh và lý do rõ ràng.',
  },
]

const AI_FEATURES = [
  {
    icon: BrainCircuit,
    title: 'Đối sánh CV thông minh',
    description:
      'Chấm điểm ứng viên theo kỹ năng, kinh nghiệm và yêu cầu công việc với độ chính xác cao.',
  },
  {
    icon: Search,
    title: 'Tìm kiếm ngữ nghĩa',
    description:
      'Mô tả công việc hoặc ứng viên bạn cần bằng ngôn ngữ tự nhiên — AI tìm kết quả đúng ý bạn.',
  },
  {
    icon: MessageSquareText,
    title: 'Trợ lý AI nghề nghiệp',
    description:
      'Hỏi đáp về lộ trình, kỹ năng và cơ hội tuyển dụng dựa trên dữ liệu thực tế của nền tảng.',
  },
  {
    icon: ClipboardList,
    title: 'Bộ câu hỏi phỏng vấn',
    description:
      'Tự động sinh câu hỏi phỏng vấn kèm tiêu chí đánh giá và gợi ý trả lời theo từng tin tuyển dụng.',
  },
]

function HeroMatchPreview() {
  return (
    <div className="relative">
      <div
        className="ai-gradient absolute -inset-8 rounded-full opacity-10 blur-3xl"
        aria-hidden="true"
      />
      <Card className="card-hover relative mx-auto w-full max-w-sm border-border/70 shadow-soft-lg">
        <CardHeader className="flex-row items-start justify-between gap-3 space-y-0">
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-primary/10 font-display text-lg font-bold text-primary">
              A
            </div>
            <div className="min-w-0">
              <p className="truncate font-display text-sm font-semibold text-foreground">
                Nguyễn Văn An
              </p>
              <p className="text-xs text-muted-foreground">
                AI Engineer · 5 năm kinh nghiệm
              </p>
            </div>
          </div>
          <Badge variant="ai-gradient">AI Match</Badge>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center gap-5">
            <ScoreRing value={92} size={84} label="Điểm đối sánh 92 phần trăm" />
            <div className="flex-1 space-y-3">
              <div>
                <div className="flex items-center justify-between text-xs">
                  <span className="text-muted-foreground">Kỹ năng</span>
                  <span className="font-semibold text-foreground">95%</span>
                </div>
                <Progress value={95} variant="ai" className="mt-1.5" />
              </div>
              <div>
                <div className="flex items-center justify-between text-xs">
                  <span className="text-muted-foreground">Kinh nghiệm</span>
                  <span className="font-semibold text-foreground">88%</span>
                </div>
                <Progress value={88} variant="ai" className="mt-1.5" />
              </div>
            </div>
          </div>

          <div className="flex flex-wrap gap-2">
            {['Python', 'FastAPI', 'LLM', 'Machine Learning'].map((skill) => (
              <Badge key={skill} variant="neutral">
                {skill}
              </Badge>
            ))}
          </div>

          <p className="flex items-start gap-2 rounded-lg bg-primary/5 p-3 text-sm leading-relaxed text-muted-foreground">
            <Sparkles
              className="mt-0.5 h-4 w-4 shrink-0 text-primary"
              aria-hidden="true"
            />
            Ứng viên khớp{' '}
            <strong className="font-semibold text-foreground">92%</strong> với
            tin tuyển dụng &quot;AI Engineer&quot; — kỹ năng Python và FastAPI
            trùng khớp gần như hoàn toàn.
          </p>

          <Link
            to="/candidate/recommendations"
            className={cn(
              buttonVariants({ variant: 'outline', size: 'lg' }),
              'w-full',
            )}
          >
            Xem chi tiết đối sánh
            <ArrowRight className="h-4 w-4" aria-hidden="true" />
          </Link>
        </CardContent>
      </Card>
      <p className="mt-3 text-center text-xs text-muted-foreground">
        Minh họa giao diện đối sánh AI của nền tảng
      </p>
    </div>
  )
}

function LatestJobsSection() {
  const { jobs, isLoading, error, refresh } = useJobs()

  return (
    <section className="container py-16 sm:py-20">
      <div className="flex flex-col gap-4 pb-8 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-primary">
            Cơ hội mới
          </p>
          <h2 className="mt-1.5 font-display text-2xl font-bold tracking-tight sm:text-3xl">
            Việc làm mới nhất
          </h2>
        </div>
        <Link to="/jobs">
          <Button variant="outline">
            Xem tất cả việc làm
            <ArrowRight className="ml-2 h-4 w-4" aria-hidden="true" />
          </Button>
        </Link>
      </div>

      {isLoading ? (
        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, index) => (
            <Card key={index} className="p-5">
              <Skeleton className="h-5 w-3/4" />
              <Skeleton className="mt-3 h-4 w-1/2" />
              <Skeleton className="mt-4 h-16 w-full" />
              <Skeleton className="mt-4 h-9 w-full" />
            </Card>
          ))}
        </div>
      ) : error ? (
        <ErrorBanner message={error} onRetry={refresh} />
      ) : jobs.length === 0 ? (
        <EmptyState
          icon={<FileText className="h-5 w-5" aria-hidden="true" />}
          title="Chưa có việc làm nào"
          description="Hiện tại nền tảng chưa có tin tuyển dụng. Quay lại sau để khám phá cơ hội mới nhé!"
        />
      ) : (
        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
          {jobs.slice(0, 6).map((job) => (
            <JobCard key={job.id} job={job} />
          ))}
        </div>
      )}
    </section>
  )
}

function HeroSearchBar() {
  const navigate = useNavigate()
  return (
    <form
      className="mt-8 flex w-full max-w-xl flex-col gap-2 sm:flex-row"
      onSubmit={(event) => {
        event.preventDefault()
        navigate('/jobs')
      }}
    >
      <div className="relative flex-1">
        <Search
          className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
          aria-hidden="true"
        />
        <Input
          name="q"
          type="search"
          aria-label="Tìm kiếm việc làm"
          placeholder="Nhập tên công việc, kỹ năng..."
          className="h-11 pl-9"
        />
      </div>
      <Button type="submit" size="lg" className="h-11 w-full sm:w-auto">
        Tìm việc ngay
        <ArrowRight className="h-4 w-4" aria-hidden="true" />
      </Button>
    </form>
  )
}

export function HomePage() {
  return (
    <div className="relative">
      <div className="bg-grid-fade pointer-events-none absolute inset-x-0 top-0 h-[560px]" aria-hidden="true" />

      <section className="container relative pb-16 pt-14 sm:pt-20">
        <div className="grid items-center gap-12 lg:grid-cols-2 lg:gap-16">
          <div className="max-w-2xl">
            <p className="inline-flex items-center gap-2 rounded-full border border-primary/20 bg-primary/5 px-3 py-1 text-xs font-semibold text-primary">
              <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
              Nền tảng tuyển dụng thông minh tại Việt Nam
            </p>
            <h1 className="mt-5 font-display text-4xl font-bold leading-[1.08] tracking-tight sm:text-5xl">
              Tìm đúng công việc.
              <br className="hidden sm:block" />
              Tìm đúng ứng viên.
              <br />
              <span className="ai-text">Nhanh hơn với AI.</span>
            </h1>
            <p className="mt-5 max-w-xl text-base leading-relaxed text-muted-foreground sm:text-lg">
              Nền tảng kết nối ứng viên và nhà tuyển dụng bằng trí tuệ nhân
              tạo — đối sánh CV theo ngữ nghĩa, gợi ý việc làm và tìm ứng viên
              phù hợp chỉ trong vài giây.
            </p>
            <HeroSearchBar />
            <ul className="mt-8 flex flex-wrap items-center gap-x-6 gap-y-2 text-sm text-muted-foreground">
              {HERO_HIGHLIGHTS.map((item) => (
                <li key={item} className="flex items-center gap-1.5">
                  <CheckCircle2
                    className="h-4 w-4 text-success"
                    aria-hidden="true"
                  />
                  {item}
                </li>
              ))}
            </ul>
          </div>

          <HeroMatchPreview />
        </div>
      </section>

      <section className="border-y bg-muted/40">
        <div className="container py-16">
          <div className="mx-auto max-w-2xl text-center">
            <p className="text-xs font-semibold uppercase tracking-wider text-primary">
              Cách hoạt động
            </p>
            <h2 className="mt-1.5 font-display text-2xl font-bold tracking-tight sm:text-3xl">
              Từ hồ sơ đến kết nối — chỉ trong 3 bước
            </h2>
          </div>
          <div className="mt-12 grid gap-8 md:grid-cols-3">
            {STEPS.map((step, index) => (
              <div key={step.title} className="relative text-center">
                <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-primary/10 text-primary ring-1 ring-primary/15">
                  <step.icon className="h-6 w-6" aria-hidden="true" />
                </div>
                <p className="mt-4 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  Bước {index + 1}
                </p>
                <h3 className="mt-1 font-display text-lg font-semibold">
                  {step.title}
                </h3>
                <p className="mx-auto mt-2 max-w-xs text-sm leading-relaxed text-muted-foreground">
                  {step.description}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="container py-16 sm:py-20">
        <div className="mx-auto max-w-2xl text-center">
          <p className="text-xs font-semibold uppercase tracking-wider text-primary">
            Khả năng AI
          </p>
          <h2 className="mt-1.5 font-display text-2xl font-bold tracking-tight sm:text-3xl">
            Trợ lý tuyển dụng thông minh, toàn diện
          </h2>
          <p className="mt-3 text-muted-foreground">
            Từ đối sánh hồ sơ đến sinh câu hỏi phỏng vấn — AI hỗ trợ trọn vẹn
            hành trình tuyển dụng.
          </p>
        </div>
        <div className="mt-12 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
          {AI_FEATURES.map((feature) => (
            <Card
              key={feature.title}
              className="card-hover border-border/70 hover:-translate-y-0.5 hover:border-primary/30 hover:shadow-soft"
            >
              <CardHeader>
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10 text-primary">
                  <feature.icon className="h-5 w-5" aria-hidden="true" />
                </div>
                <CardTitle className="pt-2 font-display text-base font-semibold">
                  {feature.title}
                </CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-sm leading-relaxed text-muted-foreground">
                  {feature.description}
                </p>
              </CardContent>
            </Card>
          ))}
        </div>
      </section>

      <LatestJobsSection />

      <section className="container pb-16 sm:pb-20">
        <div className="grid gap-6 lg:grid-cols-2">
          <Card className="card-hover border-border/70 p-8 hover:border-primary/30 hover:shadow-soft">
            <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-primary/10 text-primary">
              <Users className="h-5 w-5" aria-hidden="true" />
            </div>
            <h3 className="mt-4 font-display text-xl font-bold">Dành cho ứng viên</h3>
            <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
              Tải lên CV và để AI gợi ý những công việc phù hợp nhất với kỹ
              năng của bạn. Theo dõi đơn ứng tuyển và chuẩn bị phỏng vấn tốt
              hơn.
            </p>
            <div className="mt-6">
              <Link to="/register">
                <Button>
                  Khám phá việc làm
                  <ArrowRight className="h-4 w-4" aria-hidden="true" />
                </Button>
              </Link>
            </div>
          </Card>
          <Card className="card-hover border-border/70 p-8 hover:border-primary/30 hover:shadow-soft">
            <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-primary/10 text-primary">
              <Briefcase className="h-5 w-5" aria-hidden="true" />
            </div>
            <h3 className="mt-4 font-display text-xl font-bold">Dành cho nhà tuyển dụng</h3>
            <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
              Đăng tin tuyển dụng, nhận danh sách ứng viên được xếp hạng theo
              điểm đối sánh AI và sinh bộ câu hỏi phỏng vấn ngay trong vài giây.
            </p>
            <div className="mt-6">
              <Link to="/register">
                <Button>
                  Tuyển dụng thông minh
                  <ArrowRight className="h-4 w-4" aria-hidden="true" />
                </Button>
              </Link>
            </div>
          </Card>
        </div>
      </section>

      <section className="container pb-16 sm:pb-24">
        <div className="ai-gradient relative overflow-hidden rounded-3xl px-6 py-14 text-center text-white sm:px-12">
          <div className="absolute inset-0 bg-grid opacity-15" aria-hidden="true" />
          <div className="relative mx-auto max-w-2xl">
            <h2 className="font-display text-2xl font-bold tracking-tight sm:text-3xl">
              Bắt đầu hành trình tuyển dụng thông minh ngay hôm nay
            </h2>
            <p className="mt-3 text-white/85">
              Miễn phí cho ứng viên. Nhanh chóng, chính xác và hoàn toàn bằng
              tiếng Việt.
            </p>
            <div className="mt-7 flex flex-wrap items-center justify-center gap-3">
              <Link to="/register">
                <Button
                  size="lg"
                  variant="secondary"
                  className="bg-white text-primary hover:bg-white/90"
                >
                  Tạo tài khoản ngay
                </Button>
              </Link>
              <Link to="/jobs">
                <Button
                  size="lg"
                  variant="ghost"
                  className="border border-white/40 text-white hover:bg-white/10 hover:text-white"
                >
                  Xem danh sách việc làm
                </Button>
              </Link>
            </div>
          </div>
        </div>
      </section>
    </div>
  )
}