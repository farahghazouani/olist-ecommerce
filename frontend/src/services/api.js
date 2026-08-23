// frontend/src/services/api.js
import axios from 'axios';

const api = axios.create({
  baseURL: 'http://localhost:8000/api',
  timeout: 300000,
});

export const getKpiSummary = () => api.get('/dashboard/summary').then(res => res.data);
export const getRevenueByMonth = () => api.get('/dashboard/revenue-by-month').then(res => res.data);
export const getTopCategories = (limit = 5) =>
  api.get('/dashboard/top-categories', { params: { limit } }).then(res => res.data);
export const getDashboardMetrics = (params = {}) =>
  api.get('/dashboard/metrics', { params }).then(res => res.data);
export const getRiskOrders = (params = {}) =>
  api.get('/dashboard/risk-orders', { params }).then(res => res.data);

// Machine Learning
export const getForecastCategories = () => api.get('/ml/forecast/categories').then(res => res.data);
export const getForecastByCategory = (category, state) =>
  api.get('/ml/forecast/by-category', { params: { category, state } }).then(res => res.data);
export const getDelayRisk = (payload) => api.post('/ml/predict/delay-risk', payload).then(res => res.data);
export const getDelayBatchMonteCarlo = (orders, nSimulations = 10000) =>
  api.post('/ml/predict/delay-batch-montecarlo', { orders, n_simulations: nSimulations }).then(res => res.data);

// Ventes
export const getSalesMetrics = () => api.get('/sales/metrics').then(res => res.data);
export const getRevenueByState = () => api.get('/sales/revenue-by-state').then(res => res.data);
export const getTopSellers = (limit = 10) => api.get('/sales/top-sellers', { params: { limit } }).then(res => res.data);
export const getBestSellerBySeason = () => api.get('/sales/best-seller-by-season').then(res => res.data);
export const getTopReviews = (category, limit = 3) =>
  api.get('/products/top-reviews', { params: { category, limit } }).then(res => res.data);
// Catalogue / Produits
export const getProductsAnalytics = () => api.get('/products/analytics').then(res => res.data);

// Clients
export const getCustomerSegmentsSummary = () => api.get('/customers/segments/summary').then(res => res.data);
export const getCustomerSegment = (customerUniqueId) =>
  api.get(`/customers/segments/${customerUniqueId}`).then(res => res.data);
export const getCustomerStates = () => api.get('/customers/states').then(res => res.data);
export const predictSegment = (payload) => api.post('/customers/predict-segment', payload).then(res => res.data);

// Chatbot
export const sendChatMessage = (message, context, history) =>
  api.post('/chat/message', { message, context, history }).then(res => res.data);

// Chatbot -- version streaming (SSE) : `onEvent` recoit chaque evenement
// {"event": "status"|"final", ...} des qu'il arrive, au lieu d'attendre la
// reponse complete. Permet d'afficher "recherche des top categories..."
// pendant que l'agent travaille encore, plutot qu'un spinner muet.
// `signal` (AbortController.signal) permet d'annuler proprement une requete
// en cours depuis l'UI (bouton "Annuler").
export async function sendChatMessageStream(message, context, history, onEvent, signal) {
  const response = await fetch('http://localhost:8000/api/chat/message/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, context, history }),
    signal,
  });

  if (!response.ok || !response.body) {
    throw new Error(`Erreur HTTP ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buffer = '';

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // Les messages SSE sont separes par une ligne vide ("\n\n").
    const parts = buffer.split('\n\n');
    buffer = parts.pop(); // le dernier morceau peut etre incomplet
    for (const part of parts) {
      const line = part.trim();
      if (!line.startsWith('data:')) continue;
      const jsonStr = line.slice(5).trim();
      if (!jsonStr) continue;
      try {
        const event = JSON.parse(jsonStr);
        onEvent(event);
      } catch {
        // ligne malformee -- on l'ignore plutot que de casser tout le flux
      }
    }
  }
}

export default api;