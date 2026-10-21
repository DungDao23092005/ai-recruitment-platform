import { describe, expect, it } from 'vitest'

import { getFriendlyErrorMessage } from './errors'

function responseError(status: number, data?: unknown) {
  return { response: { status, data } }
}

const GENERIC_SERVER_ERROR_MESSAGE =
  'Hệ thống đang gặp sự cố khi xử lý yêu cầu. Vui lòng thử lại sau.'

describe('getFriendlyErrorMessage', () => {
  it('falls back to the connection message when there is no response', () => {
    expect(getFriendlyErrorMessage(new Error('Network Error'))).toBe(
      'Không thể kết nối tới máy chủ. Vui lòng kiểm tra kết nối và thử lại.',
    )
  })

  it('localizes the generic FastAPI 5xx detail', () => {
    expect(
      getFriendlyErrorMessage(
        responseError(500, { detail: 'Internal Server Error' }),
      ),
    ).toBe(GENERIC_SERVER_ERROR_MESSAGE)
  })

  it('localizes 5xx responses without a detail body', () => {
    expect(getFriendlyErrorMessage(responseError(500))).toBe(
      GENERIC_SERVER_ERROR_MESSAGE,
    )
    expect(getFriendlyErrorMessage(responseError(503, {}))).toBe(
      GENERIC_SERVER_ERROR_MESSAGE,
    )
  })

  it('keeps a meaningful specific 5xx detail message', () => {
    expect(
      getFriendlyErrorMessage(
        responseError(500, { detail: 'Cơ sở dữ liệu tạm thời không khả dụng.' }),
      ),
    ).toBe('Cơ sở dữ liệu tạm thời không khả dụng.')
  })

  it('keeps conflict and authorization details intact', () => {
    expect(
      getFriendlyErrorMessage(
        responseError(409, { detail: 'Đơn ứng tuyển đã thay đổi.' }),
      ),
    ).toBe('Đơn ứng tuyển đã thay đổi.')
    expect(
      getFriendlyErrorMessage(
        responseError(403, { detail: 'Bạn không có quyền thực hiện.' }),
      ),
    ).toBe('Bạn không có quyền thực hiện.')
  })

  it('keeps validation details and falls back for empty 422 failures', () => {
    expect(
      getFriendlyErrorMessage(
        responseError(422, { detail: [{ msg: 'Trạng thái không hợp lệ.' }] }),
      ),
    ).toBe('Trạng thái không hợp lệ.')
    expect(getFriendlyErrorMessage(responseError(422))).toBe(
      'Vui lòng kiểm tra lại các trường trong biểu mẫu.',
    )
  })

  it('keeps the authentication message and generic 400 fallback', () => {
    expect(getFriendlyErrorMessage(responseError(401))).toBe(
      'Email hoặc mật khẩu không chính xác.',
    )
    expect(getFriendlyErrorMessage(responseError(400))).toBe(
      'Yêu cầu không thể hoàn tất. Vui lòng thử lại.',
    )
  })
})
