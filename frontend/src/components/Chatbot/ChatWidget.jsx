// frontend/src/components/Chatbot/ChatWidget.jsx
import { useState, useRef, useEffect } from 'react';
import { sendChatMessageStream } from '../../services/api';
import QuickSuggestions from './QuickSuggestions';
import './ChatWidget.css';

export default function ChatWidget({ pageContext }) {
  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      content:
        'Bonjour ! 👋 Je suis votre assistant BI. Posez-moi une question sur les ventes, les prévisions ou les avis clients.',
    },
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  // Statut affiche en direct pendant que l'agent travaille : "Analyse de la
  // question...", "Récupération de..." etc, mis a jour au fil du flux SSE
  // au lieu d'un simple spinner muet.
  const [statusText, setStatusText] = useState('');
  const [elapsedSec, setElapsedSec] = useState(0);
  const messagesEndRef = useRef(null);
  const abortControllerRef = useRef(null);
  const timerRef = useRef(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, statusText]);

  const stopTimer = () => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
  };

  const handleCancel = () => {
    abortControllerRef.current?.abort();
  };

  const handleSend = async (overrideText) => {
    const trimmed = (overrideText ?? input).trim();
    if (!trimmed || loading) return;

    const historyToSend = messages.map(({ role, content }) => ({ role, content }));

    setMessages((prev) => [...prev, { role: 'user', content: trimmed }]);
    setInput('');
    setLoading(true);
    setStatusText('🧠 Analyse de la question…');
    setElapsedSec(0);

    const controller = new AbortController();
    abortControllerRef.current = controller;
    const startedAt = Date.now();
    timerRef.current = setInterval(() => {
      setElapsedSec(Math.floor((Date.now() - startedAt) / 1000));
    }, 1000);

    try {
      let finalReply = null;

      await sendChatMessageStream(
        trimmed,
        pageContext,
        historyToSend,
        (event) => {
          if (event.event === 'status') {
            setStatusText(event.message);
          } else if (event.event === 'final') {
            finalReply = event.reply;
          }
        },
        controller.signal
      );

      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: finalReply ?? "Je n'ai pas pu récupérer de réponse." },
      ]);
    } catch (err) {
      if (err.name === 'AbortError') {
        setMessages((prev) => [...prev, { role: 'assistant', content: 'Demande annulée.' }]);
      } else {
        console.error('Erreur chat :', err); // <- ouvre la console navigateur (F12) pour voir le vrai détail
        setMessages((prev) => [
          ...prev,
          {
            role: 'assistant',
            content: "Désolé, une erreur est survenue en contactant l'assistant. Réessaie dans un instant.",
          },
        ]);
      }
    } finally {
      stopTimer();
      setLoading(false);
      setStatusText('');
      abortControllerRef.current = null;
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="chat-widget">
      <p className="chat-scope-note">Données historiques disponibles : sept. 2016 → août 2018.</p>
      <div className="chat-messages">
        {messages.map((msg, i) => (
          <div key={i} className={`chat-bubble msg-fade-in ${msg.role === 'user' ? 'chat-bubble-user' : 'chat-bubble-assistant'}`}>
            {msg.content}
          </div>
        ))}
        {loading && (
          <div className="chat-thinking">
            <div>{statusText || 'L\'assistant réfléchit…'}</div>
            <div className="chat-thinking-meta">
              <span>{elapsedSec}s écoulées</span>
              <button type="button" className="chat-cancel-btn" onClick={handleCancel}>
                Annuler
              </button>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {messages.length === 1 && <QuickSuggestions onSelect={handleSend} />}

      <div className="chat-input-row">
        <textarea
          id="chat-input"
          name="chat-input"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Posez votre question..."
          rows={1}
          className="chat-input"
        />
        <button onClick={() => handleSend()} disabled={loading} className="chat-send-btn">
          Envoyer
        </button>
      </div>

      <img src="/assets/bot-avatar-full2.png" alt="" className="chat-avatar avatar-float" aria-hidden="true" />
    </div>
  );
}
