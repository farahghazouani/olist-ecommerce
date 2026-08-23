import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import DashboardPage from './pages/DashboardPage';
import CatalogPage from './pages/CatalogPage';
import SalesPage from './pages/SalesPage';
import CustomersPage from './pages/CustomersPage';
import MlPredictionsPage from './pages/MlPredictionsPage';

export default function App() {
  return (
    <Router>
      <Routes>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/produits" element={<CatalogPage />} />
        <Route path="/ventes" element={<SalesPage />} />
        <Route path="/clients" element={<CustomersPage />} />
        <Route path="/previsions" element={<MlPredictionsPage />} />
      </Routes>
    </Router>
  );
}