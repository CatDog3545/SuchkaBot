import { useEffect, useState } from 'react'

declare global {
  interface Window {
    Telegram: {
      WebApp: {
        ready: () => void
        expand: () => void
        close: () => void
        showMainButton: (params: { text: string; is_active: boolean; is_visible: boolean }) => void
        hideMainButton: () => void
        onEvent: (event: string, callback: () => void) => void
        offEvent: (event: string, callback: () => void) => void
        initData: string
        initDataUnsafe: {
          user?: {
            id: number
            first_name: string
            last_name?: string
            username?: string
            language_code?: string
          }
          auth_date?: string
          hash?: string
        }
        themeParams: {
          bg_color?: string
          text_color?: string
          hint_color?: string
          link_color?: string
          button_color?: string
          button_text_color?: string
          secondary_bg_color?: string
          header_bg_color?: string
          section_header_text_color?: string
          section_bg_color?: string
          section_separator_color?: string
        }
        colorScheme: 'light' | 'dark'
        isExpanded: boolean
        version: string
        platform: string
      }
    }
  }
}

export function useTelegram() {
  const [isReady, setIsReady] = useState(false)
  const [user, setUser] = useState<{
    id: number
    first_name: string
    last_name?: string
    username?: string
  } | null>(null)
  const [themeParams, setThemeParams] = useState<Record<string, string>>({})
  const [colorScheme, setColorScheme] = useState<'light' | 'dark'>('light')
  const [initData, setInitData] = useState('')

  useEffect(() => {
    const tg = window.Telegram?.WebApp
    if (!tg) {
      console.warn('Telegram Web App SDK not found, running in dev mode')
      setIsReady(true)
      return
    }

    tg.ready()
    tg.expand()

    setInitData(tg.initData || '')
    setThemeParams(tg.themeParams || {})
    setColorScheme(tg.colorScheme || 'light')

    if (tg.initDataUnsafe?.user) {
      setUser({
        id: tg.initDataUnsafe.user.id,
        first_name: tg.initDataUnsafe.user.first_name,
        last_name: tg.initDataUnsafe.user.last_name,
        username: tg.initDataUnsafe.user.username,
      })
    }

    setIsReady(true)

    tg.onEvent('themeChanged', () => {
      setThemeParams(tg.themeParams || {})
      setColorScheme(tg.colorScheme || 'light')
    })

    return () => {
      tg.offEvent('themeChanged', () => {})
    }
  }, [])

  const close = () => {
    window.Telegram?.WebApp?.close()
  }

  const expand = () => {
    window.Telegram?.WebApp?.expand()
  }

  return {
    isReady,
    user,
    themeParams,
    colorScheme,
    initData,
    close,
    expand,
    isTelegram: !!window.Telegram?.WebApp,
  }
}
