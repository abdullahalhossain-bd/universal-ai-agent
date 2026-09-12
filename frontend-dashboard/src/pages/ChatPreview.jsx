import { useEffect, useState } from 'react'
import { Image as ImageIcon, MessageSquareText, Send, UploadCloud, Sparkles, ExternalLink, X, RefreshCw } from 'lucide-react'
import { api, ApiError } from '../api/client'
import { Alert, Button, Card, Input, PageHeader, Spinner } from '../components/ui'

const safeUrl = (value) => {
  if (typeof value !== 'string') return null
  const valueTrimmed = value.trim()
  try {
    const url = new URL(valueTrimmed, window.location.origin)
    return url.protocol === 'http:' || url.protocol === 'https:' ? url.href : null
  } catch {
    return null
  }
}

const formatPrice = (value) => {
  if (value === null || value === undefined || value === '') return ''
  const number = Number(value)
  return Number.isFinite(number) ? `$${number.toFixed(2)}` : String(value)
}

const roleLabel = (role) => {
  if (role === 'user') return 'Customer'
  if (role === 'merchant') return 'You'
  return 'AI Assistant'
}

const formatFileSize = (bytes) => {
  if (!bytes) return ''
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export default function ChatPreview() {
  const [message, setMessage] = useState('')
  const [conversation, setConversation] = useState([])
  const [conversationId, setConversationId] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [imageId, setImageId] = useState('')
  const [imageUrl, setImageUrl] = useState('')
  const [imageName, setImageName] = useState('')
  const [imageSize, setImageSize] = useState(0)
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

  useEffect(() => () => {
    if (imageUrl?.startsWith('blob:')) URL.revokeObjectURL(imageUrl)
  }, [imageUrl])

  const sendChat = async () => {
    const next = message.trim()
    if (!next) return
    setLoading(true)
    setError('')
    setConversation((prev) => [...prev, { role: 'user', content: next }, { role: 'assistant', content: 'Thinking…' }])

    try {
      const result = await api.post('/v1/chat', {
        message: next,
        conversation_id: conversationId,
      })
      if (result?.conversation_id) setConversationId(result.conversation_id)

      setConversation((prev) => {
        const items = [...prev]
        items[items.length - 1] = {
          role: 'assistant',
          content: result?.message || 'No response returned.',
          products: Array.isArray(result?.products) ? result.products : [],
          sources: Array.isArray(result?.sources) ? result.sources : [],
        }
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

  const clearUploadedImage = () => {
    if (imageUrl?.startsWith('blob:')) URL.revokeObjectURL(imageUrl)
    setImageId('')
    setImageUrl('')
    setImageName('')
    setImageSize(0)
    setError('')
  }

  const uploadImage = async (e) => {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return

    if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) {
      setError('Please choose a JPG, PNG, or WebP image.')
      return
    }

    if (imageUrl?.startsWith('blob:')) URL.revokeObjectURL(imageUrl)
    const localPreviewUrl = URL.createObjectURL(file)
    setImageUrl(localPreviewUrl)
    setImageName(file.name)
    setImageSize(file.size)
    setImageId('')
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
      if (data.url) setImageUrl(data.url)
      setError('')
    } catch (err) {
      setImageId('')
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
      const question = imageQuestion.trim() || 'What is this product?'
      const result = await fetch(`/v1/images/${encodeURIComponent(imageId)}/analyze`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${localStorage.getItem('merchant_console_token') || ''}`,
        },
        body: JSON.stringify({ question, conversation_id: conversationId }),
      })
      const data = await result.json().catch(() => ({}))
      if (!result.ok) throw new ApiError(result.status, data.detail || 'Image analysis failed')
      if (data?.conversation_id) setConversationId(data.conversation_id)
      setConversation((prev) => [
        ...prev,
        { role: 'user', content: question, image: imageUrl },
        {
          role: 'assistant',
          content: data.message || 'No visual summary returned.',
          products: Array.isArray(data.products) ? data.products : [],
          sources: Array.isArray(data.sources) ? data.sources : [],
        },
      ])
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Image analysis failed.')
    } finally {
      setLoading(false)
    }
  }

  const startNewChat = () => {
    setConversationId(null)
    clearUploadedImage()
    setConversation([
      {
        role: 'assistant',
        content: 'New conversation started. Ask about product details, shipping, policies, or items in your catalog.',
      },
    ])
    setError('')
  }

  return (
    <div>
      <PageHeader
        title="AI chat preview"
        description="Test the same retrieval and response pipeline used by your storefront assistant."
      />

      {error && (
        <div className="mb-5">
          <Alert tone="warn">{error}</Alert>
        </div>
      )}

      <div className="grid gap-5 lg:grid-cols-[1.3fr_0.7fr]">
        <Card className="flex min-h-[680px] flex-col">
          <div className="mb-4 flex items-center justify-between gap-3">
            <div className="flex items-center gap-2 text-sm font-medium text-text">
              <MessageSquareText size={16} /> Live chat test
            </div>
            <Button onClick={startNewChat} disabled={loading}>New chat</Button>
          </div>

          {conversationId && (
            <div className="mb-3 text-[10px] text-muted">Conversation: {conversationId}</div>
          )}

          <div className="flex-1 space-y-3 overflow-y-auto rounded-lg border border-line bg-paper p-3">
            {conversation.map((item, index) => (
              <div key={`${item.role}-${index}`}>
                <div className={`rounded-lg px-3 py-2 text-sm ${item.role === 'user' ? 'ml-8 bg-accent text-white' : 'mr-8 bg-white text-text border border-line'}`}>
                  <div className="mb-1 text-[10px] font-medium uppercase opacity-60">{roleLabel(item.role)}</div>
                  {item.image && (
                    <div className="mb-2 overflow-hidden rounded-lg border border-white/20 bg-black/5">
                      <img src={item.image} alt="Uploaded product" className="max-h-64 w-full object-contain" />
                    </div>
                  )}
                  <div className="whitespace-pre-wrap break-words">{item.content}</div>
                </div>

                {item.products?.length > 0 && (
                  <div className="mr-8 mt-2 grid gap-2 sm:grid-cols-2">
                    {item.products.slice(0, 6).map((product, productIndex) => {
                      const url = safeUrl(product?.product_url || product?.url || product?.link)
                      const name = product?.name || product?.title || 'Product'
                      const price = formatPrice(product?.price)
                      const stock = product?.stock
                      const content = (
                        <>
                          <div className="flex items-start justify-between gap-2">
                            <span className="font-medium">{name}</span>
                            {url && <ExternalLink size={13} className="shrink-0 opacity-50" />}
                          </div>
                          {price && <div className="mt-1 text-xs text-muted">{price}</div>}
                          {stock !== null && stock !== undefined && (
                            <div className="mt-1 text-[11px] text-muted">{Number(stock) > 0 ? 'In stock' : 'Out of stock'}</div>
                          )}
                        </>
                      )
                      return url ? (
                        <a key={`${product?.id || name}-${productIndex}`} href={url} target="_blank" rel="noopener noreferrer" className="rounded-lg border border-line bg-white p-3 text-xs text-text hover:border-accent">
                          {content}
                        </a>
                      ) : (
                        <div key={`${product?.id || name}-${productIndex}`} className="rounded-lg border border-line bg-white p-3 text-xs text-text">
                          {content}
                        </div>
                      )
                    })}
                  </div>
                )}

                {item.sources?.length > 0 && (
                  <div className="mr-8 mt-2 flex flex-wrap gap-2">
                    {item.sources.slice(0, 6).map((source, sourceIndex) => {
                      const url = safeUrl(source?.url)
                      const label = source?.title || source?.url || 'Source'
                      return url ? (
                        <a key={`${label}-${sourceIndex}`} href={url} target="_blank" rel="noopener noreferrer" className="text-[10px] text-muted underline hover:text-text">
                          {label}
                        </a>
                      ) : (
                        <span key={`${label}-${sourceIndex}`} className="text-[10px] text-muted">{label}</span>
                      )
                    })}
                  </div>
                )}
              </div>
            ))}
          </div>

          <div className="mt-4 flex gap-2">
            <Input
              id="chat-message"
              className="flex-1"
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendChat() } }}
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

          {!imageUrl ? (
            <label className="block">
              <span className="mb-2 block text-sm font-medium text-text">Upload image</span>
              <div className="group flex min-h-48 cursor-pointer flex-col items-center justify-center rounded-2xl border border-dashed border-line bg-paper px-5 py-8 text-center transition hover:border-accent hover:bg-white">
                <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-full border border-line bg-white shadow-sm transition group-hover:scale-105">
                  <UploadCloud size={21} className="text-muted" />
                </div>
                <div className="text-sm font-semibold text-text">Upload a product image</div>
                <div className="mt-1 text-xs text-muted">JPG, PNG or WebP · preview appears instantly</div>
                <input type="file" accept="image/png,image/jpeg,image/webp" className="hidden" onChange={uploadImage} disabled={uploading} />
              </div>
            </label>
          ) : (
            <div className="overflow-hidden rounded-2xl border border-line bg-paper shadow-sm">
              <div className="relative flex min-h-64 items-center justify-center bg-white p-3">
                <img src={imageUrl} alt={imageName || 'Uploaded product'} className="max-h-80 w-full rounded-xl object-contain" />
                {uploading && (
                  <div className="absolute inset-0 flex items-center justify-center bg-black/40 backdrop-blur-[2px]">
                    <div className="flex items-center gap-2 rounded-full bg-white px-4 py-2 text-xs font-medium text-text shadow-lg">
                      <Spinner /> Uploading image…
                    </div>
                  </div>
                )}
                <button
                  type="button"
                  onClick={clearUploadedImage}
                  disabled={uploading}
                  aria-label="Remove image"
                  className="absolute right-5 top-5 flex h-8 w-8 items-center justify-center rounded-full bg-white/95 text-text shadow-md transition hover:bg-white disabled:opacity-50"
                >
                  <X size={15} />
                </button>
              </div>

              <div className="border-t border-line px-4 py-3">
                <div className="flex items-center gap-3">
                  <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-white text-muted shadow-sm">
                    <ImageIcon size={17} />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-sm font-medium text-text">{imageName || 'Uploaded image'}</div>
                    <div className="mt-0.5 text-[11px] text-muted">
                      {uploading ? 'Uploading…' : imageId ? `Uploaded${imageSize ? ` · ${formatFileSize(imageSize)}` : ''}` : 'Upload failed — choose another image'}
                    </div>
                  </div>
                  <label className="cursor-pointer rounded-lg border border-line bg-white p-2 text-muted transition hover:border-accent hover:text-text" title="Replace image">
                    <RefreshCw size={15} />
                    <input type="file" accept="image/png,image/jpeg,image/webp" className="hidden" onChange={uploadImage} disabled={uploading} />
                  </label>
                </div>
              </div>
            </div>
          )}

          {imageUrl && imageId && (
            <>
              <Input
                id="image-question"
                label="What would you like to know?"
                value={imageQuestion}
                onChange={(e) => setImageQuestion(e.target.value)}
                className="mt-4"
              />
              <Button className="mt-3 w-full" onClick={askImageQuestion} disabled={loading || uploading || !imageQuestion.trim()}>
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
