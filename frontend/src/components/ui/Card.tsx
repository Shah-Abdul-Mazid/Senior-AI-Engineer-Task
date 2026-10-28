import React from 'react';
import { clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  glow?: boolean;
}

export const Card: React.FC<CardProps> = ({
  children,
  className,
  glow = false,
  ...props
}) => {
  return (
    <div
      className={twMerge(
        clsx(
          'bg-[#121216] border border-[#272732] rounded-xl p-5 shadow-sm transition-all',
          glow && 'hover:border-indigo-500/40 hover:shadow-indigo-500/10 hover:shadow-lg',
          className
        )
      )}
      {...props}
    >
      {children}
    </div>
  );
};
