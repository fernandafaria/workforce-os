import { BrowserRouter, Routes, Route } from 'react-router-dom';
import LandingPage from './screens/Landing';
import { LoginPage } from './screens/Login';
import { HomePage } from './screens/Home';
import { AgentCreatePage } from './screens/AgentCreate';
import ConselhoPage from './screens/Conselho';
import GrupoPage from './screens/Grupo';
import './tokens.css';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/home" element={<HomePage />} />
        <Route path="/criar" element={<AgentCreatePage />} />
        <Route path="/conselho" element={<ConselhoPage />} />
        <Route path="/grupo" element={<GrupoPage />} />
      </Routes>
    </BrowserRouter>
  );
}
