import api from './api';

export const cameraService = {
  list: (params) => api.cameras.list(params),
  get: (id) => api.cameras.get(id),
  getStats: (id) => api.cameras.getStats(id),
  getStatus: (id) => api.cameras.getStatus(id),
  startRecording: (id) => api.cameras.startRecording(id),
  stopRecording: (id) => api.cameras.stopRecording(id),
  testCamera: (id) => api.cameras.testCamera(id),
  testConnection: (sourceType, source) => api.cameras.testConnection(sourceType, source),
  warm: (id) => api.cameras.warm(id),
  getStreamUrl: (id, mode) => api.cameras.getStreamUrl(id, mode),
  getOriginalStreamUrl: (id) => api.cameras.getOriginalStreamUrl(id),
  getTrackingStreamUrl: (id) => api.cameras.getTrackingStreamUrl(id),
  getSnapshotUrl: (id) => api.cameras.getSnapshotUrl(id),
};

export default cameraService;
