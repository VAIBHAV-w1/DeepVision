import api from './api';

export const recordingService = {
  list: (params) => api.recordings.list(params),
  get: (id) => api.recordings.get(id),
  getViewUrl: (id) => api.recordings.getViewUrl(id),
  getDownloadUrl: (id) => api.recordings.getDownloadUrl(id),
};

export default recordingService;
