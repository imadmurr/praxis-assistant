// src/ChatWidget.jsx

import React, { useState, useEffect, useRef } from 'react'
import { motion } from 'framer-motion'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { User, MessageSquare, ArrowRight } from 'lucide-react'

const STORAGE_KEY = 'praxis_chat_history'

export default function ChatWidget() {
    const [messages, setMessages] = useState(() => {
        // on first render, try to load from sessionStorage
        try {
            const raw = sessionStorage.getItem(STORAGE_KEY)
            if (raw) return JSON.parse(raw).map(m => ({
                ...m,
                time: new Date(m.time)    // restore Date objects
            }))
        } catch {}
        // fallback initial message
        return [{
            sender: 'bot',
            text: '👋 Hello! How can I assist you with Praxis ERP today?',
            time: new Date()
        }]
    })

    const [input, setInput]     = useState('')
    const [loading, setLoading] = useState(false)
    const [error, setError]     = useState(null)
    const endRef                = useRef(null)

    // scroll whenever messages or loading changes
    useEffect(() => {
        endRef.current?.scrollIntoView({ behavior: 'smooth' })
    }, [messages, loading])

    // persist messages to sessionStorage on every change
    useEffect(() => {
        const toStore = messages.map(m => ({
            ...m,
            time: m.time.toISOString()
        }))
        sessionStorage.setItem(STORAGE_KEY, JSON.stringify(toStore))
    }, [messages])

    // clear error on new typing
    useEffect(() => {
        if (error) setError(null)
    }, [input])

    const formatTime = date =>
        date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })

    const send = async () => {
        const text = input.trim()
        if (!text) return

        const now = new Date()
        const userMsg = { sender: 'user', text, time: now }

        // append user → update state immediately
        setMessages(ms => [...ms, userMsg])
        setInput('')
        setLoading(true)

        // build payload from up-to-date messages
        const historyPayload = [
            ...messages,
            userMsg
        ].map(m => ({
            role: m.sender === 'user' ? 'user' : 'assistant',
            content: m.text
        }))

        try {
            const res = await fetch('/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ history: historyPayload })
            })
            if (!res.ok) throw new Error(await res.text())
            const { reply } = await res.json()

            setMessages(ms => [
                ...ms,
                { sender: 'bot', text: reply, time: new Date() }
            ])
        } catch (err) {
            console.error(err)
            setError('⚠️ Oops—something went wrong. Please try again.')
        } finally {
            setLoading(false)
        }
    }

    const onKey = e => { if (e.key === 'Enter') send() }
    const handleClick = e => {
        send()
        e.currentTarget.classList.add('animate-ripple')
        setTimeout(() => e.currentTarget.classList.remove('animate-ripple'), 400)
    }

    return (
        <div className="max-w-md w-full p-6 bg-card rounded-2xl shadow-lg flex flex-col h-[600px]">
            {error && (
                <div className="bg-red-100 border border-red-300 text-red-800 px-4 py-2 rounded mb-2 flex justify-between items-center">
                    <span>{error}</span>
                    <button className="text-red-600 font-bold" onClick={() => setError(null)}>
                        ✕
                    </button>
                </div>
            )}

            <div className="flex-1 overflow-y-auto space-y-4 pr-6">
                {messages.map((m,i) => (
                    <motion.div
                        key={i}
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: i*0.05, duration: 0.3 }}
                        className={`flex flex-col ${
                            m.sender === 'user' ? 'items-end' : 'items-start'
                        }`}
                    >
                        <div className="flex items-start space-x-3">
                            <div className={`p-2 rounded-full ${
                                m.sender==='user'
                                    ? 'bg-chart-1 text-card-foreground'
                                    : 'bg-chart-4 text-card-foreground'
                            }`}>
                                {m.sender==='user'
                                    ? <User size={16}/>
                                    : <MessageSquare size={16}/>
                                }
                            </div>
                            <div className={`prose prose-sm max-w-[85%] p-3 rounded-2xl ${
                                m.sender==='user'
                                    ? 'bg-muted text-foreground'
                                    : 'bg-card text-foreground'
                            }`}>
                                {m.sender==='bot' ? (
                                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                                        {m.text}
                                    </ReactMarkdown>
                                ) : (
                                    <span>{m.text}</span>
                                )}
                            </div>
                        </div>
                        <div className={`text-xs text-muted-foreground mt-1 ${
                            m.sender==='bot'? 'ml-[calc(2rem+0.75rem)]':''}`}>
                            {formatTime(m.time)}
                        </div>
                    </motion.div>
                ))}

                {loading && (
                    <div className="flex items-start space-x-3">
                        <div className="p-2 bg-chart-4 rounded-full text-card-foreground">
                            <MessageSquare size={16}/>
                        </div>
                        <div className="flex-1 bg-muted p-3 rounded-2xl flex space-x-1">
                            <div className="w-2 h-2 rounded-full animate-bounce"></div>
                            <div className="w-2 h-2 rounded-full animate-bounce delay-150"></div>
                            <div className="w-2 h-2 rounded-full animate-bounce delay-300"></div>
                        </div>
                    </div>
                )}
                <div ref={endRef}/>
            </div>

            <div className={`mt-4 relative transition-opacity ${
                loading ? 'opacity-50 pointer-events-none' : ''
            }`}>
                <input
                    type="text"
                    placeholder="What’s up?"
                    value={input}
                    onChange={e => setInput(e.target.value)}
                    onKeyDown={onKey}
                    disabled={loading}
                    className="w-full pr-12 pl-4 py-2 rounded-full bg-muted border border-secondary placeholder:text-muted-foreground focus:outline-none"
                />
                <button
                    onClick={handleClick}
                    disabled={loading}
                    className="absolute right-4 top-1/2 transform -translate-y-1/2"
                >
                    <ArrowRight size={20}/>
                </button>
            </div>
        </div>
    )
}
