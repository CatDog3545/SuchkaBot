import { useState, useRef, useEffect } from 'react'

interface InputAreaProps {
  onSend: (message: string) => void
  disabled?: boolean
  placeholder?: string
}

export function InputArea({ onSend, disabled, placeholder }: InputAreaProps) {
  const [text, setText] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
      textareaRef.current.style.height = Math.min(textareaRef.current.scrollHeight, 120) + 'px'
    }
  }, [text])

  const handleSend = () => {
    const trimmed = text.trim()
    if (!trimmed || disabled) return

    onSend(trimmed)
    setText('')

    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="flex items-end gap-2 p-3 bg-tg-bg border-t border-tg-separator">
      <textarea
        ref={textareaRef}
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={placeholder || 'Сообщение...'}
        disabled={disabled}
        rows={1}
        className="flex-1 resize-none bg-tg-secondary text-tg-text placeholder-tg-hint rounded-xl px-3.5 py-2.5 text-sm leading-relaxed focus:outline-none focus:ring-2 focus:ring-tg-link/30 disabled:opacity-50 max-h-[120px]"
      />
      <button
        onClick={handleSend}
        disabled={!text.trim() || disabled}
        className="flex-shrink-0 w-10 h-10 rounded-full bg-tg-button text-tg-buttonText flex items-center justify-center disabled:opacity-40 transition-all active:scale-95"
      >
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
        </svg>
      </button>
    </div>
  )
}
