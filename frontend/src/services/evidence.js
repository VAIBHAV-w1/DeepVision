import api from './api';

export const evidenceService = {
  list: (params) => api.evidence.list(params),
  get: (id) => api.evidence.get(id),
  getPreviewUrl: (id) => api.evidence.getPreviewUrl(id),
  getDownloadUrl: (id) => api.evidence.getDownloadUrl(id),
};

export default evidenceService;
