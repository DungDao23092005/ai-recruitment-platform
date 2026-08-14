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
    return 'Unable to connect to server. Please check your connection and try again.'
  }

  const status = error.response?.status
  const data = error.response?.data as ApiErrorDetail | undefined

  if (status === 401) {
    return 'Incorrect email or password.'
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
    return 'The request could not be completed. Please try again.'
  }

  if (status === 422) {
    return 'Please check the form fields and try again.'
  }

  return 'Something went wrong. Please try again.'
}