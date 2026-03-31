import { useEffect } from 'react'
import { useChatStore } from '../store/chatStore'
import { useTelegram } from '../hooks/useTelegram'
import type { ChatInfo } from '../types'

interface ChatListProps {
  onSelectChat: (chatId: string) => void
  onNewChat: () => void
  onClose: () => void
}

export function ChatList({ onSelectChat, onNewChat, onClose }: ChatListProps) {
  const { chats, loading, fetchChats, deleteChat } = useChatStore()
  const { isTelegram } = useTelegram()

  useEffect(() => {
    fetchChats()
  }, [fetchChats])

  const formatDate = (dateStr?: string) => {
    if (!dateStr) return ''
    const d = new Date(dateStr)
    const now = new Date()
    const diff = now.getTime() - d.getTime()

    if (diff < 86400000) {
      return d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
    }
    return d.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' })
  }

  const handleDelete = async (e: React.MouseEvent, chatId: string) => {
    e.stopPropagation()
    await deleteChat(chatId)
    if (isTelegram) {
      window.Telegram.WebApp.HapticFeedback?.notificationOccurred('success')
    }
  }

  return (
    <div className="flex flex-col h-full bg-tg-bg">
      <div className="flex items-center justify-between px-4 py-3 border-b border-tg-separator">
        <h2 className="text-lg font-semibold text-tg-text">Чаты</h2>
        <button
          onClick={onClose}
          className="p-2 rounded-full hover:bg-tg-secondary transition-colors"
        >
          <svg className="w-5 h-5 text-tg-hint" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      <div className="flex-1 overflow-y-auto">
        {loading && chats.length === 0 ? (
          <div className="flex items-center justify-center h-32">
            <div className="animate-spin rounded-full h-6 w-6 border-2 border-tg-link border-t-transparent" />
          </div>
        ) : chats.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-48 text-tg-hint">
            <svg className="w-12 h-12 mb-2 opacity-50" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
            </svg>
            <p className="text-sm">Нет чатов</p>
          </div>
        ) : (
          <ul className="divide-y divide-tg-separator">
            {chats.map((chat: ChatInfo) => (
              <li
                key={chat.chat_id}
                onClick={() => onSelectChat(chat.chat_id)}
                className="flex items-center gap-3 px-4 py-3 hover:bg-tg-secondary cursor-pointer transition-colors active:opacity-70"
              >
                <div className="flex-shrink-0 w-10 h-10 rounded-full bg-tg-button flex items-center justify-center text-tg-buttonText font-semibold text-sm">
                  {chat.name.charAt(0).toUpperCase()}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between">
                    <p className="text-sm font-medium text-tg-text truncate">{chat.name}</p>
                    {chat.last_message_time && (
                      <span className="text-xs text-tg-hint ml-2 flex-shrink-0">
                        {formatDate(chat.last_message_time)}
                      </span>
                    )}
                  </div>
                  {chat.last_message && (
                    <p className="text-xs text-tg-hint truncate mt-0.5">{chat.last_message}</p>
                  )}
                </div>
                <button
                  onClick={(e) => handleDelete(e, chat.chat_id)}
                  className="flex-shrink-0 p-1.5 rounded-full hover:bg-red-500/10 text-tg-hint hover:text-red-500 transition-colors opacity-0 group-hover:opacity-100"
                  title="Удалить чат"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                  </svg>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="p-4 border-t border-tg-separator">
        <button
          onClick={onNewChat}
          className="w-full py-2.5 px-4 bg-tg-button text-tg-buttonText rounded-xl font-medium text-sm hover:opacity-90 transition-opacity active:opacity-80"
        >
          + Новый чат
        </button>
      </div>
    </div>
  )
}
