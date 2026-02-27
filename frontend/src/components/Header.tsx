import React from 'react';

interface HeaderProps {
    title: string;
    onBack?: () => void;
    rightAction?: React.ReactNode;
}

export const Header: React.FC<HeaderProps> = ({ title, onBack, rightAction }) => {
    return (
        <header className="sticky top-0 z-40 bg-white/80 dark:bg-background-dark/80 backdrop-blur-xl px-4 pt-4 pb-2">
            <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-1 text-primary cursor-pointer active:opacity-50" onClick={onBack}>
                    <span className="material-symbols-outlined text-[28px]">chevron_left</span>
                    <span className="text-[17px] font-medium">Back</span>
                </div>
                <h1 className="text-[18px] font-bold dark:text-white">{title}</h1>
                <div className="w-12 flex justify-end">
                    {rightAction}
                </div>
            </div>
        </header>
    );
};
