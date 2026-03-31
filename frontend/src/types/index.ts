export interface Message {
  role: 'user' | 'assistant' | 'system'
  content: string
}

export interface ChatInfo {
  chat_id: string
  name: string
  last_message?: string
  last_message_time?: string
  message_count: number
}

export interface ChatDetail {
  chat_id: string
  name: string
  messages: Message[]
}

export interface StreamEvent {
  type: 'chunk' | 'done' | 'error'
  content?: string
  message?: string
}
