import React from 'react';
import Navbar from '../components/common/Navbar';
import Footer from '../components/common/Footer';
import AssistantChat from '../components/common/AssistantChat';
import useNotifications from '../hooks/useNotifications';

export function AppLayout({ children, activePage, setActivePage }) {
  const { unreadCount } = useNotifications();

  return (
    <div className="app-layout">
      <div className="app-main">
        <Navbar
          activePage={activePage}
          setActivePage={setActivePage}
          unreadNotifCount={unreadCount}
        />
        <main className="app-content app-content-container">
          {children}
        </main>
        <Footer />
      </div>
      <AssistantChat />
    </div>
  );
}

export default AppLayout;
