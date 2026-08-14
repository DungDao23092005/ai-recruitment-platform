import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { Button } from './button'

describe('Button', () => {
  it('renders a button with children', () => {
    render(<Button>Submit</Button>)
    expect(
      screen.getByRole('button', { name: 'Submit' }),
    ).toBeInTheDocument()
  })

  it('renders button variants', () => {
    const { container } = render(
      <>
        <Button variant="default">Default</Button>
        <Button variant="secondary">Secondary</Button>
        <Button variant="outline">Outline</Button>
        <Button variant="ghost">Ghost</Button>
        <Button variant="destructive">Destructive</Button>
      </>,
    )

    const buttons = container.querySelectorAll('button')
    expect(buttons).toHaveLength(5)

    const classes = Array.from(buttons).map((b) => b.className)
    expect(classes[0]).toContain('bg-primary')
    expect(classes[1]).toContain('bg-secondary')
    expect(classes[2]).toContain('border-input')
    expect(classes[3]).not.toContain('bg-primary')
    expect(classes[3]).not.toContain('bg-secondary')
    expect(classes[4]).toContain('bg-destructive')
  })

  it('calls onClick when clicked', () => {
    const handleClick = vi.fn()

    render(<Button onClick={handleClick}>Click me</Button>)

    fireEvent.click(screen.getByRole('button', { name: 'Click me' }))
    expect(handleClick).toHaveBeenCalledTimes(1)
  })

  it('renders loading state and disables interaction', () => {
    const handleClick = vi.fn()

    render(
      <Button isLoading loadingText="Saving...">
        Save
      </Button>,
    )

    const button = screen.getByRole('button', {
      name: 'Saving...',
    })
    expect(button).toBeDisabled()
    expect(button).toHaveAttribute('aria-busy', 'true')

    fireEvent.click(button)
    expect(handleClick).not.toHaveBeenCalled()
  })

  it('is disabled when disabled prop is set', () => {
    render(<Button disabled>Disabled</Button>)
    expect(screen.getByRole('button', { name: 'Disabled' })).toBeDisabled()
  })
})