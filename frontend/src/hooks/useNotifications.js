import { useState, useEffect, useCallback, useRef } from 'react';
import { notificationService } from '../services/notifications';
import { useAuth } from './useAuth';

export function useNotifications() {
  const { isAuthenticated } = useAuth();
  const [unreadCount, setUnreadCount] = useState(0);
  const [notifications, setNotifications] = useState([]);
  const [loading, setLoading] = useState(false);
  const inFlightUnreadRef = useRef(false);

  const fetchUnreadCount = useCallback(async () => {
    if (!isAuthenticated || inFlightUnreadRef.current) return;
    if (typeof document !== 'undefined' && document.hidden) return;
    inFlightUnreadRef.current = true;
    try {
      const data = await notificationService.unreadCount();
      if (data && typeof data.count === 'number') {
        setUnreadCount(data.count);
      }
    } catch {
      // Background poll failure is non-fatal
    } finally {
      inFlightUnreadRef.current = false;
    }
  }, [isAuthenticated]);

  const fetchNotifications = useCallback(async (params = { status: 'unread', per_page: 5 }) => {
    try {
      setLoading(true);
      const data = await notificationService.list(params);
      if (data && Array.isArray(data.notifications)) {
        setNotifications(data.notifications);
      }
    } catch (e) {
      console.warn('Failed to load notifications:', e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!isAuthenticated) {
      setUnreadCount(0);
      return undefined;
    }
    fetchUnreadCount();
    const timer = setInterval(fetchUnreadCount, 12000);
    const handleSync = () => fetchUnreadCount();
    window.addEventListener('notifications:updated', handleSync);
    return () => {
      clearInterval(timer);
      window.removeEventListener('notifications:updated', handleSync);
    };
  }, [isAuthenticated, fetchUnreadCount]);

  const markRead = async (id) => {
    try {
      await notificationService.markRead(id);
      setNotifications(prev => prev.filter(n => n.id !== id));
      setUnreadCount(prev => Math.max(0, prev - 1));
    } catch (e) {
      console.warn('Failed to mark notification read:', e);
    }
  };

  const markAllRead = async () => {
    try {
      await notificationService.markAllRead();
      setNotifications([]);
      setUnreadCount(0);
    } catch (e) {
      console.warn('Failed to mark all notifications read:', e);
    }
  };

  return {
    unreadCount,
    notifications,
    loading,
    fetchNotifications,
    fetchUnreadCount,
    markRead,
    markAllRead,
  };
}

export default useNotifications;
