import api from './api';

export const alertService = {
  list: (params) => api.alerts.list(params),
  get: (id) => api.alerts.get(id),
  acknowledge: (id) => api.alerts.acknowledge(id),
  resolve: (id) => api.alerts.resolve(id),
};

export default alertService;
