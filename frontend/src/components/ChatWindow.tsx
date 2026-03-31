import { useRef, useEffect, useState } from 'react'
import { useChatStore } from '../store/chatStore'
import { useChatSync } from '../hooks/useChatSync'
import { MessageBubble } from './MessageBubble'
import { InputArea } from './InputArea'

interface ChatWindowProps {
  chatId: string
  onBack: () => void
}

export function ChatWindow({ chatId, onBack }: ChatWindowProps) {
  const { sendMessage, sendMessageStream, streaming, error, clearError } = useChatStore()
  const { chat, loading } = useChatSync(chatId)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const [streamingContent, setStreamingContent] = useState<string | null>(null)

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [chat?.messages, streamingContent])

  useEffect(() => {
    setStreamingContent(null)
  }, [chatId])

  const handleSend = async (content: string) => {
    setStreamingContent('')

    await sendMessageStream(chatId, content, (chunk: string) => {
      setStreamingContent((prev) => (prev || '') + chunk)
    })
  }

  const messages = chat?.messages || []
  const hasStreaming = streamingContent !== null && streaming

  return (
    <div className="flex flex-col h-full bg-tg-bg">
      <div className="flex items-center gap-3 px-3 py-2.5 bg-tg-header border-b border-tg-separator">
        <button
          onClick={onBack}
          className="p-1.5 rounded-full hover:bg-tg-secondary transition-colors"
        >
          <svg className="w-5 h-5 text-tg-text" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
        </button>
        <div className="flex-1 min-w-0">
          <h2 className="text-sm font-semibold text-tg-text truncate">
            {chat?.name || 'Загрузка...'}
          </h2>
          {streaming && (
            <p className="text-xs text-tg-link">печатает...</p>
          )}
        </div>
      </div>

      {error && (
        <div className="mx-3 mt-2 px-3 py-2 bg-red-500/10 text-red-500 rounded-lg text-xs flex items-center justify-between">
          <span>{error}</span>
          <button onClick={clearError} className="ml-2 font-medium">✕</button>
        </div>
      )}

      <div
        ref={containerRef}
        className="flex-1 overflow-y-auto px-3 py-3"
      >
        {loading ? (
          <div className="flex items-center justify-center h-full">
            <div className="animate-spin rounded-full h-8 w-8 border-2 border-tg-link border-t-transparent" />
          </div>
        ) : messages.length === 0 && !hasStreaming ? (
          <div className="flex flex-col items-center justify-center h-full text-tg-hint">
            <svg className="w-16 h-16 mb-3 opacity-30" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
            </svg>
            <p className="text-sm font-medium">Начните диалог</p>
            <p className="text-xs mt-1 opacity-70">Напишите что-нибудь, чтобы начать</p>
          </div>
        ) : (
          <>
            {messages.map((msg, i) => (
              <MessageBubble
                key={i}
                role={msg.role}
                content={msg.content}
              />
            ))}
            {hasStreaming && streamingContent && (
              <MessageBubble
                role="assistant"
                content={streamingContent}
                isStreaming={true}
              />
            )}
            <div ref={messagesEndRef} />
          </>
        )}
      </div>

      <InputArea
        onSend={handleSend}
        disabled={loading || streaming}
        placeholder={streaming ? 'Ожидайте ответа...' : 'Сообщение...'}
      />
    </div>
  )
}
