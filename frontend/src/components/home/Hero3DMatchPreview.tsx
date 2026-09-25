import * as React from 'react'
import { cn } from '@/utils/cn'
import { useInView } from '@/hooks/useInView'
import { ScoreRing } from '@/components/ui/score-ring'
import { Progress } from '@/components/ui/progress'
import { Badge } from '@/components/ui/badge'
import { Sparkles, ArrowRight } from 'lucide-react'
import { Link } from 'react-router-dom'

interface CVCardData {
  name: string
  title: string
  experience: string
  match: number
  skills: string[]
  skillMatch: number
  experienceMatch: number
}

const CV_CARDS: CVCardData[] = [
  {
    name: 'Nguyễn Văn An',
    title: 'AI Engineer',
    experience: '5 năm kinh nghiệm',
    match: 92,
    skills: ['Python', 'FastAPI', 'LLM', 'Machine Learning'],
    skillMatch: 95,
    experienceMatch: 88,
  },
  {
    name: 'Trần Minh Khoa',
    title: 'ML Engineer',
    experience: '3 năm kinh nghiệm',
    match: 88,
    skills: ['Python', 'PyTorch', 'Computer Vision', 'MLOps'],
    skillMatch: 90,
    experienceMatch: 82,
  },
  {
    name: 'Lê Minh Anh',
    title: 'Data / AI Engineer',
    experience: '4 năm kinh nghiệm',
    match: 84,
    skills: ['Python', 'SQL', 'Spark', 'Data Engineering'],
    skillMatch: 85,
    experienceMatch: 80,
  },
]

interface Hero3DMatchPreviewProps {
  className?: string
}

