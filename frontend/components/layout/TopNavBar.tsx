"use client";

interface TopNavBarProps {
  userName: string;
  avatarInitials: string;
  onSearch?: (value: string) => void;
  showSearch?: boolean;
}

/** Sticky header, ported from the desktop Stitch exports' TopNavBar-equivalent markup. */
export function TopNavBar({ avatarInitials, onSearch, showSearch = false }: TopNavBarProps) {
  return (
    <header className="flex justify-between items-center w-full px-container-padding h-16 backdrop-blur-md bg-surface/80 border-b border-outline-variant sticky top-0 z-40 shadow-sm md:hidden">
      <h1 className="font-headline-md text-headline-md font-extrabold text-primary">Proxy Busters</h1>
      <div className="flex items-center gap-4">
        {showSearch && (
          <input
            type="text"
            placeholder="Search..."
            onChange={(e) => onSearch?.(e.target.value)}
            className="hidden sm:block pl-4 pr-4 py-2 bg-surface-container border border-outline-variant rounded-full text-body-md font-body-md focus:ring-2 focus:ring-primary/15 focus:border-primary transition-all w-40"
          />
        )}
        <button className="text-on-surface-variant hover:text-primary transition-all">
          <span className="material-symbols-outlined">notifications</span>
        </button>
        <div className="w-8 h-8 rounded-full bg-primary-container text-on-primary-container flex items-center justify-center text-label-md font-label-md border border-outline-variant">
          {avatarInitials}
        </div>
      </div>
    </header>
  );
}

/** Desktop-only header row used inside the main canvas above page content (name/search/bell/avatar). */
export function DesktopTopBar({ userName, avatarInitials, onSearch, showSearch = false }: TopNavBarProps) {
  return (
    <div className="hidden md:flex items-center gap-4 justify-end">
      {showSearch && (
        <div className="relative">
          <span className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-on-surface-variant text-lg">
            search
          </span>
          <input
            type="text"
            placeholder="Search student..."
            onChange={(e) => onSearch?.(e.target.value)}
            className="pl-10 pr-4 py-2 bg-surface-container border border-outline-variant rounded-full text-body-md font-body-md focus:ring-2 focus:ring-primary/15 focus:border-primary transition-all w-64"
          />
        </div>
      )}
      <button className="flex items-center gap-2 p-2 rounded-full text-on-surface-variant hover:bg-surface-container-highest transition-colors">
        <span className="material-symbols-outlined">notifications</span>
      </button>
      <div className="w-10 h-10 rounded-full bg-primary-container text-on-primary-container flex items-center justify-center text-label-md font-label-md border border-outline-variant">
        {avatarInitials}
      </div>
      <span className="font-body-md text-body-md text-on-surface-variant">{userName}</span>
    </div>
  );
}
