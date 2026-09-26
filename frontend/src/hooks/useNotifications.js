import { useState, useEffect, useCallback } from 'react';
import { notificationService } from '../services/notifications';

export function useNotifications() {
  const [unreadCount, setUnreadCount] = useState(0);
  const [notifications, setNotifications] = useState([]);
  const [loading, setLoading] = useState(false);

  const fetchUnreadCount = useCallback(async () => {
    try {
      const data = await notificationService.unreadCount();
      if (data && typeof data.count === 'number') {
        setUnreadCount(data.count);
      }
    } catch {
      // Background poll failure is non-fatal
    }
  }, []);

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
    fetchUnreadCount();
    const timer = setInterval(fetchUnreadCount, 10000);
    return () => clearInterval(timer);
  }, [fetchUnreadCount]);

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
