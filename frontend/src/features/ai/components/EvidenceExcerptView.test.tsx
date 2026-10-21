import { render, screen, fireEvent } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import {
  EvidenceExcerptView,
  evidenceSectionLabel,
} from './EvidenceExcerptView'
import type { EvidenceExcerpt } from '@/types/ai'

function makeExcerpt(
  overrides: Partial<EvidenceExcerpt> = {},
): EvidenceExcerpt {
  return {
    section: 'experiences',
    field_name: 'skills_used',
    item_index: 0,
    item_title: 'Senior Engineer',
    quote: 'Led platform team building microservices',
    ...overrides,
  }
}

describe('evidenceSectionLabel', () => {
  it('maps known sections to Vietnamese labels', () => {
    expect(evidenceSectionLabel('skills')).toBe('Kỹ năng')
    expect(evidenceSectionLabel('experiences')).toBe('Kinh nghiệm')
    expect(evidenceSectionLabel('projects')).toBe('Dự án')
    expect(evidenceSectionLabel('summary')).toBe('Giới thiệu')
    expect(evidenceSectionLabel('education')).toBe('Học vấn')
  })

  it('falls back to the raw value for unknown sections', () => {
    expect(evidenceSectionLabel('volunteering')).toBe('volunteering')
  })
})

describe('EvidenceExcerptView', () => {
  it('renders the section, item metadata and the verbatim quote', () => {
    render(<EvidenceExcerptView excerpt={makeExcerpt()} />)

    expect(screen.getByText('Kinh nghiệm')).toBeInTheDocument()
    expect(screen.getByText('Senior Engineer')).toBeInTheDocument()
    expect(screen.getByText('skills_used')).toBeInTheDocument()
    expect(
      screen.getByText('Led platform team building microservices'),
    ).toBeInTheDocument()
  })

  it('renders a quote containing HTML-like characters as literal text', () => {
    const quote = 'Used C++ templates: 5 < 10 && "constexpr" <script>alert(1)</script>'
    render(<EvidenceExcerptView excerpt={makeExcerpt({ quote })} />)

    const quoteNode = screen.getByText(quote)
    expect(quoteNode).toBeInTheDocument()
    const blockquote = quoteNode.closest('blockquote')
    expect(blockquote).not.toBeNull()
    // No markup from the quote string may be parsed into real elements.
    expect(blockquote?.querySelector('script')).toBeNull()
  })

  it('omits absent nullable metadata instead of fabricating values', () => {
    render(
      <EvidenceExcerptView
        excerpt={makeExcerpt({ item_title: null, field_name: null })}
      />,
    )

    expect(screen.queryByText('Senior Engineer')).not.toBeInTheDocument()
    expect(screen.queryByText('skills_used')).not.toBeInTheDocument()
    expect(
      screen.getByText('Led platform team building microservices'),
    ).toBeInTheDocument()
  })

  it('does not render a disclosure toggle for a short quote', () => {
    render(<EvidenceExcerptView excerpt={makeExcerpt()} />)
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it('provides an accessible disclosure for a long quote', () => {
    const quote = 'A'.repeat(300)
    render(<EvidenceExcerptView excerpt={makeExcerpt({ quote })} />)

    const button = screen.getByRole('button', {
      name: /Xem toàn bộ dẫn chứng/i,
    })
    expect(button).toHaveAttribute('aria-expanded', 'false')

    const controlledId = button.getAttribute('aria-controls')
    expect(controlledId).toBeTruthy()
    expect(document.getElementById(controlledId as string)).not.toBeNull()

    fireEvent.click(button)

    expect(
      screen.getByRole('button', { name: /Thu gọn dẫn chứng/i }),
    ).toHaveAttribute('aria-expanded', 'true')
  })
})
