export interface Notification {
    id: number;
    user_id: number;
    type: string;
    title: string;
    body: string;
    payload?: any;
    is_read: boolean;
    created_at: string;
}
