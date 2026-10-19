import { useCallback, useEffect, useState } from 'react'
import { FileText, Lock, Pencil, RefreshCw, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Spinner } from '@/components/ui/spinner'
import { Textarea } from '@/components/ui/textarea'
import { EmptyState } from '@/components/ui/empty-state'
import { useAuth } from '@/contexts/AuthContext'
import {
  createApplicationNote,
  deleteApplicationNote,
  listApplicationNotes,
  updateApplicationNote,
} from '@/api/applications'
import { getErrorStatus, getFriendlyErrorMessage } from '@/utils/errors'
import { formatDateTime } from '@/utils/datetime'
import type { ApplicationNote } from '@/types/application'

const NOTE_MAX_LENGTH = 2000
const PAGE_SIZE = 50

type NotesState =
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'success'; notes: ApplicationNote[] }

export interface ApplicationNoteListProps {
  applicationId: string
}

export function ApplicationNoteList({ applicationId }: ApplicationNoteListProps) {
  const { currentUser } = useAuth()
  const [state, setState] = useState<NotesState>({ kind: 'loading' })
  const [content, setContent] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editingContent, setEditingContent] = useState('')
  const [busyId, setBusyId] = useState<string | null>(null)

  const load = useCallback(() => {
    let active = true
    setState({ kind: 'loading' })
    listApplicationNotes(applicationId, { limit: PAGE_SIZE })
      .then((notes) => {
        if (active) setState({ kind: 'success', notes })
      })
      .catch((err) => {
        if (active) {
          setState({
            kind: 'error',
            message:
              getErrorStatus(err) === 403
                ? 'Bạn không có quyền xem ghi chú nội bộ của đơn ứng tuyển này.'
                : getFriendlyErrorMessage(err),
          })
        }
      })
    return () => {
      active = false
    }
  }, [applicationId])

  useEffect(() => {
    return load()
  }, [load])

  const canManage = (note: ApplicationNote): boolean =>
    currentUser?.role === 'admin' || note.author_id === currentUser?.id

  const authorLabel = (note: ApplicationNote): string =>
    note.author_id === currentUser?.id ? 'Bạn' : 'Đồng nghiệp'

  const handleCreate = async (event: React.FormEvent) => {
    event.preventDefault()
    const trimmed = content.trim()
    if (!trimmed) {
      setFormError('Vui lòng nhập nội dung ghi chú.')
      return
    }
    if (trimmed.length > NOTE_MAX_LENGTH) {
      setFormError(`Ghi chú không được vượt quá ${NOTE_MAX_LENGTH} ký tự.`)
      return
    }

    setSubmitting(true)
    setFormError(null)
    try {
      const created = await createApplicationNote(applicationId, trimmed)
      setContent('')
      setState((prev) =>
        prev.kind === 'success'
          ? { kind: 'success', notes: [created, ...prev.notes] }
          : { kind: 'success', notes: [created] },
      )
    } catch (err) {
      setFormError(
        getErrorStatus(err) === 403
          ? 'Bạn không có quyền thêm ghi chú cho đơn ứng tuyển này.'
          : getFriendlyErrorMessage(err),
      )
    } finally {
      setSubmitting(false)
    }
  }

  const startEditing = (note: ApplicationNote) => {
    setEditingId(note.id)
    setEditingContent(note.content)
  }

  const handleUpdate = async (note: ApplicationNote) => {
    const trimmed = editingContent.trim()
    if (!trimmed) return
    setBusyId(note.id)
    try {
      const updated = await updateApplicationNote(
        applicationId,
        note.id,
        trimmed,
      )
      setState((prev) =>
        prev.kind === 'success'
          ? {
              kind: 'success',
              notes: prev.notes.map((item) =>
                item.id === updated.id ? updated : item,
              ),
            }
          : prev,
      )
      setEditingId(null)
      setEditingContent('')
    } catch (err) {
      setFormError(
        getErrorStatus(err) === 403
          ? 'Chỉ người tạo ghi chú hoặc quản trị viên mới có thể sửa ghi chú này.'
          : getFriendlyErrorMessage(err),
      )
    } finally {
      setBusyId(null)
    }
  }

  const handleDelete = async (note: ApplicationNote) => {
    if (!window.confirm('Bạn có chắc chắn muốn xóa ghi chú này?')) return
    setBusyId(note.id)
    try {
      await deleteApplicationNote(applicationId, note.id)
      setState((prev) =>
        prev.kind === 'success'
          ? {
              kind: 'success',
              notes: prev.notes.filter((item) => item.id !== note.id),
            }
          : prev,
      )
    } catch (err) {
      setFormError(
        getErrorStatus(err) === 403
          ? 'Chỉ người tạo ghi chú hoặc quản trị viên mới có thể xóa ghi chú này.'
          : getFriendlyErrorMessage(err),
      )
    } finally {
      setBusyId(null)
    }
  }

  return (
    <div className="space-y-4">
      <p className="flex items-center gap-2 rounded-lg bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
        <Lock className="h-3.5 w-3.5" aria-hidden="true" />
        Ghi chú nội bộ chỉ hiển thị cho nhà tuyển dụng và quản trị viên, ứng viên
        không nhìn thấy.
      </p>

      <form onSubmit={handleCreate} className="space-y-2">
        <Textarea
          id="new-note"
          name="content"
          label="Thêm ghi chú nội bộ"
          value={content}
          maxLength={NOTE_MAX_LENGTH}
          onChange={(e) => setContent(e.target.value)}
          placeholder="Ghi lại nhận xét, thông tin trao đổi hoặc bước tiếp theo..."
          helperText={`${content.length}/${NOTE_MAX_LENGTH} ký tự`}
        />
        {formError ? (
          <p role="alert" className="text-sm font-medium text-destructive">
            {formError}
          </p>
        ) : null}
        <div className="flex justify-end">
          <Button
            type="submit"
            size="sm"
            isLoading={submitting}
            disabled={!content.trim()}
          >
            Thêm ghi chú
          </Button>
        </div>
      </form>

      {state.kind === 'loading' ? (
        <div className="flex items-center justify-center gap-3 py-8 text-muted-foreground">
          <Spinner size="md" />
          <span>Đang tải ghi chú...</span>
        </div>
      ) : state.kind === 'error' ? (
        <div className="space-y-4 py-4 text-center">
          <p role="alert" className="text-sm font-medium text-destructive">
            {state.message}
          </p>
          <Button variant="outline" size="sm" onClick={load}>
            <RefreshCw className="h-4 w-4" aria-hidden="true" />
            Thử lại
          </Button>
        </div>
      ) : state.notes.length === 0 ? (
        <EmptyState
          icon={<FileText className="h-6 w-6" aria-hidden="true" />}
          title="Chưa có ghi chú nội bộ"
          description="Chưa có ghi chú nào cho đơn ứng tuyển này."
        />
      ) : (
        <ul className="space-y-3">
          {state.notes.map((note) => (
            <li
              key={note.id}
              className="rounded-xl border bg-muted/20 px-4 py-3"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-center gap-2">
                  <Badge variant="neutral">{authorLabel(note)}</Badge>
                  <span className="text-xs text-muted-foreground">
                    {formatDateTime(note.created_at)}
                    {note.updated_at !== note.created_at ? ' · đã chỉnh sửa' : ''}
                  </span>
                </div>
                {canManage(note) && editingId !== note.id ? (
                  <div className="flex items-center gap-1">
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      className="h-7 w-7"
                      aria-label="Sửa ghi chú"
                      onClick={() => startEditing(note)}
                      disabled={busyId === note.id}
                    >
                      <Pencil className="h-3.5 w-3.5" aria-hidden="true" />
                    </Button>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      className="h-7 w-7 text-destructive hover:text-destructive"
                      aria-label="Xóa ghi chú"
                      onClick={() => handleDelete(note)}
                      disabled={busyId === note.id}
                    >
                      <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                    </Button>
                  </div>
                ) : null}
              </div>

              {editingId === note.id ? (
                <div className="mt-2 space-y-2">
                  <Textarea
                    id={`edit-note-${note.id}`}
                    name={`edit-note-${note.id}`}
                    label="Chỉnh sửa ghi chú"
                    value={editingContent}
                    maxLength={NOTE_MAX_LENGTH}
                    onChange={(e) => setEditingContent(e.target.value)}
                  />
                  <div className="flex gap-2">
                    <Button
                      type="button"
                      size="sm"
                      isLoading={busyId === note.id}
                      disabled={!editingContent.trim()}
                      onClick={() => handleUpdate(note)}
                    >
                      Lưu
                    </Button>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={() => {
                        setEditingId(null)
                        setEditingContent('')
                      }}
                      disabled={busyId === note.id}
                    >
                      Hủy
                    </Button>
                  </div>
                </div>
              ) : (
                <p className="mt-2 whitespace-pre-wrap text-sm text-foreground">
                  {note.content}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
