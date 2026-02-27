import { useEffect, useState } from 'react';
import WebApp from '@twa-dev/sdk';
import { NotificationCenter } from './pages/NotificationCenter';

function App() {
  const [isReady, setIsReady] = useState(false);

  useEffect(() => {
    const initApp = async () => {
      try {
        // 1. Initialize Telegram WebApp SDK
        if (typeof window !== 'undefined' && WebApp) {
          WebApp.ready();
          WebApp.expand();

          console.log('WebApp initialized:', WebApp);

          // 2. Handle Dark Mode
          // ALWAYS force dark mode for this design as requested/shown in Stitch
          document.documentElement.classList.add('dark');

          WebApp.onEvent('themeChanged', () => {
            // Even on theme change, we keep it dark for now if that's what user prefers to see
            document.documentElement.classList.add('dark');
          });
        }
      } catch (e) {
        console.error('WebApp init error:', e);
      } finally {
        // Always set ready to render the UI, even if WebApp fails (e.g. local browser)
        setIsReady(true);
      }
    };

    initApp();
  }, []);

  if (!isReady) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen bg-background-light dark:bg-ios-dark text-slate-500">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary mb-2"></div>
        <p>Initializing...</p>
      </div>
    )
  }

  return (
    <NotificationCenter />
  );
}

export default App;
