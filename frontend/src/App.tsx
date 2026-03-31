import { useState, useCallback } from 'react'
import { useChatStore } from './store/chatStore'
import { useTelegram } from './hooks/useTelegram'
import { ChatList } from './components/ChatList'
import { ChatWindow } from './components/ChatWindow'

type View = 'list' | 'chat'

export default function App() {
  const [view, setView] = useState<View>('list')
  const [activeChatId, setActiveChatId] = useState<string | null>(null)
  const [showDrawer, setShowDrawer] = useState(false)
  const { createChat } = useChatStore()
  const { isReady, isTelegram } = useTelegram()

  const openChat = useCallback((chatId: string) => {
    setActiveChatId(chatId)
    setView('chat')
    setShowDrawer(false)
  }, [])

  const handleNewChat = useCallback(async () => {
    try {
      const chatId = await createChat()
      openChat(chatId)
      if (isTelegram) {
        window.Telegram.WebApp.HapticFeedback?.impactOccurred('light')
      }
    } catch {
      // error handled in store
    }
  }, [createChat, openChat, isTelegram])

  const handleBack = useCallback(() => {
    setView('list')
    setActiveChatId(null)
  }, [])

  const handleSelectFromDrawer = useCallback((chatId: string) => {
    openChat(chatId)
  }, [openChat])

  const handleNewFromDrawer = useCallback(async () => {
    setShowDrawer(false)
    await handleNewChat()
  }, [handleNewChat])

  if (!isReady) {
    return (
      <div className="flex items-center justify-center h-screen bg-tg-bg">
        <div className="animate-spin rounded-full h-8 w-8 border-2 border-tg-link border-t-transparent" />
      </div>
    )
  }

  return (
    <div className="h-screen w-screen overflow-hidden bg-tg-bg relative">
      {showDrawer && (
        <div
          className="absolute inset-0 z-40 bg-black/30"
          onClick={() => setShowDrawer(false)}
        />
      )}

      <div
        className={`absolute top-0 left-0 h-full z-50 w-[85%] max-w-sm transition-transform duration-300 ${
          showDrawer ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <ChatList
          onSelectChat={handleSelectFromDrawer}
          onNewChat={handleNewFromDrawer}
          onClose={() => setShowDrawer(false)}
        />
      </div>

      {view === 'list' ? (
        <div className="flex flex-col h-full">
          <div className="flex items-center justify-between px-4 py-3 bg-tg-header border-b border-tg-separator">
            <h1 className="text-lg font-bold text-tg-text">Suchka AI</h1>
            <button
              onClick={() => setShowDrawer(true)}
              className="p-2 rounded-full hover:bg-tg-secondary transition-colors"
            >
              <svg className="w-6 h-6 text-tg-text" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
              </svg>
            </button>
          </div>

          <div className="flex-1 flex flex-col items-center justify-center text-tg-hint p-6">
            <svg className="w-20 h-20 mb-4 opacity-20" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
            <p className="text-base font-medium text-tg-text mb-1">Добро пожаловать</p>
            <p className="text-sm text-center opacity-70 mb-6">
              Выберите чат из списка или создайте новый
            </p>
            <button
              onClick={handleNewChat}
              className="py-3 px-6 bg-tg-button text-tg-buttonText rounded-xl font-medium text-sm hover:opacity-90 transition-opacity active:opacity-80"
            >
              + Новый чат
            </button>
          </div>
        </div>
      ) : (
        activeChatId && (
          <ChatWindow chatId={activeChatId} onBack={handleBack} />
        )
      )}
    </div>
  )
}
