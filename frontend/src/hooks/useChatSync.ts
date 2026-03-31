import { useState, useEffect, useRef } from 'react'
import { useChatStore } from '../store/chatStore'

export function useChatSync(chatId: string | null) {
  const { fetchChat, currentChat } = useChatStore()
  const [initialized, setInitialized] = useState(false)
  const chatIdRef = useRef(chatId)

  useEffect(() => {
    chatIdRef.current = chatId
  }, [chatId])

  useEffect(() => {
    if (!chatId) {
      setInitialized(false)
      return
    }

    let cancelled = false

    const load = async () => {
      await fetchChat(chatId)
      if (!cancelled) {
        setInitialized(true)
      }
    }

    load()

    return () => {
      cancelled = true
    }
  }, [chatId, fetchChat])

  return {
    chat: currentChat?.chat_id === chatId ? currentChat : null,
    loading: !initialized,
  }
}
