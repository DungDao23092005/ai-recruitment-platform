import * as React from 'react'
import { cn } from '@/utils/cn'

interface AnimatedSectionProps {
  children: React.ReactNode
  className?: string
  delay?: number
  triggerOnce?: boolean
  rootMargin?: string
}

export function AnimatedSection({
  children,
  className,
  delay = 0,
  triggerOnce = true,
  rootMargin = '0px',
}: AnimatedSectionProps) {
  const [isVisible, setIsVisible] = React.useState(false)
  const sectionRef = React.useRef<HTMLDivElement>(null)

  React.useEffect(() => {
    const element = sectionRef.current
    if (!element) return

    if (typeof window === 'undefined' || !window.IntersectionObserver) {
      setIsVisible(true)
      return
    }

    const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    if (prefersReducedMotion) {
      setIsVisible(true)
      return
    }

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setIsVisible(true)
          if (triggerOnce) {
            observer.unobserve(element)
          }
        }
      },
      { rootMargin, threshold: 0.1 }
    )

    observer.observe(element)

    return () => {
      observer.disconnect()
    }
  }, [triggerOnce, rootMargin])

  const baseStyles = `
    transition-all duration-600 ease-out
    ${isVisible ? 'opacity-100 translate-y-0 scale-100 blur-0' : 'opacity-0 translate-y-10 scale-96 blur-sm'}
  `

  return (
    <div
      ref={sectionRef}
      className={cn(baseStyles, className)}
      style={{ transitionDelay: `${delay}ms` }}
    >
      {children}
    </div>
  )
}