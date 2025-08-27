// src/components/Error401.jsx
import { useEffect } from "react";

export default function Error401() {
    useEffect(() => {
        document.title = "Unauthorized - Praxis Assistant";
    }, []);

    return (
        <div className="flex items-center justify-center h-screen bg-gray-50">
            <div className="max-w-md w-full bg-white shadow-lg rounded-xl p-8 text-center border">
                <h1 className="text-3xl font-bold text-red-600 mb-3">401</h1>
                <h2 className="text-xl font-semibold mb-2">Unauthorized</h2>
                <p className="text-gray-600 mb-6">
                    Your session is invalid or expired. Please log in again.
                </p>
                <a
                    href="/"
                    className="inline-block px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
                >
                    Go to Login
                </a>
            </div>
        </div>
    );
}
