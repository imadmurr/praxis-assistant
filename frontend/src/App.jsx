import React, {useEffect, useState} from 'react'
import { Sun, Moon } from 'lucide-react'
import ChatWidget from './components/ChatWidget'
import './index.css'

// Persist token in localStorage; also accept ?jwt=<token> once
function useJwtToken() {
    const [token, setToken] = useState(() => {
        const fromLS = localStorage.getItem('jwt_token')
        if (fromLS) return fromLS
        try {
            const url = new URL(window.location.href)
            const qp = url.searchParams.get('jwt')
            if (qp) {
                localStorage.setItem('jwt_token', qp)
                url.searchParams.delete('jwt')
                window.history.replaceState({}, '', url.toString())
                return qp
            }
        } catch {}
        return null
    })
    useEffect(() => {
        if (token) localStorage.setItem('jwt_token', token)
        else localStorage.removeItem('jwt_token')
    }, [token])
    return [token, setToken]
}

function JwtGate({ onSet }) {
    const [val, setVal] = useState('')
    return (
        <div className="w-full max-w-xs mx-auto mt-24 p-8 bg-white rounded-2xl shadow space-y-4 border">
            <h2 className="text-lg font-semibold mb-2">JWT required</h2>
            <input
                className="w-full border rounded px-3 py-2"
                value={val}
                onChange={e => setVal(e.target.value)}
                placeholder="Paste your JWT"
                autoFocus
            />
            <button
                onClick={() => val && onSet(val)}
                className="w-full bg-blue-600 text-white rounded py-2 font-bold mt-2"
            >Use token</button>
            <details className="text-sm opacity-80">
                <summary>Quick test without UI</summary>
                <pre className="mt-2 p-2 bg-gray-100 rounded">{`localStorage.setItem('jwt_token','<token>'); location.reload();`}</pre>
            </details>
        </div>
    )
}

export default function App() {
    const [dark, setDark] = useState(
        () => localStorage.theme === 'dark' || window.matchMedia('(prefers-color-scheme: dark)').matches
    )
    const [token, setToken] = useJwtToken()

    useEffect(() => {
        document.documentElement.classList.toggle('dark', dark)
        localStorage.theme = dark ? 'dark' : 'light'
    }, [dark])

    return (
        <div className="p-8 bg-background dark:bg-background text-foreground min-h-screen flex flex-col items-center">
            {/* Top bar: Theme toggle (left) + Logout (right) */}
            <div className="w-full flex justify-between items-center mb-6">
                <button onClick={() => setDark(d => !d)}>
                    {dark ? <Sun size={24} className="text-primary"/> : <Moon size={24} className="text-primary"/>}
                </button>
                {token && (
                    <button
                        onClick={() => setToken(null)}
                        className="bg-red-500 text-white px-4 py-2 rounded shadow hover:bg-red-600 transition"
                    >
                        Logout
                    </button>
                )}
            </div>

            {token ? <ChatWidget token={token}/> : <JwtGate onSet={setToken} />}
        </div>
    )
}
