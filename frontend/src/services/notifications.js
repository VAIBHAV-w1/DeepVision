import api from './api';

export const notificationService = {
  list: (params) => api.notifications.list(params),
  unreadCount: () => api.notifications.unreadCount(),
  markRead: (id) => api.notifications.markRead(id),
  markAllRead: () => api.notifications.markAllRead(),
};

export default notificationService;
