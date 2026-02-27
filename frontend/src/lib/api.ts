import axios from 'axios';
import WebApp from '@twa-dev/sdk';

// Get the initData from Telegram WebApp
const initData = WebApp.initData;

const apiClient = axios.create({
    baseURL: '/api',
    headers: {
        'Content-Type': 'application/json',
        'Authorization': `tma ${initData}`,
    },
});

export interface Notification {
    id: number;
    user_id: number;
    type: string;
    title: string;
    body: string;
    payload: any;
    is_read: boolean;
    created_at: string;
}

export interface UserProfile {
    user_id: number;
    role: 'worker' | 'customer' | null;
    name: string;
    is_registered: boolean;
}

export const api = {
    // Notifications
    getNotifications: async (limit = 50, offset = 0, filter_type = 'all') => {
        const response = await apiClient.get<Notification[]>('/notifications', {
            params: { limit, offset, filter_type },
        });
        return response.data;
    },

    markAsRead: async (id: number) => {
        const response = await apiClient.post(`/notifications/read/${id}`);
        return response.data;
    },

    markAllAsRead: async () => {
        const response = await apiClient.post('/notifications/read_all');
        return response.data;
    },

    openNotification: async (id: number) => {
        const response = await apiClient.post(`/notifications/${id}/open`);
        return response.data;
    },

    // User
    getProfile: async () => {
        const response = await apiClient.get<UserProfile>('/user/profile');
        return response.data;
    },
};

export default api;
