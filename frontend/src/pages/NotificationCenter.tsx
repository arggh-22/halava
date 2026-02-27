import React, { useState, useEffect } from 'react';
import { Header } from '../components/Header';
import { Tabs } from '../components/Tabs';
import { BottomNav } from '../components/BottomNav';
import { NotificationCard } from '../components/NotificationCard';
import { api } from '../lib/api';
import type { Notification } from '../lib/api';
import WebApp from '@twa-dev/sdk';

export const NotificationCenter: React.FC = () => {
    const [activeTab, setActiveTab] = useState('Все');
    const [notifications, setNotifications] = useState<Notification[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);


    // Dynamic fetching based on activeTab
    useEffect(() => {
        const fetchData = async () => {
            try {
                setIsLoading(true);


                // Determine filter_type based on activeTab
                let filterType = 'all';
                if (activeTab === 'Чаты') filterType = 'chats';
                if (activeTab === 'Контакты' || activeTab === 'Отклики') filterType = 'contacts';
                if (activeTab === 'Объявления') filterType = 'system'; // 'order' falls into system/others

                // Fetch notifications
                const data = await api.getNotifications(50, 0, filterType);
                setNotifications(data);
                setIsLoading(false);
            } catch (err: any) {
                console.error('Failed to fetch data:', err);
                setError(err.message || 'Failed to load notifications');
                setIsLoading(false);
            }
        };

        fetchData();
    }, [activeTab]);

    const tabs = ['Все', 'Объявления', 'Отклики', 'Чаты', 'Контакты'];

    // Client-side refinement (after server-side filtering)
    const filteredNotifications = notifications.filter(n => {
        if (activeTab === 'Все') return true;
        if (activeTab === 'Объявления') return n.type === 'order';
        if (activeTab === 'Отклики') return ['response', 'new_response', 'response_rejected'].includes(n.type);
        if (activeTab === 'Чаты') return true; // Already filtered by server (grouped)
        if (activeTab === 'Контакты') return !['response', 'new_response', 'response_rejected'].includes(n.type);
        return true;
    });



    const handleAction = async (id: number, action: 'view' | 'decline') => {
        console.log(`Action ${action} for notification ${id}`);

        if (action === 'view') {
            try {
                WebApp.HapticFeedback.impactOccurred('medium');
                await api.openNotification(id);
                // Mark local as read
                setNotifications(notifications.map(n => n.id === id ? { ...n, is_read: true } : n));
                WebApp.close();
            } catch (err) {
                console.error('Failed to open notification:', err);
            }
        }

        if (action === 'decline') {
            try {
                WebApp.HapticFeedback.notificationOccurred('warning');
                await api.markAsRead(id);
                // Mark local as read
                setNotifications(notifications.map(n => n.id === id ? { ...n, is_read: true } : n));
            } catch (err) {
                console.error('Failed to decline notification:', err);
            }
        }
    };

    if (isLoading) {
        return (
            <div className="min-h-screen bg-background-dark flex items-center justify-center">
                <div className="animate-spin rounded-full h-8 w-8 border-t-2 border-primary"></div>
            </div>
        );
    }

    if (error) {
        return (
            <div className="min-h-screen bg-background-dark flex flex-col items-center justify-center p-6 text-center">
                <div className="text-red-500 mb-4">
                    <span className="material-symbols-rounded text-4xl">error</span>
                </div>
                <h2 className="text-xl font-semibold mb-2">Произошла ошибка</h2>
                <p className="text-gray-400 mb-6">{error}</p>
                <button
                    onClick={() => window.location.reload()}
                    className="bg-primary text-white px-6 py-2 rounded-xl font-medium"
                >
                    Попробовать снова
                </button>
            </div>
        );
    }

    return (
        <div className="min-h-screen bg-background-dark pb-24 text-white">
            <Header
                title="Уведомления"
            />

            <div className="px-4 py-2 sticky top-[60px] z-20 bg-background-dark/80 backdrop-blur-sm">
                <Tabs
                    tabs={tabs}
                    activeTab={activeTab}
                    onTabChange={setActiveTab}
                />
            </div>

            <main className="px-4 pt-2 space-y-3">


                {filteredNotifications.length > 0 ? (
                    filteredNotifications.map((notification) => (
                        <NotificationCard
                            key={notification.id}
                            type={
                                (notification.type === 'response' || notification.type === 'new_response')
                                    ? 'response'
                                    : (notification.type === 'worker' || notification.type === 'customer' || notification.type === 'chat_message' || notification.type === 'anonymous_chat')
                                        ? 'message'
                                        : notification.type as any
                            }
                            title={notification.title}
                            body={notification.body}
                            time={new Date(notification.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                            isRead={notification.is_read}
                            onClick={() => handleAction(notification.id, 'view')}
                            onAction={(action) => handleAction(notification.id, action as any)}
                        />
                    ))
                ) : (
                    <div className="flex flex-col items-center justify-center py-20 text-gray-500">
                        <span className="material-symbols-rounded text-5xl mb-4 opacity-20">notifications_off</span>
                        <p>Уведомлений пока нет</p>
                    </div>
                )}
            </main>
            <BottomNav activeTab="Alerts" />
        </div >
    );
};
