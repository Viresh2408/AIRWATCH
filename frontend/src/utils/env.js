const trimTrailingSlash = (value) => value?.replace(/\/+$/, '');

export const getApiBaseUrl = () => {
  const envUrl = trimTrailingSlash(import.meta.env.VITE_API_BASE_URL);

  // In browser production deployments (e.g. Vercel), route through the same-origin /api/v1 proxy
  // to completely eliminate browser CORS preflight blocks ("Failed to fetch")
  if (
    typeof window !== 'undefined' &&
    window.location?.hostname &&
    window.location.hostname !== 'localhost' &&
    window.location.hostname !== '127.0.0.1'
  ) {
    if (!envUrl || envUrl.includes('onrender.com')) {
      return '/api/v1';
    }
    return envUrl;
  }

  // Local development (localhost)
  if (envUrl) {
    return envUrl;
  }

  return 'http://localhost:8000/api/v1';
};
