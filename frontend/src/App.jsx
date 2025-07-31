import React, {useEffect, useState} from 'react'
import { Sun, Moon } from 'lucide-react'
import ChatWidget from './components/ChatWidget'
import LoginForm from './components/LoginForm'
import './index.css'

export default function App() {
    const [dark, setDark] = useState(
        () =>
            localStorage.theme === 'dark' ||
            window.matchMedia('(prefers-color-scheme: dark)').matches
    )
    // Load token from localStorage on page load
    const [token, setToken] = useState(() => localStorage.getItem('jwt_token') || null)

    // Save JWT to localStorage after login
    useEffect(() => {
        if (token) {
            localStorage.setItem('jwt_token', token)
        } else {
            localStorage.removeItem('jwt_token')
        }
    }, [token])

    // Theme toggle effect
    React.useEffect(() => {
        document.documentElement.classList.toggle('dark', dark)
        localStorage.theme = dark ? 'dark' : 'light'
    }, [dark])

    return (
        <div className="p-8 bg-background dark:bg-background text-foreground min-h-screen flex flex-col items-center">
            {/* Top bar: Theme toggle (left) + Logout (right) */}
            <div className="w-full flex justify-between items-center mb-6">
                <button onClick={() => setDark(d => !d)}>
                    {dark
                        ? <Sun size={24} className="text-primary"/>
                        : <Moon size={24} className="text-primary"/>}
                </button>
                {token && (
                    <button
                        onClick={() => {
                            setToken(null)
                            //sessionStorage.removeItem(`praxis_chat_history`)
                        }
                    }
                        className="bg-red-500 text-white px-4 py-2 rounded shadow hover:bg-red-600 transition"
                    >
                        Logout
                    </button>
                )}
            </div>
            {token
                ? <ChatWidget token={token}/>
                : <LoginForm onLogin={setToken}/>
            }
        </div>
    )
}
