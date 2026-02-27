import axios from 'axios';
import WebApp from '@twa-dev/sdk';

// Get WebApp init data if available
// We will use a mock user_id for development if not in Telegram
export const getTelegramUserId = () => {
    try {
        if (WebApp.initDataUnsafe && WebApp.initDataUnsafe.user) {
            return WebApp.initDataUnsafe.user.id;
        }
    } catch (e) {
        console.error("Error getting Telegram WebApp data:", e);
    }
    return null;
};

// Base URL for API
// In production, this should be configured. For dev, we assume localhost:8000
// If VITE_API_URL is set, use it. Otherwise, use relative path which will be proxied by Vite.
const API_BASE_URL = import.meta.env.VITE_API_URL
    ? `${import.meta.env.VITE_API_URL}/api/notifications`
    : '/api/notifications';

export const api = axios.create({
    baseURL: API_BASE_URL,
});

// Interceptor to add Authorization header
api.interceptors.request.use((config) => {
    try {
        const initData = WebApp.initData;
        if (initData) {
            config.headers.Authorization = `tma ${initData}`;
        }
    } catch (e) {
        console.error("Error getting initData:", e);
    }
    return config;
});

export const fetchNotifications = async (limit: number = 20, offset: number = 0) => {
    // Backend endpoint changed from slash user_id to just slash (root of router)
    const response = await api.get(`/`, {
        params: { limit, offset }
    });
    return response.data;
};

export const markAsRead = async (notificationId: number) => {
    const response = await api.post(`/read/${notificationId}`);
    return response.data;
};

export const markAllAsRead = async () => {
    // Backend endpoint changed from /read_all/{user_id} to /read_all
    const response = await api.post(`/read_all`);
    return response.data;
};
