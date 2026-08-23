import { useState } from 'react'
import { Trash2, Edit2, Plus, Clock, MapPin, Link as LinkIcon, Sparkles } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge as BadgeComponent } from '@/components/ui/badge'
import { scheduleInterview, updateInterview, cancelInterview } from '@/api/interviews'
import { getFriendlyErrorMessage } from '@/utils/errors'
import type { Interview } from '@/types/application'
import { Link } from 'react-router-dom'

// Terminal application statuses that should disable interview actions
const TERMINAL_STATUSES = ['accepted', 'rejected', 'withdrawn'] as const
type TerminalStatus = (typeof TERMINAL_STATUSES)[number]

function isTerminalStatus(status: string): status is TerminalStatus {
  return TERMINAL_STATUSES.includes(status as TerminalStatus)
}

export function InterviewManager({ 
  applicationId, 
  jobId,
  initialInterviews = [],
  onInterviewUpdated,
  applicationStatus = ''
}: { 
  applicationId: string
  jobId: string
  initialInterviews?: Interview[]
  onInterviewUpdated?: (interviews: Interview[]) => void
  applicationStatus?: string
}) {
  const [interviews, setInterviews] = useState<Interview[]>(initialInterviews)
  const [isEditing, setIsEditing] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  
  // Form State
  const [scheduledAt, setScheduledAt] = useState('')
  const [duration, setDuration] = useState(60)
  const [type, setType] = useState<'technical' | 'behavioral' | 'hr' | 'case_study'>('technical')
  const [meetingUrl, setMeetingUrl] = useState('')
  const [location, setLocation] = useState('')
  const [notes, setNotes] = useState('')

  const activeInterviews = interviews.filter(i => i.status === 'scheduled')

  const confirmedInterviews = interviews.filter(i => i.status === 'candidate_confirmed')
  const declinedInterviews = interviews.filter(i => i.status === 'candidate_declined')

  const resetForm = () => {
    setScheduledAt('')
    setDuration(60)
    setType('technical')
    setMeetingUrl('')
    setLocation('')
    setNotes('')
    setError(null)
  }

  const handleOpenNew = () => {
    resetForm()
    setEditingId(null)
    setIsEditing(true)
  }

  const handleOpenEdit = (i: Interview) => {
    const localDate = new Date(i.scheduled_at)
    // Format to datetime-local string (YYYY-MM-DDThh:mm)
    const formatted = new Date(localDate.getTime() - localDate.getTimezoneOffset() * 60000).toISOString().slice(0, 16)
    setScheduledAt(formatted)
    setDuration(i.duration_minutes)
    setType(i.interview_type)
    setMeetingUrl(i.meeting_url || '')
    setLocation(i.location || '')
    setNotes(i.notes || '')
    setEditingId(i.id)
    setIsEditing(true)
    setError(null)
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!scheduledAt) {
      setError('Vui lòng chọn thời gian')
      return
    }
    const utcDate = new Date(scheduledAt).toISOString()
    
    setSubmitting(true)
    setError(null)
    try {
      if (editingId) {
        const updated = await updateInterview(editingId, {
          scheduled_at: utcDate,
          duration_minutes: duration,
          interview_type: type,
          meeting_url: meetingUrl || null,
          location: location || null,
          notes: notes || null
        })
        const newInterviews = interviews.map(i => i.id === editingId ? updated : i)
        setInterviews(newInterviews)
        onInterviewUpdated?.(newInterviews)
      } else {
        const created = await scheduleInterview(applicationId, {
          scheduled_at: utcDate,
          duration_minutes: duration,
          interview_type: type,
          meeting_url: meetingUrl || null,
          location: location || null,
          notes: notes || null
        })
        const newInterviews = [...interviews, created]
        setInterviews(newInterviews)
        onInterviewUpdated?.(newInterviews)
      }
      setIsEditing(false)
    } catch (err) {
      setError(getFriendlyErrorMessage(err))
    } finally {
      setSubmitting(false)
    }
  }

  const handleCancel = async (id: string) => {
    if (!window.confirm('Bạn có chắc chắn muốn hủy lịch phỏng vấn này? Hành động này không thể hoàn tác.')) {
      return
    }
    try {
      await cancelInterview(id)
      const newInterviews = interviews.map(i => i.id === id ? { ...i, status: 'cancelled' as const } : i)
      setInterviews(newInterviews)
      onInterviewUpdated?.(newInterviews)
    } catch (err) {
      alert(getFriendlyErrorMessage(err))
    }
  }

  // Check if application is in terminal status
  const isTerminal = isTerminalStatus(applicationStatus)
  const terminalMessage = 'Không thể tạo lịch phỏng vấn hoặc tạo câu hỏi AI vì hồ sơ ứng viên đang ở trạng thái đã đóng.'

  return (
    <div className="space-y-4 rounded-xl border bg-card px-4 py-4">
      <div className="flex items-center justify-between">
        <p className="font-semibold text-foreground">Lịch phỏng vấn</p>
        <div className="flex items-center gap-2">
          {isTerminal ? (
            <BadgeComponent variant="destructive" className="mr-2">Đã đóng</BadgeComponent>
          ) : !isEditing && (
            <Button variant="outline" size="sm" onClick={handleOpenNew}>
              <Plus className="mr-1 h-4 w-4" /> Lên lịch
            </Button>
          )}
          {isTerminal ? (
            <Button variant="outline" size="sm" disabled>
              <Sparkles className="mr-1 h-4 w-4" /> Tạo câu hỏi AI
            </Button>
          ) : (
            <Link
              to={`/recruiter/jobs/${jobId}/interview?applicationId=${applicationId}`}
              className="flex items-center gap-1.5"
            >
              <Button variant="outline" size="sm">
                <Sparkles className="mr-1 h-4 w-4" /> Tạo câu hỏi AI
              </Button>
            </Link>
          )}
        </div>
      </div>

      {isTerminal && (
        <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {terminalMessage}
        </p>
      )}

      {error && (
        <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </p>
      )}

      {isEditing ? (
        <form onSubmit={handleSubmit} className="space-y-3 rounded-lg border bg-muted/20 p-3 text-sm">
          {isTerminal && (
            <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {terminalMessage}
            </p>
          )}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block font-medium">Thời gian</label>
              <input type="datetime-local" value={scheduledAt} onChange={e => setScheduledAt(e.target.value)} className="w-full rounded-md border bg-background px-3 py-1.5" required />
            </div>
            <div>
              <label className="mb-1 block font-medium">Thời lượng (phút)</label>
              <input type="number" min={15} value={duration} onChange={e => setDuration(parseInt(e.target.value))} className="w-full rounded-md border bg-background px-3 py-1.5" required />
            </div>
            <div>
              <label className="mb-1 block font-medium">Hình thức</label>
              <select value={type} onChange={e => setType(e.target.value as any)} className="w-full rounded-md border bg-background px-3 py-1.5">
                <option value="technical">Chuyên môn (Technical)</option>
                <option value="behavioral">Hành vi (Behavioral)</option>
                <option value="hr">Nhân sự (HR)</option>
                <option value="case_study">Bài tập (Case Study)</option>
              </select>
            </div>
            <div>
              <label className="mb-1 block font-medium">Link Meeting</label>
              <input type="url" value={meetingUrl} onChange={e => setMeetingUrl(e.target.value)} className="w-full rounded-md border bg-background px-3 py-1.5" placeholder="https://meet.google.com/..." />
            </div>
            <div className="col-span-2">
              <label className="mb-1 block font-medium">Địa điểm trực tiếp (nếu có)</label>
              <input type="text" value={location} onChange={e => setLocation(e.target.value)} className="w-full rounded-md border bg-background px-3 py-1.5" />
            </div>
            <div className="col-span-2">
              <label className="mb-1 block font-medium">Ghi chú</label>
              <textarea value={notes} onChange={e => setNotes(e.target.value)} className="w-full rounded-md border bg-background px-3 py-1.5" rows={2} />
            </div>
          </div>
          <div className="flex gap-2 pt-2">
            <Button type="submit" size="sm" isLoading={submitting}>Lưu</Button>
            <Button type="button" variant="ghost" size="sm" onClick={() => setIsEditing(false)} disabled={submitting}>Hủy</Button>
          </div>
        </form>
      ) : activeInterviews.length > 0 ? (
        <div className="space-y-3">
          {activeInterviews.map(i => (
            <div key={i.id} className="rounded-lg border border-primary/20 bg-primary/5 p-3 text-sm">
              <div className="flex justify-between items-start mb-2">
                <p className="font-semibold text-primary">Phỏng vấn {i.interview_type}</p>
                <div className="flex gap-1">
                  <Button type="button" variant="ghost" size="icon" className="h-6 w-6 text-muted-foreground" onClick={() => handleOpenEdit(i)}><Edit2 className="h-3 w-3" /></Button>
                  <Button type="button" variant="ghost" size="icon" className="h-6 w-6 text-destructive hover:text-destructive hover:bg-destructive/10" onClick={() => handleCancel(i.id)}><Trash2 className="h-3 w-3" /></Button>
                </div>
              </div>
              <div className="space-y-1 text-muted-foreground">
                <p className="flex items-center gap-2"><Clock className="h-3.5 w-3.5" /> {new Date(i.scheduled_at).toLocaleString('vi-VN')} ({i.duration_minutes} phút)</p>
                {i.meeting_url && <p className="flex items-center gap-2"><LinkIcon className="h-3.5 w-3.5" /> <a href={i.meeting_url} target="_blank" rel="noopener noreferrer" className="hover:underline">{i.meeting_url}</a></p>}
                {i.location && <p className="flex items-center gap-2"><MapPin className="h-3.5 w-3.5" /> {i.location}</p>}
                {i.notes && <p className="mt-2 text-xs italic bg-background p-2 rounded">{i.notes}</p>}
              </div>
            </div>
          ))}
        </div>
      ) : confirmedInterviews.length > 0 ? (
        <div className="space-y-3">
          {confirmedInterviews.map(i => (
            <div key={i.id} className="rounded-lg border border-success/20 bg-success/5 p-3 text-sm">
              <div className="flex justify-between items-start mb-2">
                <p className="font-semibold text-success">Phỏng vấn {i.interview_type}</p>
                <BadgeComponent variant="success" className="mr-1">Đã xác nhận</BadgeComponent>
              </div>
              <div className="space-y-1 text-muted-foreground">
                <p className="flex items-center gap-2"><Clock className="h-3.5 w-3.5" /> {new Date(i.scheduled_at).toLocaleString('vi-VN')} ({i.duration_minutes} phút)</p>
                {i.meeting_url && <p className="flex items-center gap-2"><LinkIcon className="h-3.5 w-3.5" /> <a href={i.meeting_url} target="_blank" rel="noopener noreferrer" className="hover:underline">{i.meeting_url}</a></p>}
                {i.location && <p className="flex items-center gap-2"><MapPin className="h-3.5 w-3.5" /> {i.location}</p>}
                {i.candidate_notes && <p className="mt-2 text-xs italic bg-success/5 border border-success/20 p-2 rounded text-success">Phản hồi: {i.candidate_notes}</p>}
              </div>
            </div>
          ))}
        </div>
      ) : declinedInterviews.length > 0 ? (
        <div className="space-y-3">
          {declinedInterviews.map(i => (
            <div key={i.id} className="rounded-lg border border-destructive/20 bg-destructive/5 p-3 text-sm">
              <div className="flex justify-between items-start mb-2">
                <p className="font-semibold text-destructive">Phỏng vấn {i.interview_type}</p>
                <BadgeComponent variant="destructive">Đã từ chối</BadgeComponent>
              </div>
              <div className="space-y-1 text-muted-foreground">
                <p className="flex items-center gap-2"><Clock className="h-3.5 w-3.5" /> {new Date(i.scheduled_at).toLocaleString('vi-VN')} ({i.duration_minutes} phút)</p>
                {i.meeting_url && <p className="flex items-center gap-2"><LinkIcon className="h-3.5 w-3.5" /> <a href={i.meeting_url} target="_blank" rel="noopener noreferrer" className="hover:underline">{i.meeting_url}</a></p>}
                {i.location && <p className="flex items-center gap-2"><MapPin className="h-3.5 w-3.5" /> {i.location}</p>}
                {i.candidate_notes && <p className="mt-2 text-xs italic bg-destructive/5 border border-destructive/20 p-2 rounded text-destructive">Lý do: {i.candidate_notes}</p>}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <p className="text-sm text-muted-foreground italic">Chưa có lịch phỏng vấn nào.</p>
      )}
    </div>
  )
}
