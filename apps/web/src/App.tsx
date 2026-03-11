import { NavLink, Route, Routes } from "react-router-dom";

import { ConvertPage } from "./pages/ConvertPage";
import { JobDetailPage } from "./pages/JobDetailPage";
import { LibraryPage } from "./pages/LibraryPage";
import { SettingsPage } from "./pages/SettingsPage";

export function App() {
  return (
    <div className="app-shell">
      <header className="app-header">
        <div>
          <p className="eyebrow">Local GPU Narration</p>
          <h1>NAC TTS</h1>
        </div>
        <nav className="top-nav">
          <NavLink to="/">Convert</NavLink>
          <NavLink to="/library">Library</NavLink>
          <NavLink to="/settings">Settings</NavLink>
        </nav>
      </header>
      <main className="page-frame">
        <Routes>
          <Route path="/" element={<ConvertPage />} />
          <Route path="/library" element={<LibraryPage />} />
          <Route path="/jobs/:jobId" element={<JobDetailPage />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Routes>
      </main>
    </div>
  );
}
