import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';

import './styles/globals.css';
import './styles/layout.css';
import './styles/components.css';
import './styles/camera.css';
import './styles/cameras.css';
import './styles/dashboard.css';
import './styles/recordings.css';

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