export function Hero3DMatchPreview({ className }: Hero3DMatchPreviewProps) {
  const { ref, isInView } = useInView<HTMLDivElement>({
    triggerOnce: true,
    rootMargin: '0px 0px -100px',
  })

  const [rotation, setRotation] = React.useState({ x: 0, y: 0 })
  const [isDragging, setIsDragging] = React.useState(false)
  const [dragStart, setDragStart] = React.useState<{ x: number; y: number } | null>(null)
  const [startRotation, setStartRotation] = React.useState({ x: 0, y: 0 })
  const [hasMoved, setHasMoved] = React.useState(false)
  const [isHovering, setIsHovering] = React.useState(false)
  const containerRef = React.useRef<HTMLDivElement>(null)

  const prefersReducedMotion = React.useMemo(
    () => {
      if (typeof window === 'undefined') return false
      try {
        return window.matchMedia('(prefers-reduced-motion: reduce)').matches
      } catch {
        return false
      }
    },
    []
  )

  // Handle pointer down - start drag
  const handlePointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    e.currentTarget.setPointerCapture(e.pointerId)
    setIsDragging(true)
    setDragStart({ x: e.clientX, y: e.clientY })
    setStartRotation(rotation)
    setHasMoved(false)
  }

  // Handle pointer move - drag rotation
  const handlePointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!isDragging || !dragStart) return

    const deltaX = e.clientX - dragStart.x
    const deltaY = e.clientY - dragStart.y

    // Only consider it a drag if moved more than threshold
    const distance = Math.sqrt(deltaX * deltaX + deltaY * deltaY)
    if (distance > 5) {
      setHasMoved(true)
    }

    if (hasMoved) {
      const maxRotation = 45
      const sensitivity = 0.15
      const newRotationY = Math.max(-maxRotation, Math.min(maxRotation, startRotation.y + deltaX * sensitivity))
      const newRotationX = Math.max(-maxRotation, Math.min(maxRotation, startRotation.x - deltaY * sensitivity))
      setRotation({ x: newRotationX, y: newRotationY })
    }
  }

  // Handle pointer up/cancel - release drag
  const handlePointerUp = (e: React.PointerEvent<HTMLDivElement>) => {
    if (isDragging) {
      e.currentTarget.releasePointerCapture(e.pointerId)
      setIsDragging(false)
      setDragStart(null)
      // Reset rotation to neutral
      setRotation({ x: 0, y: 0 })
      // Don't reset hasMoved here - let the click handler check it
      // We'll reset it in a microtask after click event fires
    }
  }

  // Handle mouse enter - enable hover tilt
  const handleMouseEnter = () => {
    setIsHovering(true)
  }

  // Handle mouse leave - disable hover tilt
  const handleMouseLeave = () => {
    setIsHovering(false)
    // Reset rotation to neutral
    setRotation({ x: 0, y: 0 })
  }

  // Handle mouse move for hover tilt
  const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    if (isDragging) return

    const rect = e.currentTarget.getBoundingClientRect()
    const centerX = rect.left + rect.width / 2
    const centerY = rect.top + rect.height / 2
    const deltaX = e.clientX - centerX
    const deltaY = e.clientY - centerY

    const maxTilt = 25
    const tiltY = Math.max(-maxTilt, Math.min(maxTilt, (deltaX / (rect.width / 2)) * maxTilt))
    const tiltX = Math.max(-maxTilt, Math.min(maxTilt, -(deltaY / (rect.height / 2)) * maxTilt))

    setRotation({ x: tiltX, y: tiltY })
  }

  // Apply rotation transform
  const rotationStyle = {
    transform: `rotateX(${rotation.x}deg) rotateY(${rotation.y}deg)`,
    transition: prefersReducedMotion
      ? 'none'
      : isDragging || isHovering
      ? 'none'
      : 'transform 300ms ease-out',
  }

  // Float animation (disabled when dragging/hovering or reduced motion)
  const floatStyle = prefersReducedMotion || isDragging || isHovering
    ? {}
    : {
        animation: 'float 6s ease-in-out infinite',
      }

  // Count-up animation
  const frontCard = CV_CARDS[0]
  const displayMatch = isInView ? frontCard.match : 0
  const displaySkill = isInView ? frontCard.skillMatch : 0
  const displayExperience = isInView ? frontCard.experienceMatch : 0

  // Handle CTA click - prevent navigation if drag occurred
  const handleCTAClick = (e: React.MouseEvent<HTMLAnchorElement>) => {
    if (hasMoved) {
      e.preventDefault()
    }
    // Reset hasMoved after click is handled
    setHasMoved(false)
  }

  return (
    <div ref={ref} className={cn('relative', className)}>
      <div
        className="ai-gradient absolute -inset-12 rounded-full opacity-20 blur-[80px]"
        aria-hidden="true"
      />

      {/* Perspective Container */}
      <div
        ref={containerRef}
        className="relative pb-10"
        style={{
          perspective: '1200px',
          width: '100%',
          maxWidth: '380px',
          margin: '0 auto',
        }}
      >
        {/* Float Wrapper - handles only float animation */}
        <div
          className="relative"
          style={{
            transformStyle: 'preserve-3d',
            ...floatStyle,
            touchAction: 'pan-y',
          }}
          onMouseEnter={handleMouseEnter}
          onMouseLeave={handleMouseLeave}
          onMouseMove={handleMouseMove}
        >
          {/* Rotation Wrapper - handles only rotation transform */}
          <div
            ref={containerRef}
            className="relative cursor-grab active:cursor-grabbing"
            style={{
              transformStyle: 'preserve-3d',
              ...rotationStyle,
              touchAction: 'pan-y',
            }}
            onPointerDown={handlePointerDown}
            onPointerMove={handlePointerMove}
            onPointerUp={handlePointerUp}
            onPointerCancel={handlePointerUp}
          >
            {/* Right Card - Lê Minh Anh */}
            <div
              className={cn(
                'absolute inset-0',
                'bg-card border border-border/50 rounded-2xl shadow-sm',
                'p-5',
                'transition-all duration-300 ease-out',
                'ring-1 ring-foreground/5',
              )}
              style={{
                transform: 'translateZ(-40px) translateX(56px) translateY(12px) rotateZ(3deg) scale(0.96)',
                opacity: 0.7,
                zIndex: 10,
                transformStyle: 'preserve-3d',
              }}
              aria-hidden="true"
            >
              <div className="flex items-center gap-3">
                <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-primary/10 font-display text-lg font-bold text-primary">
                  L
                </div>
                <div className="min-w-0">
                  <p className="truncate font-display text-sm font-semibold text-foreground">
                    Lê Minh Anh
                  </p>
                  <p className="text-xs text-muted-foreground">
                    Data / AI Engineer · 4 năm kinh nghiệm
                  </p>
                </div>
              </div>
              <Badge variant="ai-gradient" className="mt-3 inline-block">AI Match 84%</Badge>
            </div>

            {/* Left Card - Trần Minh Khoa */}
            <div
              className={cn(
                'absolute inset-0',
                'bg-card border border-border/50 rounded-2xl shadow-sm',
                'p-5',
                'transition-all duration-300 ease-out',
                'ring-1 ring-foreground/5',
              )}
              style={{
                transform: 'translateZ(-40px) translateX(-56px) translateY(12px) rotateZ(-3deg) scale(0.96)',
                opacity: 0.7,
                zIndex: 20,
                transformStyle: 'preserve-3d',
              }}
              aria-hidden="true"
            >
              <div className="flex items-center gap-3">
                <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-primary/10 font-display text-lg font-bold text-primary">
                  T
                </div>
                <div className="min-w-0">
                  <p className="truncate font-display text-sm font-semibold text-foreground">
                    Trần Minh Khoa
                  </p>
                  <p className="text-xs text-muted-foreground">
                    ML Engineer · 3 năm kinh nghiệm
                  </p>
                </div>
              </div>
              <Badge variant="ai-gradient" className="mt-3 inline-block">AI Match 88%</Badge>
            </div>

            {/* Front Card - Nguyễn Văn An */}
            <div
              className={cn(
                'relative select-none',
                'bg-card border border-border/80 rounded-2xl shadow-soft-lg',
                'p-5',
                'transition-all duration-300 ease-out',
                'ring-1 ring-foreground/5',
              )}
              style={{
                transform: 'translateZ(60px)',
                opacity: 1,
                zIndex: 30,
                transformStyle: 'preserve-3d',
              }}
            >
              {/* Inner Content Layer - for internal parallax */}
              <div
                className="relative"
                style={{
                  transformStyle: 'preserve-3d',
                  transform: 'translateZ(30px)',
                }}
              >
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

                <div className="mt-4 space-y-4">
                  <div className="flex items-center gap-5">
                    <ScoreRing
                      value={displayMatch}
                      size={84}
                      label="Điểm đối sánh 92 phần trăm"
                      animate={isInView}
                    />
                    <div className="flex-1 space-y-3">
                      <div>
                        <div className="flex items-center justify-between text-xs">
                          <span className="text-muted-foreground">Kỹ năng</span>
                          <span className="font-semibold text-foreground">{displaySkill}%</span>
                        </div>
                        <Progress value={displaySkill} variant="ai" className="mt-1.5" animate={isInView} />
                      </div>
                      <div>
                        <div className="flex items-center justify-between text-xs">
                          <span className="text-muted-foreground">Kỹ năng</span>
                          <span className="font-semibold text-foreground">{displayExperience}%</span>
                        </div>
                        <Progress value={displayExperience} variant="ai" className="mt-1.5" animate={isInView} />
                      </div>
                    </div>
                  </div>

                  <div className="flex flex-wrap gap-2">
                    {CV_CARDS[0].skills.map((skill) => (
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
                    <span className="flex-1">
                      Ứng viên khớp{' '}
                      <strong className="font-semibold text-foreground">{displayMatch}%</strong>{' '}
                      với tin tuyển dụng "AI Engineer" — kỹ năng Python và FastAPI
                      trùng khớp gần như hoàn toàn.
                    </span>
                  </p>

                  <Link
                    to="/candidate/recommendations"
                    draggable={false}
                    className={cn(
                      'inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-lg text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 border border-input bg-background hover:bg-accent hover:text-accent-foreground h-10 px-4 py-2 w-full',
                      'w-full',
                    )}
                    onClick={handleCTAClick}
                  >
                    Xem chi tiết đối sánh
                    <ArrowRight className="h-4 w-4" aria-hidden="true" />
                  </Link>
                </div>
              </div>
            </div>
</div>
      </div>
      </div>

      {/* Floating Badge 1 - Top Left */}
      <div
        aria-hidden="true"
        className="absolute -left-8 top-16 hidden md:flex items-center gap-2 rounded-full border border-border/50 bg-background/80 px-4 py-2 text-xs font-medium text-muted-foreground shadow-sm backdrop-blur-md pointer-events-none animate-[bounce_4s_ease-in-out_infinite] motion-reduce:animate-none"
      >
        ✨ PyTorch
      </div>

      {/* Floating Badge 2 - Bottom Right */}
      <div
        aria-hidden="true"
        className="absolute -right-4 bottom-24 hidden md:flex items-center gap-2 rounded-full border border-border/50 bg-background/80 px-4 py-2 text-xs font-medium text-muted-foreground shadow-sm backdrop-blur-md pointer-events-none animate-[bounce_4s_ease-in-out_infinite] motion-reduce:animate-none"
        style={{ animationDelay: '1.5s' }}
      >
        Top 1% Match
      </div>

      <p className="mt-8 text-center text-xs text-muted-foreground">
        Minh họa giao diện đối sánh AI của nền tảng — Kéo để xoay 3D
      </p>
    </div>
  )
}