import React, { useState } from 'react'
import {AUTH_URL} from "../.lib/api.js";

export default function LoginForm({ onLogin }) {
    const [username, setUsername] = useState("")
    const [error, setError] = useState(null)
    const handleLogin = async () => {
        setError(null)
        if (!username) return setError("Enter a username")
        try {
            const res = await fetch(`${AUTH_URL}/login`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username })
            })
            const data = await res.json()
            if (data.token) {
                onLogin(data.token)
            } else {
                setError(data.error || "Login failed")
            }
        } catch {
            setError("Server error")
        }
    }
    return (
        <div className="w-full max-w-xs mx-auto mt-24 p-8 bg-white rounded-2xl shadow space-y-4 border">
            <h2 className="text-lg font-semibold mb-2">Sign In</h2>
            <input
                className="w-full border rounded px-3 py-2"
                value={username}
                onChange={e => setUsername(e.target.value)}
                placeholder="Username"
                autoFocus
            />
            <button
                onClick={handleLogin}
                className="w-full bg-blue-600 text-white rounded py-2 font-bold mt-2"
            >Login</button>
            {error && <div className="text-red-600 text-sm">{error}</div>}
        </div>
    )
}
