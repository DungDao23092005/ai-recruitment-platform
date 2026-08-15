import { render, screen, fireEvent } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { SystemHealthCard } from './SystemHealthCard'
import type { HealthStatus } from '@/api/endpoints'

const mockHealth: HealthStatus = {
  status: 'healthy',
  service: 'AI Recruitment Platform API',
  version: '1.0.0',
  environment: 'development',
}

describe('SystemHealthCard', () => {
  it('shows loading state', () => {
    render(
      <SystemHealthCard
        status="loading"
        health={null}
        error={null}
        onRefresh={vi.fn()}
      />,
    )
    expect(
      screen.getByText('Đang kiểm tra backend...'),
    ).toBeInTheDocument()
  })

  it('shows healthy details', () => {
    render(
      <SystemHealthCard
        status="healthy"
        health={mockHealth}
        error={null}
        onRefresh={vi.fn()}
      />,
    )
    expect(screen.getByText('Hoạt động tốt')).toBeInTheDocument()
    expect(
      screen.getByText('AI Recruitment Platform API'),
    ).toBeInTheDocument()
    expect(screen.getByText('1.0.0')).toBeInTheDocument()
    expect(screen.getByText('development')).toBeInTheDocument()
  })

  it('shows an unhealthy state with an error', () => {
    render(
      <SystemHealthCard
        status="unhealthy"
        health={null}
        error="Cannot connect"
        onRefresh={vi.fn()}
      />,
    )
    expect(screen.getByText('Không kết nối được')).toBeInTheDocument()
    expect(screen.getByText('Cannot connect')).toBeInTheDocument()
  })

  it('triggers refresh on button click', () => {
    const onRefresh = vi.fn()
    render(
      <SystemHealthCard
        status="unhealthy"
        health={null}
        error="Cannot connect"
        onRefresh={onRefresh}
      />,
    )
    fireEvent.click(
      screen.getByRole('button', { name: 'Làm mới trạng thái hệ thống' }),
    )
    expect(onRefresh).toHaveBeenCalledTimes(1)
  })
})