import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import App from './App'
import Rankings from './pages/Rankings'
import SchoolProfile from './pages/SchoolProfile'
import Compare from './pages/Compare'
import About from './pages/About'
import Methodology from './pages/Methodology'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<App />}>
          <Route index element={<Rankings />} />
          <Route path="school/:unitid" element={<SchoolProfile />} />
          <Route path="compare" element={<Compare />} />
          <Route path="about" element={<About />} />
          <Route path="methodology" element={<Methodology />} />
        </Route>
      </Routes>
    </BrowserRouter>
  </React.StrictMode>
)
