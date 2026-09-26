import api from './api';

export const authService = {
  me: () => api.auth.me(),
  csrf: () => api.auth.csrf(),
  login: (email, password) => api.auth.login(email, password),
  signup: (data) => api.auth.signup(data),
  verifyOtp: (email, otp) => api.auth.verifyOtp(email, otp),
  resendOtp: (email) => api.auth.resendOtp(email),
  forgotPassword: (email) => api.auth.forgotPassword(email),
  resetPassword: (data) => api.auth.resetPassword(data),
  logout: () => api.auth.logout(),
};

export default authService;
