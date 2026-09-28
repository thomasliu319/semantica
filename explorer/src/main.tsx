import { createRoot } from 'react-dom/client'
import './index.css'
import { installExplorerVersionFetch } from './explorerVersionFetch'
import App from './App.tsx'

installExplorerVersionFetch()

createRoot(document.getElementById('root')!).render(
  <App />,
)
