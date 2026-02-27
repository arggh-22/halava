import React from 'react';
import { cn } from '../lib/utils';

interface BottomNavProps {
    activeTab: string;
}

export const BottomNav: React.FC<BottomNavProps> = ({ activeTab }) => {
    const navItems = [
        { name: 'Home', icon: 'home' },
        { name: 'Orders', icon: 'assignment' },
        { name: 'Alerts', icon: 'notifications', isAlert: true },
        { name: 'Profile', icon: 'account_circle' },
    ];

    return (
        <div className="fixed bottom-0 left-0 right-0 z-50 glass-nav border-t border-white/5 px-6 pb-8 pt-2">
            <div className="flex items-center justify-between max-w-md mx-auto">
                {navItems.map((item) => (
                    <div
                        key={item.name}
                        className={cn(
                            "flex flex-col items-center gap-1 group cursor-pointer",
                            item.isAlert || item.name === activeTab
                                ? "text-primary"
                                : "text-slate-500 hover:text-primary transition-colors"
                        )}
                    >
                        <span className={cn("material-symbols-outlined", item.isAlert && "fill-1")}>
                            {item.icon}
                        </span>
                        <span className={cn("text-[10px] font-medium", item.isAlert && "font-bold")}>
                            {item.name}
                        </span>
                        {item.isAlert && (
                            <div className="h-1 w-1 bg-primary rounded-full"></div>
                        )}
                    </div>
                ))}
            </div>
        </div>
    );
};
