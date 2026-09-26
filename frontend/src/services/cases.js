import api from './api';

export const caseService = {
  list: (params) => api.cases.list(params),
  get: (id) => api.cases.get(id),
  addNote: (id, note) => api.cases.addNote(id, note),
};

export default caseService;
