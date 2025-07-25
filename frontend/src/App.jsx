import React, { useState, useEffect } from 'react'
import { Sun, Moon } from 'lucide-react'
import ChatWidget from './components/ChatWidget'
import './index.css'

export default function App() {
    const [dark, setDark] = useState(
        () =>
            localStorage.theme === 'dark' ||
            window.matchMedia('(prefers-color-scheme: dark)').matches
    )

    useEffect(() => {
        document.documentElement.classList.toggle('dark', dark)
        localStorage.theme = dark ? 'dark' : 'light'
    }, [dark])

    return (
        <div className="p-8 bg-background dark:bg-background text-foreground min-h-screen flex flex-col items-center">
            <button onClick={() => setDark(d => !d)} className="self-end mb-4">
                {dark
                    ? <Sun size={24} className="text-primary"/>
                    : <Moon size={24} className="text-primary"/>}
            </button>
            <ChatWidget />
        </div>
    )
}
