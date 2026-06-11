import { Navigate } from 'react-router-dom'

export default function AuthGuard({ children }) {
  const token = localStorage.getItem('senova_token')
  if (!token) return <Navigate to="/login" replace />
  return children
}