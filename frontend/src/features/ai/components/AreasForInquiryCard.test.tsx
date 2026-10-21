import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { AreasForInquiryCard } from './AreasForInquiryCard'

describe('AreasForInquiryCard', () => {
  it('renders the heading and each interview prompt verbatim', () => {
    render(
      <AreasForInquiryCard
        areas={[
          'Hỏi thêm về kinh nghiệm tối ưu truy vấn SQL nâng cao',
          'Làm rõ vai trò trong dự án microservices',
        ]}
      />,
    )

    expect(screen.getByText('Gợi ý câu hỏi phỏng vấn')).toBeInTheDocument()
    expect(
      screen.getByText('Hỏi thêm về kinh nghiệm tối ưu truy vấn SQL nâng cao'),
    ).toBeInTheDocument()
    expect(
      screen.getByText('Làm rõ vai trò trong dự án microservices'),
    ).toBeInTheDocument()
  })

  it('renders a long list without dropping entries', () => {
    const areas = Array.from({ length: 15 }, (_, index) => `Câu hỏi ${index}`)
    render(<AreasForInquiryCard areas={areas} />)

    expect(screen.getAllByRole('listitem')).toHaveLength(15)
    expect(screen.getByText('Câu hỏi 14')).toBeInTheDocument()
  })

  it('renders long prompt text without truncation', () => {
    const longPrompt =
      'Hãy giải thích chi tiết cách bạn xử lý xung đột đồng thời khi nhiều worker cùng ghi vào một bản ghi duy nhất trong hệ thống phân tán quy mô lớn.'
    render(<AreasForInquiryCard areas={[longPrompt]} />)

    expect(screen.getByText(longPrompt)).toBeInTheDocument()
  })

  it('shows an empty state when there are no prompts', () => {
    render(<AreasForInquiryCard areas={[]} />)
    expect(
      screen.getByText('Chưa có gợi ý câu hỏi cho ứng viên này.'),
    ).toBeInTheDocument()
    expect(screen.queryByRole('listitem')).not.toBeInTheDocument()
  })
})
