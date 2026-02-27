import React from 'react';
import { cn } from '../lib/utils';

interface TabsProps {
    activeTab: string;
    onTabChange: (tab: string) => void;
    tabs: string[];
}

export const Tabs: React.FC<TabsProps> = ({ activeTab, onTabChange, tabs }) => {
    return (
        <div className="flex h-10 w-full items-center justify-center rounded-full bg-slate-200/50 dark:bg-white/10 p-1">
            {tabs.map((tab) => (
                <label
                    key={tab}
                    className={cn(
                        "flex cursor-pointer h-full grow items-center justify-center overflow-hidden rounded-full px-2 text-[13px] font-semibold transition-all",
                        activeTab === tab
                            ? "bg-white dark:bg-[#323234] shadow-sm text-slate-900 dark:text-white"
                            : "text-slate-500 dark:text-[#8e8e93]"
                    )}
                    onClick={() => onTabChange(tab)}
                >
                    <span className="truncate">{tab}</span>
                    <input
                        type="radio"
                        name="filter"
                        value={tab}
                        className="invisible w-0"
                        checked={activeTab === tab}
                        readOnly
                    />
                </label>
            ))}
        </div>
    );
};
