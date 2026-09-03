import { useEffect, useState } from 'react'
import { MessageSquareText, Send, UploadCloud, Sparkles } from 'lucide-react'
import { api, ApiError } from '../api/client'
import { Alert, Button, Card, EmptyState, Input, PageHeader, Spinner } from '../components/ui'

export default function ChatPreview() {
  const [message, setMessage] = useState('')
  const [conversation, setConversation] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [imageId, setImageId] = useState('')
  const [imageQuestion, setImageQuestion] = useState('What is this product?')
  const [uploading, setUploading] = useState(false)

  useEffect(() => {
    setConversation([
      {
        role: 'assistant',
        content: 'Ask about product details, shipping, policies, or items in your catalog. The answer is generated using the connected store data and any configured knowledge sources.',
      },
    ])
  }, [])

  const sendChat = async () => {
    const next = message.trim()
    if (!next) return
    setLoading(true)
    setError('')
    setConversation((prev) => [...prev, { role: 'user', content: next }, { role: 'assistant', content: 'Thinking…' }])

    try {
      const result = await api.post('/v1/chat', { message: next })
      setConversation((prev) => {
        const items = [...prev]
        items[items.length - 1] = { role: 'assistant', content: result?.message || 'No response returned.' }
        return items
      })
      setMessage('')
    } catch (err) {
      setConversation((prev) => {
        const items = [...prev]
        items[items.length - 1] = { role: 'assistant', content: 'Request failed. Please check the backend or try again.' }
        return items
      })
      setError(err instanceof ApiError ? err.detail : 'Chat request failed.')
    } finally {
      setLoading(false)
    }
  }

  const uploadImage = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    setError('')
    try {
      const formData = new FormData()
      formData.append('file', file)
      const result = await fetch('/v1/images', {
        method: 'POST',
        headers: { Authorization: `Bearer ${localStorage.getItem('merchant_console_token') || ''}` },
        body: formData,
      })
      const data = await result.json().catch(() => ({}))
      if (!result.ok) throw new ApiError(result.status, data.detail || 'Image upload failed')
      setImageId(data.image_id)
      setError('Image uploaded successfully. Ask a question about it below.')
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Image upload failed.')
    } finally {
      setUploading(false)
    }
  }

  const askImageQuestion = async () => {
    if (!imageId) {
      setError('Upload an image first.')
      return
    }
    setLoading(true)
    setError('')
    try {
      const result = await fetch(`/v1/images/${imageId}/analyze`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${localStorage.getItem('merchant_console_token') || ''}`,
        },
        body: JSON.stringify({ question: imageQuestion, conversation_id: 'merchant-preview' }),
      })
      const data = await result.json().catch(() => ({}))
      if (!result.ok) throw new ApiError(result.status, data.detail || 'Image analysis failed')
      setConversation((prev) => [...prev, { role: 'user', content: `Image: ${imageQuestion}` }, { role: 'assistant', content: data.message || 'No visual summary returned.' }])
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Image analysis failed.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div>
      <PageHeader
        title="AI chat preview"
        description="Test the same retrieval and response pipeline used by your storefront assistant."
      />

      {error && (
        <div className="mb-5">
          <Alert tone={error.includes('successfully') ? 'success' : 'warn'}>{error}</Alert>
        </div>
      )}

      <div className="grid gap-5 lg:grid-cols-[1.3fr_0.7fr]">
        <Card>
          <div className="mb-4 flex items-center gap-2 text-sm font-medium text-text">
            <MessageSquareText size={16} /> Live chat test
          </div>

          <div className="space-y-3 rounded-xl border border-line bg-paper p-3">
            {conversation.map((item, index) => (
              <div key={`${item.role}-${index}`} className={`rounded-lg px-3 py-2 text-sm ${item.role === 'user' ? 'ml-8 bg-accent text-white' : 'mr-8 bg-white text-text border border-line'}`}>
                {item.content}
              </div>
            ))}
          </div>

          <div className="mt-4 flex gap-2">
            <Input
              id="chat-message"
              className="flex-1"
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              placeholder="Ask about shipping, products, or policy questions"
            />
            <Button onClick={sendChat} disabled={loading || !message.trim()}>
              {loading ? <Spinner /> : <Send size={16} />}
              Send
            </Button>
          </div>
        </Card>

        <Card>
          <div className="mb-4 flex items-center gap-2 text-sm font-medium text-text">
            <Sparkles size={16} /> Image-enabled chat
          </div>

          <label className="block">
            <span className="mb-2 block text-sm font-medium text-text">Upload image</span>
            <div className="flex cursor-pointer items-center justify-center rounded-xl border border-dashed border-line bg-paper px-4 py-8 text-center text-sm text-muted">
              <UploadCloud size={18} className="mr-2" />
              <span>{uploading ? 'Uploading…' : 'Choose image'}</span>
              <input type="file" accept="image/*" className="hidden" onChange={uploadImage} />
            </div>
          </label>

          {imageId && (
            <>
              <Input
                id="image-question"
                label="Image question"
                value={imageQuestion}
                onChange={(e) => setImageQuestion(e.target.value)}
                className="mt-4"
              />
              <Button className="mt-3 w-full" onClick={askImageQuestion} disabled={loading}>
                {loading ? <Spinner /> : <Sparkles size={16} />}
                Analyze image
              </Button>
            </>
          )}
        </Card>
      </div>
    </div>
  )
}
