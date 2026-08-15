interface HttpResponseError {
  response?: {
    status?: number
    data?: unknown
  }
}

interface ApiErrorDetail {
  detail?: string | Array<{ msg?: string; loc?: unknown[] }>
}

function isResponseError(error: unknown): error is HttpResponseError {
  return (
    typeof error === 'object' &&
    error !== null &&
    'response' in error &&
    typeof (error as HttpResponseError).response === 'object'
  )
}

export function getFriendlyErrorMessage(error: unknown): string {
  if (!isResponseError(error)) {
    return 'Không thể kết nối tới máy chủ. Vui lòng kiểm tra kết nối và thử lại.'
  }

  const status = error.response?.status
  const data = error.response?.data as ApiErrorDetail | undefined

  if (status === 401) {
    return 'Email hoặc mật khẩu không chính xác.'
  }

  if (data?.detail) {
    if (typeof data.detail === 'string') {
      return data.detail
    }
    if (Array.isArray(data.detail)) {
      const msg = data.detail[0]?.msg
      if (msg) {
        return msg
      }
    }
  }

  if (status === 400) {
    return 'Yêu cầu không thể hoàn tất. Vui lòng thử lại.'
  }

  if (status === 422) {
    return 'Vui lòng kiểm tra lại các trường trong biểu mẫu.'
  }

  return 'Đã xảy ra lỗi. Vui lòng thử lại.'
}