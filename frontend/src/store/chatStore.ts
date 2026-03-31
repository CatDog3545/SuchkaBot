import { create } from 'zustand'
import type { ChatInfo, ChatDetail, Message } from '../types'

const API_BASE = import.meta.env.VITE_API_URL || ''

interface ChatStore {
  chats: ChatInfo[]
  currentChat: ChatDetail | null
  loading: boolean
  error: string | null
  streaming: boolean

  fetchChats: () => Promise<void>
  fetchChat: (chatId: string) => Promise<void>
  createChat: (name?: string) => Promise<string>
  deleteChat: (chatId: string) => Promise<void>
  renameChat: (chatId: string, name: string) => Promise<void>
  sendMessage: (chatId: string, content: string) => Promise<void>
  sendMessageStream: (chatId: string, content: string, onChunk: (chunk: string) => void) => Promise<void>
  setCurrentChat: (chat: ChatDetail | null) => void
  clearError: () => void
}

function getHeaders(): Record<string, string> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  }

  const tg = window.Telegram?.WebApp
  if (tg?.initData) {
    headers['X-Telegram-Init-Data'] = tg.initData
  }

  return headers
}

export const useChatStore = create<ChatStore>((set, get) => ({
  chats: [],
  currentChat: null,
  loading: false,
  error: null,
  streaming: false,

  fetchChats: async () => {
    set({ loading: true, error: null })
    try {
      const res = await fetch(`${API_BASE}/api/chats`, {
        headers: getHeaders(),
      })

      if (!res.ok) throw new Error(`HTTP ${res.status}`)

      const chats: ChatInfo[] = await res.json()
      set({ chats, loading: false })
    } catch (err) {
      set({ error: (err as Error).message, loading: false })
    }
  },

  fetchChat: async (chatId: string) => {
    set({ loading: true, error: null })
    try {
      const res = await fetch(`${API_BASE}/api/chats/${chatId}`, {
        headers: getHeaders(),
      })

      if (!res.ok) throw new Error(`HTTP ${res.status}`)

      const chat: ChatDetail = await res.json()
      set({ currentChat: chat, loading: false })
    } catch (err) {
      set({ error: (err as Error).message, loading: false })
    }
  },

  createChat: async (name?: string) => {
    set({ loading: true, error: null })
    try {
      const res = await fetch(`${API_BASE}/api/chats`, {
        method: 'POST',
        headers: getHeaders(),
        body: JSON.stringify({ name: name || undefined }),
      })

      if (!res.ok) throw new Error(`HTTP ${res.status}`)

      const chat: ChatDetail = await res.json()

      set((state) => ({
        currentChat: chat,
        chats: [
          {
            chat_id: chat.chat_id,
            name: chat.name,
            message_count: 0,
          },
          ...state.chats,
        ],
        loading: false,
      }))

      return chat.chat_id
    } catch (err) {
      set({ error: (err as Error).message, loading: false })
      throw err
    }
  },

  deleteChat: async (chatId: string) => {
    set({ loading: true, error: null })
    try {
      const res = await fetch(`${API_BASE}/api/chats/${chatId}`, {
        method: 'DELETE',
        headers: getHeaders(),
      })

      if (!res.ok) throw new Error(`HTTP ${res.status}`)

      set((state) => ({
        chats: state.chats.filter((c) => c.chat_id !== chatId),
        currentChat: state.currentChat?.chat_id === chatId ? null : state.currentChat,
        loading: false,
      }))
    } catch (err) {
      set({ error: (err as Error).message, loading: false })
    }
  },

  renameChat: async (chatId: string, name: string) => {
    set({ loading: true, error: null })
    try {
      const res = await fetch(`${API_BASE}/api/chats/${chatId}`, {
        method: 'PATCH',
        headers: getHeaders(),
        body: JSON.stringify({ name }),
      })

      if (!res.ok) throw new Error(`HTTP ${res.status}`)

      set((state) => ({
        chats: state.chats.map((c) =>
          c.chat_id === chatId ? { ...c, name } : c
        ),
        currentChat:
          state.currentChat?.chat_id === chatId
            ? { ...state.currentChat, name }
            : state.currentChat,
        loading: false,
      }))
    } catch (err) {
      set({ error: (err as Error).message, loading: false })
    }
  },

  sendMessage: async (chatId: string, content: string) => {
    const userMsg: Message = { role: 'user', content }

    set((state) => ({
      currentChat: state.currentChat
        ? {
            ...state.currentChat,
            messages: [...state.currentChat.messages, userMsg],
          }
        : null,
      loading: true,
      error: null,
    }))

    try {
      const res = await fetch(`${API_BASE}/api/chats/${chatId}/messages`, {
        method: 'POST',
        headers: getHeaders(),
        body: JSON.stringify({ chat_id: chatId, message: content }),
      })

      if (!res.ok) throw new Error(`HTTP ${res.status}`)

      const data = await res.json()
      const assistantMsg: Message = { role: 'assistant', content: data.response }

      set((state) => ({
        currentChat: state.currentChat
          ? {
              ...state.currentChat,
              messages: [...state.currentChat.messages, assistantMsg],
            }
          : null,
        chats: state.chats.map((c) =>
          c.chat_id === chatId
            ? { ...c, last_message: content, message_count: c.message_count + 2 }
            : c
        ),
        loading: false,
      }))
    } catch (err) {
      set({ error: (err as Error).message, loading: false })
    }
  },

  sendMessageStream: async (chatId: string, content: string, onChunk: (chunk: string) => void) => {
    const userMsg: Message = { role: 'user', content }
    let fullResponse = ''

    set((state) => ({
      currentChat: state.currentChat
        ? {
            ...state.currentChat,
            messages: [...state.currentChat.messages, userMsg],
          }
        : null,
      streaming: true,
      loading: false,
      error: null,
    }))

    try {
      const res = await fetch(`${API_BASE}/api/chats/${chatId}/messages/stream`, {
        method: 'POST',
        headers: {
          ...getHeaders(),
          Accept: 'text/event-stream',
        },
        body: JSON.stringify({ chat_id: chatId, message: content }),
      })

      if (!res.ok) throw new Error(`HTTP ${res.status}`)

      const reader = res.body?.getReader()
      if (!reader) throw new Error('No reader available')

      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const event = JSON.parse(line.slice(6))

              if (event.type === 'chunk' && event.content) {
                fullResponse += event.content
                onChunk(event.content)
              } else if (event.type === 'done') {
                const assistantMsg: Message = { role: 'assistant', content: fullResponse }

                set((state) => ({
                  currentChat: state.currentChat
                    ? {
                        ...state.currentChat,
                        messages: [...state.currentChat.messages, assistantMsg],
                      }
                    : null,
                  chats: state.chats.map((c) =>
                    c.chat_id === chatId
                      ? { ...c, last_message: content, message_count: c.message_count + 2 }
                      : c
                  ),
                  streaming: false,
                }))
              } else if (event.type === 'error') {
                throw new Error(event.message || 'Stream error')
              }
            } catch {
              // skip malformed SSE
            }
          }
        }
      }
    } catch (err) {
      set({ error: (err as Error).message, streaming: false })
    }
  },

  setCurrentChat: (chat: ChatDetail | null) => {
    set({ currentChat: chat })
  },

  clearError: () => {
    set({ error: null })
  },
}))
