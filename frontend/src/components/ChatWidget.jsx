// src/ChatWidget.jsx

import React, { useState, useEffect, useRef } from 'react'
import { motion } from 'framer-motion'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { User, MessageSquare, ArrowRight } from 'lucide-react'
import '../index.css'
import { BACKEND_URL } from '../lib/api.js'

// Helper to decode JWT (without verifying signature) and extract payload
function parseJwt(token) {
    if (!token) return null
    try {
        const base64Url = token.split('.')[1]
        const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/')
        const jsonPayload = decodeURIComponent(
            atob(base64)
                .split('')
                .map(c => '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2))
                .join('')
        )
        return JSON.parse(jsonPayload)
    } catch {
        return null
    }
}

export default function ChatWidget({ token }) {
    // ── State & refs ─────────────────────────────────────────────────────────
    const [messages, setMessages] = useState([])
    const [input, setInput] = useState('')
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState(null)

    const endRef = useRef(null)          // scroll anchor
    const sendBtnRef = useRef(null)      // button ref (for ripple class)
    const inputRef = useRef(null)        // input ref (optional focus, styling)

    // Extract user id from JWT
    const userId = React.useMemo(() => {
        const payload = parseJwt(token)
        return payload?.sub || 'unknown'
    }, [token])

    // ── Fetch history when token changes ────────────────────────────────────
    useEffect(() => {
        if (!token) return

        console.log('🔄 Fetching history with token:', token)
        setLoading(true)

        fetch(`${BACKEND_URL}/history`, {
            headers: { Authorization: `Bearer ${token}` },
        })
            .then(res => {
                if (res.status === 401) {
                    localStorage.removeItem('jwt_token')
                    window.location.reload() // App sees no token and shows LoginForm
                    return
                }
                if (!res.ok) throw new Error(`Status ${res.status}`)
                return res.json()
            })
            .then(data => {
                if (!data) return
                console.log('📨 /history response JSON:', data)
                const hist = Array.isArray(data.messages) ? data.messages : []
                const parsed = hist.map(m => ({
                    sender: m.sender,
                    text: m.text,
                    time: new Date(m.time),
                }))
                setMessages(parsed)
            })
            .catch(err => {
                console.error('❌ Failed to load history:', err)
            })
            .finally(() => setLoading(false))
    }, [token])

    // Scroll to bottom when messages or loading change
    useEffect(() => {
        endRef.current?.scrollIntoView({ behavior: 'smooth' })
    }, [messages, loading])

    // Clear error on new input
    useEffect(() => {
        if (error) setError(null)
    }, [input])

    // Format Date -> "HH:MM"
    const formatTime = date =>
        date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })

    // ── Send handler ──────────────────────────────────────────────────────────
    const send = async () => {
        const text = input.trim()
        if (!text) return

        const now = new Date()
        const userMsg = { sender: 'user', text, time: now }

        setMessages(ms => [...ms, userMsg])
        setInput('')
        setLoading(true)
        // optional: keep focus in the input after sending
        inputRef.current?.focus()

        const historyPayload = [...messages, userMsg].map(m => ({
            role: m.sender === 'user' ? 'user' : 'assistant',
            content: m.text,
        }))

        try {
            const res = await fetch(`${BACKEND_URL}/chat`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    Authorization: `Bearer ${token}`,
                },
                body: JSON.stringify({ history: historyPayload }),
            })
            if (res.status === 401) {
                localStorage.removeItem('jwt_token')
                window.location.reload() // kicks back to LoginForm
                return
            }
            if (!res.ok) throw new Error(await res.text())
            const { reply } = await res.json()

            setMessages(ms => [
                ...ms,
                { sender: 'bot', text: reply, time: new Date() },
            ])
        } catch (err) {
            console.error(err)
            setError('⚠️ Oops—something went wrong. Please try again.')
        } finally {
            setLoading(false)
        }
    }

    const onKey = e => {
        if (e.key === 'Enter') send()
    }

    const handleClick = e => {
        // Trigger send
        send()

        // Add ripple class safely via ref (no null errors)
        const btn = sendBtnRef.current
        btn?.classList.add('animate-ripple')
        setTimeout(() => btn?.classList.remove('animate-ripple'), 400)
    }

    return (
        <div className="max-w-md w-full p-6 bg-card rounded-2xl shadow-lg flex flex-col h-[600px]">
            {/* Greeting */}
            <div className="mb-3 font-medium text-gray-700">
                Welcome, <span className="text-primary">{userId}</span>!
            </div>

            {/* Error banner */}
            {error && (
                <div className="bg-red-100 border border-red-300 text-red-800 px-4 py-2 rounded mb-2 flex justify-between items-center">
                    <span>{error}</span>
                    <button className="text-red-600 font-bold" onClick={() => setError(null)}>
                        ✕
                    </button>
                </div>
            )}

            {/* Messages list */}
            <div className="flex-1 overflow-y-auto space-y-4 pr-6">
                {/* Fallback welcome if no history */}
                {messages.length === 0 && !loading && (
                    <motion.div
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        className="flex flex-col items-start"
                    >
                        <div className="prose prose-sm max-w-[85%] p-3 rounded-2xl bg-card text-foreground">
                            👋 Hello! How can I assist you with Praxis ERP today?
                        </div>
                    </motion.div>
                )}

                {messages.map((m, i) => (
                    <motion.div
                        key={i}
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: i * 0.05, duration: 0.3 }}
                        className={`flex flex-col ${
                            m.sender === 'user' ? 'items-end' : 'items-start'
                        }`}
                    >
                        <div className="flex items-start space-x-3">
                            <div
                                className={`p-2 rounded-full ${
                                    m.sender === 'user'
                                        ? 'bg-primary text-primary-foreground'
                                        : 'bg-secondary text-secondary-foreground'
                                }`}
                            >
                                {m.sender === 'user' ? <User size={16} /> : <MessageSquare size={16} />}
                            </div>
                            <div
                                className={`prose prose-sm max-w-[85%] p-3 rounded-2xl ${
                                    m.sender === 'user' ? 'bg-muted text-foreground' : 'bg-card text-foreground'
                                }`}
                            >
                                {m.sender === 'bot' ? (
                                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.text}</ReactMarkdown>
                                ) : (
                                    <span>{m.text}</span>
                                )}
                            </div>
                        </div>
                        <div
                            className={`text-xs text-muted-foreground mt-1 ${
                                m.sender === 'bot' ? 'ml-[calc(2rem+0.75rem)]' : ''
                            }`}
                        >
                            {formatTime(m.time)}
                        </div>
                    </motion.div>
                ))}

                {/* Typing indicator */}
                {loading && (
                    <div className="flex items-start space-x-3">
                        <div className="p-2 bg-chart-4 rounded-full text-card-foreground">
                            <MessageSquare size={16} />
                        </div>
                        <div className="flex-1 bg-muted p-3 rounded-2xl text-foreground flex space-x-1">
                            <div className="w-2 h-2 rounded-full animate-bounce"></div>
                            <div className="w-2 h-2 rounded-full animate-bounce delay-150"></div>
                            <div className="w-2 h-2 rounded-full animate-bounce delay-300"></div>
                        </div>
                    </div>
                )}
                <div ref={endRef} />
            </div>

            {/* Input */}
            <div className={`mt-4 relative transition-opacity ${loading ? 'opacity-50 pointer-events-none' : ''}`}>
                <input
                    ref={inputRef}
                    type="text"
                    placeholder="What’s up?"
                    value={input}
                    onChange={e => setInput(e.target.value)}
                    onKeyDown={onKey}
                    disabled={loading}
                    className="w-full pr-12 pl-4 py-2 rounded-full bg-muted border border-secondary placeholder:text-muted-foreground focus:outline-none"
                />
                <button
                    ref={sendBtnRef}
                    onClick={handleClick}
                    disabled={loading}
                    className="absolute right-4 top-1/2 transform -translate-y-1/2"
                >
                    <ArrowRight size={20} />
                </button>
            </div>
        </div>
    )
}
