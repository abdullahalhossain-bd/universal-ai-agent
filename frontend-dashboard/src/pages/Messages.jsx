import { useEffect, useState } from 'react'
import { MessageSquare, Send, RefreshCw, Clock, UserRound } from 'lucide-react'
import { api, ApiError } from '../api/client'
import { Alert, Button, Card, EmptyState, Input, PageHeader, Spinner } from '../components/ui'

const formatTime = (value) => value ? new Date(value).toLocaleString(undefined, {
  year: 'numeric', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', second: '2-digit'
}) : ''

const roleLabel = (role) => {
  if (role === 'user') return 'Customer'
  if (role === 'merchant') return 'You'
  return 'AI Assistant'
}

export default function Messages() {
  const [conversations, setConversations] = useState([])
  const [selected, setSelected] = useState(null)
  const [reply, setReply] = useState('')
  const [loading, setLoading] = useState(true)
  const [sending, setSending] = useState(false)
  const [error, setError] = useState('')

  const load = async (conversationId = selected?.conversation_id) => {
    setLoading(true)
    setError('')
    try {
      const list = await api.get('/v1/messages/conversations')
      setConversations(Array.isArray(list) ? list : [])
      if (conversationId) {
        const item = await api.get(`/v1/messages/conversations/${encodeURIComponent(conversationId)}`)
        setSelected(item)
      } else if (!selected && list?.length) {
        setSelected(await api.get(`/v1/messages/conversations/${encodeURIComponent(list[0].conversation_id)}`))
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Could not load messages.')
    } finally { setLoading(false) }
  }

  useEffect(() => { load() }, [])
  useEffect(() => {
    const timer = setInterval(() => load(selected?.conversation_id), 5000)
    return () => clearInterval(timer)
  }, [selected?.conversation_id])

  const openConversation = async (id) => {
    setError('')
    try { setSelected(await api.get(`/v1/messages/conversations/${encodeURIComponent(id)}`)) }
    catch (err) { setError(err instanceof ApiError ? err.detail : 'Could not open conversation.') }
  }

  const sendReply = async () => {
    const text = reply.trim()
    if (!text || !selected) return
    setSending(true); setError('')
    try {
      await api.post(`/v1/messages/conversations/${encodeURIComponent(selected.conversation_id)}/reply`, { message: text })
      setReply('')
      await load(selected.conversation_id)
    } catch (err) { setError(err instanceof ApiError ? err.detail : 'Reply failed.') }
    finally { setSending(false) }
  }

  return <div>
    <PageHeader title="Inbox" description="See every customer message, who sent it, and exactly when it was sent. Reply to one customer conversation at a time." />
    {error && <div className="mb-5"><Alert tone="warn">{error}</Alert></div>}
    <div className="grid gap-5 lg:grid-cols-[360px_1fr] min-h-[680px]">
      <Card className="p-0 overflow-hidden">
        <div className="flex items-center justify-between border-b border-line px-4 py-3">
          <div className="flex items-center gap-2 text-sm font-semibold"><MessageSquare size={16}/> Customer inbox</div>
          <button className="text-muted hover:text-text" onClick={() => load()} title="Refresh"><RefreshCw size={15}/></button>
        </div>
        <div className="border-b border-line px-4 py-2 text-xs text-muted">
          {conversations.length} conversation{conversations.length === 1 ? '' : 's'}
        </div>
        <div className="divide-y divide-line max-h-[620px] overflow-y-auto">
          {loading && !conversations.length ? <div className="p-6"><Spinner /></div> : conversations.map(item => (
            <button key={item.conversation_id} onClick={() => openConversation(item.conversation_id)} className={`w-full text-left px-4 py-3 hover:bg-paper ${selected?.conversation_id === item.conversation_id ? 'bg-paper' : ''}`}>
              <div className="flex items-center justify-between gap-2">
                <span className="flex items-center gap-2 text-sm font-medium"><UserRound size={14}/> Customer</span>
                <span className="text-[11px] text-muted">{formatTime(item.last_message?.created_at)}</span>
              </div>
              <div className="mt-1 flex items-center gap-1 text-[10px] text-muted"><Clock size={11}/> {item.last_message ? roleLabel(item.last_message.role) : 'No messages'}</div>
              <p className="mt-1 truncate text-xs text-muted">{item.last_message?.content || 'No messages yet'}</p>
              <p className="mt-1 truncate text-[10px] text-muted/70">ID: {item.conversation_id}</p>
            </button>
          ))}
          {!loading && !conversations.length && <EmptyState title="No conversations yet" description="Customer messages will appear here when visitors use your assistant." />}
        </div>
      </Card>

      <Card className="flex min-h-[680px] flex-col">
        {!selected ? <EmptyState title="Select a conversation" description="Choose a customer conversation from the left." /> : <>
          <div className="border-b border-line pb-4">
            <div className="flex items-center gap-2 font-semibold text-text"><UserRound size={17}/> Customer conversation</div>
            <div className="mt-1 text-xs text-muted">Conversation ID: {selected.conversation_id}</div>
            <div className="mt-1 text-xs text-muted">Visitor ID: {selected.visitor_id || 'anonymous'}</div>
            <div className="mt-1 text-xs text-muted">Started: {formatTime(selected.created_at)}</div>
          </div>
          <div className="flex-1 space-y-4 overflow-y-auto py-5 pr-1">
            {(selected.messages || []).map(message => <div key={message.id} className={`flex ${message.role === 'user' ? 'justify-start' : 'justify-end'}`}>
              <div className={`max-w-[80%] rounded-xl px-3 py-2 text-sm ${message.role === 'user' ? 'bg-paper border border-line' : message.role === 'merchant' ? 'bg-accent text-white' : 'bg-ink text-white'}`}>
                <div className="mb-1 flex items-center justify-between gap-5 text-[10px] uppercase opacity-70">
                  <span>{roleLabel(message.role)}</span>
                  <span className="normal-case">{formatTime(message.created_at)}</span>
                </div>
                <div className="whitespace-pre-wrap break-words">{message.content}</div>
                <div className="mt-1 text-[9px] opacity-50">Message ID: {message.id}</div>
              </div>
            </div>)}
            {!selected.messages?.length && <EmptyState title="No messages" description="This conversation does not have any messages yet." />}
          </div>
          <div className="border-t border-line pt-4 flex gap-2">
            <Input id="merchant-reply" value={reply} onChange={e => setReply(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendReply() } }} placeholder="Write a reply to this customer…" className="flex-1" />
            <Button onClick={sendReply} disabled={sending || !reply.trim()}>{sending ? <Spinner /> : <Send size={16}/>} Reply</Button>
          </div>
        </>}
      </Card>
    </div>
  </div>
}
