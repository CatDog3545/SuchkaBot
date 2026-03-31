import { clsx } from 'clsx'

interface MessageBubbleProps {
  role: 'user' | 'assistant' | 'system'
  content: string
  isStreaming?: boolean
}

export function MessageBubble({ role, content, isStreaming }: MessageBubbleProps) {
  const isUser = role === 'user'
  const isSystem = role === 'system'

  if (isSystem) {
    return (
      <div className="flex justify-center my-2">
        <span className="text-xs text-tg-hint bg-tg-secondary px-3 py-1 rounded-full">
          {content}
        </span>
      </div>
    )
  }

  return (
    <div
      className={clsx(
        'flex w-full mb-2',
        isUser ? 'justify-end' : 'justify-start'
      )}
    >
      <div
        className={clsx(
          'max-w-[85%] rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed whitespace-pre-wrap break-words',
          isUser
            ? 'bg-tg-button text-tg-buttonText rounded-br-md'
            : 'bg-tg-secondary text-tg-text rounded-bl-md'
        )}
      >
        {content}
        {isStreaming && (
          <span className="inline-block w-1.5 h-4 ml-0.5 bg-tg-text animate-pulse align-text-bottom" />
        )}
      </div>
    </div>
  )
}
