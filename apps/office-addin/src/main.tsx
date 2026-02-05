import React from 'react';
import ReactDOM from 'react-dom/client';
import { FluentProvider, webLightTheme } from '@fluentui/react-components';
import App from './App';
import './styles/globals.css';

const rootEl = document.getElementById('root');

if (!rootEl) {
  throw new Error('Root element not found');
}

Office.onReady(() => {
  ReactDOM.createRoot(rootEl).render(
    <React.StrictMode>
      <FluentProvider theme={webLightTheme}>
        <App />
      </FluentProvider>
    </React.StrictMode>
  );
});
