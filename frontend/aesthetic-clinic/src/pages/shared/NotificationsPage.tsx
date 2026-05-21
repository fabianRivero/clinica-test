import { useEffect, useState } from 'react'

type Item = { id:number; title:string; message:string; createdAt:string; isRead:boolean; actionUrl:string }

export function NotificationsPage() {
  const [items,setItems]=useState<Item[]>([])
  const [loading,setLoading]=useState(true)

  const load = async () => {
    const res = await fetch('/api/notifications/', { credentials:'include' })
    const data = await res.json()
    setItems(data.items || [])
    setLoading(false)
  }

  useEffect(() => { void load() }, [])

  const markAll = async () => {
    await fetch('/api/notifications/mark-all-read/', { method:'POST', credentials:'include' })
    await load()
  }

  return <section className='page-section'><header style={{display:'flex',justifyContent:'space-between',alignItems:'center'}}><h1>Notificaciones</h1><button className='button button--ghost button--compact' onClick={() => void markAll()}>Marcar todas como leidas</button></header>{loading ? <p>Cargando...</p> : <div className='table-card'><table className='table'><thead><tr><th>Estado</th><th>Mensaje</th><th>Fecha</th></tr></thead><tbody>{items.map((n)=><tr key={n.id}><td>{n.isRead ? 'Leida' : 'No leida'}</td><td><strong>{n.title}</strong><div>{n.message}</div></td><td>{new Date(n.createdAt).toLocaleString()}</td></tr>)}</tbody></table></div>}</section>
}
