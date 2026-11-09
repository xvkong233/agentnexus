import { create } from 'zustand'

export const useAuth = create((set) => ({
  token: localStorage.getItem('token') || '',
  role: localStorage.getItem('role') || '',
  name: localStorage.getItem('name') || '',
  setSession: (token, role, name) => {
    set({ token, role, name })
    localStorage.setItem('token', token)
    localStorage.setItem('role', role)
    localStorage.setItem('name', name || '')
  },
  logout: () => {
    set({ token: '', role: '', name: '' })
    localStorage.removeItem('token')
    localStorage.removeItem('role')
    localStorage.removeItem('name')
  },
}))
