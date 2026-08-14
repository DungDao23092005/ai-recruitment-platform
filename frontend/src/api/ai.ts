import apiClient from '@/api/client'
import type { ParsedResume } from '@/types/ai'

export async function parseResume(file: File): Promise<ParsedResume> {
  const formData = new FormData()
  formData.append('file', file)

  return apiClient.post<ParsedResume, ParsedResume>(
    '/ai/parse-resume',
    formData,
    {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    },
  )
}