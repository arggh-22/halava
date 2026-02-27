import React from 'react';
import { cn } from '../lib/utils';

export type NotificationType = 'response' | 'order' | 'contact_bought' | 'system' | 'message' | 'contact_request' | 'contact_reject' | 'response_rejected' | 'info' | 'contact_offer';

interface NotificationCardProps {
    type: NotificationType;
    title: string;
    body: string;
    time: string;
    avatarUrl?: string; // For response/message
    rating?: number; // For worker response
    budget?: string; // For order
    isVerified?: boolean; // For order
    isRead?: boolean;
    onClick?: () => void;
    onAction?: (action: string) => void;
}

export const NotificationCard: React.FC<NotificationCardProps> = ({
    type, title, body, time, avatarUrl, rating, budget, isVerified, isRead, onClick, onAction
}) => {
    const isUnread = !isRead;

    // 1. Worker Response Card
    if (type === 'response') {
        return (
            <div className={cn(
                "relative flex flex-col gap-3 rounded-xl bg-white dark:bg-ios-card p-4 shadow-sm border transition-all active:scale-[0.98]",
                isRead ? "opacity-70 border-slate-100 dark:border-white/5" : "border-slate-200 dark:border-white/10"
            )} onClick={onClick}>
                {isUnread && <div className="absolute left-1.5 top-1/2 -translate-y-1/2 w-1.5 h-1.5 rounded-full bg-primary"></div>}
                <div className="flex items-center gap-3">
                    <div className="relative">
                        {avatarUrl ? (
                            <div className="h-12 w-12 rounded-full bg-center bg-cover border border-slate-200 dark:border-white/10" style={{ backgroundImage: `url(${avatarUrl})` }}></div>
                        ) : (
                            <div className="h-12 w-12 rounded-full bg-slate-200 dark:bg-white/10 flex items-center justify-center">
                                <span className="material-symbols-outlined text-slate-400">person</span>
                            </div>
                        )}
                        <div className="absolute -bottom-1 -right-1 flex h-5 w-5 items-center justify-center rounded-full bg-primary text-white text-[10px] font-bold border-2 border-white dark:border-ios-card">
                            <span className="material-symbols-outlined text-[12px] leading-none">bolt</span>
                        </div>
                    </div>
                    <div className="flex flex-col flex-1 min-w-0">
                        <div className="flex items-center justify-between">
                            <p className="text-[15px] font-bold dark:text-white truncate">
                                {title} {rating && <span className="text-amber-400 font-medium ml-1">{rating}★</span>}
                            </p>
                            <span className="text-slate-400 dark:text-slate-500 text-[12px] whitespace-nowrap">{time}</span>
                        </div>
                        <p className="text-slate-600 dark:text-slate-400 text-sm leading-snug line-clamp-3 break-words" dangerouslySetInnerHTML={{ __html: body }} />
                    </div>
                </div>
                <div className="flex gap-2 pl-12">
                    <button onClick={(e) => { e.stopPropagation(); onAction?.('view'); }} className="flex-1 py-2 rounded-lg bg-primary text-white text-sm font-semibold active:opacity-80 transition-opacity">
                        Посмотреть
                    </button>
                    <button onClick={(e) => { e.stopPropagation(); onAction?.('decline'); }} className="px-4 py-2 rounded-lg bg-slate-100 dark:bg-white/10 text-slate-900 dark:text-white text-sm font-semibold active:opacity-70 transition-all">
                        Скрыть
                    </button>
                </div>
            </div>
        );
    }

    // 2. New Order Card
    if (type === 'order') {
        return (
            <div className={cn(
                "relative flex flex-col gap-3 rounded-xl bg-white dark:bg-ios-card p-4 shadow-sm border transition-all active:scale-[0.98] overflow-hidden",
                isRead ? "opacity-70 border-slate-100 dark:border-white/5" : "border-slate-200 dark:border-white/10"
            )} onClick={onClick}>
                {isUnread && <div className="absolute left-1.5 top-1/2 -translate-y-1/2 w-1.5 h-1.5 rounded-full bg-primary"></div>}
                <div className="flex items-start gap-3">
                    <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
                        <span className="material-symbols-outlined text-[28px]">work</span>
                    </div>
                    <div className="flex flex-col flex-1 min-w-0">
                        <div className="flex items-center justify-between gap-2">
                            <p className="text-[15px] font-bold dark:text-white truncate">{title}</p>
                            <span className="text-slate-400 dark:text-slate-500 text-[12px] whitespace-nowrap">{time}</span>
                        </div>
                        <p className="text-slate-600 dark:text-slate-400 text-sm leading-snug mb-1 line-clamp-3 break-words" dangerouslySetInnerHTML={{ __html: body }} />
                        <div className="flex items-center gap-1.5">
                            {budget && <span className="px-2 py-0.5 rounded-full bg-primary/20 text-primary text-[11px] font-bold">BUDGET {budget}</span>}
                            {isVerified && <span className="px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-500 text-[11px] font-bold">VERIFIED</span>}
                        </div>
                    </div>
                </div>
                <div className="flex gap-2 pl-12">
                    <button onClick={(e) => { e.stopPropagation(); onAction?.('view'); }} className="flex-1 py-2 rounded-lg bg-primary text-white text-sm font-semibold active:opacity-80 transition-opacity">
                        Посмотреть
                    </button>
                    <button onClick={(e) => { e.stopPropagation(); onAction?.('decline'); }} className="px-4 py-2 rounded-lg bg-slate-100 dark:bg-white/10 text-slate-900 dark:text-white text-sm font-semibold active:opacity-70 transition-all">
                        Скрыть
                    </button>
                </div>
            </div>
        );
    }

    // 3. Contact Request Card
    if (type === 'contact_request') {
        return (
            <div className={cn(
                "relative flex flex-col gap-3 rounded-xl bg-white dark:bg-ios-card p-4 shadow-sm border transition-all active:scale-[0.98] overflow-hidden",
                isRead ? "opacity-70 border-slate-100 dark:border-white/5" : "border-slate-200 dark:border-white/10"
            )} onClick={onClick}>
                {isUnread && <div className="absolute left-1.5 top-1/2 -translate-y-1/2 w-1.5 h-1.5 rounded-full bg-primary"></div>}
                <div className="flex items-start gap-3">
                    <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-blue-500/10 text-blue-500">
                        <span className="material-symbols-outlined text-[28px]">contact_phone</span>
                    </div>
                    <div className="flex flex-col flex-1 min-w-0">
                        <div className="flex items-center justify-between gap-2">
                            <p className="text-[15px] font-bold dark:text-white truncate">{title}</p>
                            <span className="text-slate-400 dark:text-slate-500 text-[12px] whitespace-nowrap">{time}</span>
                        </div>
                        <p className="text-slate-600 dark:text-slate-400 text-sm leading-snug mb-1 line-clamp-3 break-words" dangerouslySetInnerHTML={{ __html: body }} />
                    </div>
                </div>
                <div className="flex gap-2 pl-12">
                    <button onClick={(e) => { e.stopPropagation(); onAction?.('view'); }} className="flex-1 py-2 rounded-lg bg-blue-500 text-white text-sm font-semibold active:opacity-80 transition-opacity">
                        Посмотреть
                    </button>
                    <button onClick={(e) => { e.stopPropagation(); onAction?.('decline'); }} className="px-4 py-2 rounded-lg bg-slate-100 dark:bg-white/10 text-slate-900 dark:text-white text-sm font-semibold active:opacity-70 transition-all">
                        Скрыть
                    </button>
                </div>
            </div>
        );
    }

    // 3.1 Contact Offer Card (Green for Offer, no buttons)
    if (type === 'contact_offer') {
        return (
            <div className={cn(
                "relative flex flex-col gap-3 rounded-xl bg-white dark:bg-ios-card p-4 shadow-sm border transition-all active:scale-[0.98] overflow-hidden",
                isRead ? "opacity-70 border-slate-100 dark:border-white/5" : "border border-emerald-500/30 dark:border-emerald-500/20 ring-1 ring-emerald-500/10"
            )} onClick={onClick}>
                {isUnread && <div className="absolute left-1.5 top-1/2 -translate-y-1/2 w-1.5 h-1.5 rounded-full bg-emerald-500"></div>}
                <div className="flex items-start gap-3">
                    <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-emerald-500/10 text-emerald-500">
                        <span className="material-symbols-outlined text-[28px]">contact_mail</span>
                    </div>
                    <div className="flex flex-col flex-1 min-w-0">
                        <div className="flex items-center justify-between gap-2">
                            <p className="text-[15px] font-bold dark:text-white truncate">{title}</p>
                            <span className="text-slate-400 dark:text-slate-500 text-[12px] whitespace-nowrap">{time}</span>
                        </div>
                        {/* Use line-clamp-3 and whitespace-pre-wrap to handle newlines and multi-line text */}
                        <p className="text-slate-600 dark:text-slate-400 text-sm leading-snug mb-1 line-clamp-3 break-words whitespace-pre-wrap" dangerouslySetInnerHTML={{ __html: body }} />
                    </div>
                </div>
            </div>
        );
    }

    // 4. Contact Reject / Decline (Red Highlights)
    if (type === 'contact_reject') {
        return (
            <div className={cn(
                "relative flex flex-col gap-3 rounded-xl bg-white dark:bg-ios-card p-4 shadow-sm border border-red-500/30 dark:border-red-500/20 ring-1 ring-red-500/10 active:scale-95 transition-transform overflow-hidden",
                isRead && "opacity-70"
            )} onClick={onClick}>
                {isUnread && <div className="absolute left-1.5 top-1/2 -translate-y-1/2 w-1.5 h-1.5 rounded-full bg-red-500"></div>}
                <div className="flex items-start gap-3">
                    <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-red-500/10 text-red-500">
                        <span className="material-symbols-outlined text-[28px]">block</span>
                    </div>
                    <div className="flex flex-col flex-1 min-w-0">
                        <div className="flex items-center justify-between gap-2">
                            <p className="text-[15px] font-bold dark:text-white truncate">{title}</p>
                            <span className="text-slate-400 dark:text-slate-500 text-[12px] whitespace-nowrap">{time}</span>
                        </div>
                        <p className="text-slate-600 dark:text-slate-400 text-sm leading-snug break-words line-clamp-3" dangerouslySetInnerHTML={{ __html: body }} />
                    </div>
                </div>
            </div>
        );
    }

    // 5. Response Rejected (Red Highlights)
    if (type === 'response_rejected') {
        return (
            <div className={cn(
                "relative flex flex-col gap-3 rounded-xl bg-white dark:bg-ios-card p-4 shadow-sm border border-red-500/30 dark:border-red-500/20 ring-1 ring-red-500/10 active:scale-95 transition-transform overflow-hidden",
                isRead && "opacity-70"
            )} onClick={onClick}>
                {isUnread && <div className="absolute left-1.5 top-1/2 -translate-y-1/2 w-1.5 h-1.5 rounded-full bg-red-500"></div>}
                <div className="flex items-start gap-3">
                    <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-red-500/10 text-red-500">
                        <span className="material-symbols-outlined text-[28px]">block</span>
                    </div>
                    <div className="flex flex-col flex-1 min-w-0">
                        <div className="flex items-center justify-between gap-2">
                            <p className="text-[15px] font-bold dark:text-white truncate">{title}</p>
                            <span className="text-slate-400 dark:text-slate-500 text-[12px] whitespace-nowrap">{time}</span>
                        </div>
                        <p className="text-slate-600 dark:text-slate-400 text-sm leading-snug break-words line-clamp-3" dangerouslySetInnerHTML={{ __html: body }} />
                    </div>
                </div>
            </div>
        );
    }

    // 3. Contact Purchase / Success (Green Highlights)
    if (type === 'contact_bought') {
        return (
            <div className={cn(
                "relative flex flex-col gap-3 rounded-xl bg-white dark:bg-ios-card p-4 shadow-sm border border-emerald-500/30 dark:border-emerald-500/20 ring-1 ring-emerald-500/10 active:scale-95 transition-transform overflow-hidden",
                isRead && "opacity-70"
            )} onClick={onClick}>
                {isUnread && <div className="absolute left-1.5 top-1/2 -translate-y-1/2 w-1.5 h-1.5 rounded-full bg-emerald-500"></div>}
                <div className="flex items-start gap-3">
                    <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-emerald-500/10 text-emerald-500">
                        <span className="material-symbols-outlined text-[28px]">phone_iphone</span>
                    </div>
                    <div className="flex flex-col flex-1 min-w-0">
                        <div className="flex items-center justify-between gap-2">
                            <p className="text-[15px] font-bold dark:text-white truncate">{title}</p>
                            <span className="text-slate-400 dark:text-slate-500 text-[12px] whitespace-nowrap">{time}</span>
                        </div>
                        <p className="text-slate-600 dark:text-slate-400 text-sm leading-snug break-words line-clamp-3" dangerouslySetInnerHTML={{ __html: body }} />
                    </div>
                </div>
            </div>
        );
    }

    // 4. Message / Chat
    if (type === 'message') {
        return (
            <div className={cn(
                "relative flex items-center gap-4 rounded-xl bg-white dark:bg-ios-card p-4 shadow-sm border transition-transform active:scale-95 overflow-hidden",
                isRead ? "opacity-70 border-slate-100 dark:border-white/5" : "border-slate-200 dark:border-white/10"
            )} onClick={onClick}>
                {isUnread && <div className="absolute left-1.5 top-1/2 -translate-y-1/2 w-1.5 h-1.5 rounded-full bg-primary"></div>}
                <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
                    <span className="material-symbols-outlined text-[26px]">chat</span>
                </div>
                <div className="flex flex-col flex-1 min-w-0">
                    <div className="flex items-center justify-between gap-2">
                        <p className="text-[15px] font-bold dark:text-white truncate">{title}</p>
                        <span className="text-slate-400 dark:text-slate-500 text-[12px] whitespace-nowrap">{time}</span>
                    </div>
                    <p className="text-slate-600 dark:text-slate-400 text-[13px] leading-snug line-clamp-2 break-words" dangerouslySetInnerHTML={{ __html: body }} />
                </div>
            </div>
        );
    }

    // 5. System / Default (Includes 'info')
    return (
        <div className={cn(
            "relative flex items-center gap-4 rounded-xl bg-white dark:bg-ios-card p-4 shadow-sm border transition-transform active:scale-95 overflow-hidden",
            isRead ? "opacity-70 border-slate-100 dark:border-white/5" : "border-slate-200 dark:border-white/10"
        )} onClick={onClick}>
            {isUnread && <div className="absolute left-1.5 top-1/2 -translate-y-1/2 w-1.5 h-1.5 rounded-full bg-slate-400 dark:bg-slate-500"></div>}
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-slate-100 dark:bg-white/5 text-slate-500 dark:text-slate-400">
                <span className="material-symbols-outlined text-[22px]">
                    {type === 'info' ? 'info' : 'settings'}
                </span>
            </div>
            <div className="flex flex-col flex-1 min-w-0">
                <div className="flex items-center justify-between gap-2">
                    <p className="text-[14px] font-semibold dark:text-slate-200 truncate">{title}</p>
                    <span className="text-slate-400 dark:text-slate-500 text-[11px] font-normal whitespace-nowrap">{time}</span>
                </div>
                <p className="text-slate-500 dark:text-slate-400 text-[13px] line-clamp-1 break-words" dangerouslySetInnerHTML={{ __html: body }} />
            </div>
        </div>
    );
};
