import { useEffect, useRef, useState } from 'react'

interface UseInViewOptions {
  triggerOnce?: boolean
  rootMargin?: string
  threshold?: number | number[]
}

export function useInView<T extends HTMLElement = HTMLElement>(options: UseInViewOptions = {}) {
  const { triggerOnce = true, rootMargin = '0px', threshold = 0 } = options
  const ref = useRef<T>(null)
  const [isInView, setIsInView] = useState(false)

  useEffect(() => {
    const element = ref.current
    if (!element) return

    if (typeof window === 'undefined' || !window.IntersectionObserver) {
      setIsInView(true)
      return
    }

    const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    if (prefersReducedMotion) {
      setIsInView(true)
      return
    }

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setIsInView(true)
          if (triggerOnce) {
            observer.unobserve(element)
          }
        } else if (!triggerOnce) {
          setIsInView(false)
        }
      },
      { rootMargin, threshold }
    )

    observer.observe(element)

    return () => {
      observer.disconnect()
    }
  }, [triggerOnce, rootMargin, threshold])

  return { ref, isInView }
}