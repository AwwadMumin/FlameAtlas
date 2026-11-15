/** Line icons (24px grid, 1.6 stroke) used by the landing page. */
const base = { width: 30, height: 30, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.6, strokeLinecap: 'round', strokeLinejoin: 'round', 'aria-hidden': true } as const;
export const SearchIcon = () => <svg {...base}><circle cx="10.5" cy="10.5" r="6" /><path d="m15 15 5 5" /><path d="M8 10.5h5M10.5 8v5" opacity=".55" /></svg>;
export const MaterialsIcon = () => <svg {...base}><path d="M12 3 4.5 7.5v9L12 21l7.5-4.5v-9L12 3Z" /><path d="M12 12 4.5 7.5M12 12l7.5-4.5M12 12v9" opacity=".6" /></svg>;
export const CompareIcon = () => <svg {...base}><path d="M5 20V10M12 20V4M19 20v-6" /><path d="M3 20h18" opacity=".6" /></svg>;
export const AskIcon = () => <svg {...base}><path d="M4 5.5A2.5 2.5 0 0 1 6.5 3h11A2.5 2.5 0 0 1 20 5.5v8a2.5 2.5 0 0 1-2.5 2.5H11l-4.5 4v-4H6.5A2.5 2.5 0 0 1 4 13.5v-8Z" /><path d="M9 8.5h6M9 11.5h3.5" opacity=".6" /></svg>;
export const ProblemIcon = () => <svg {...base}><path d="M12 3 2.8 19.5h18.4L12 3Z" /><path d="M12 10v4.5M12 17.2v.1" /></svg>;
export const SolutionIcon = () => <svg {...base}><circle cx="12" cy="12" r="8.5" /><path d="m8 12.3 2.8 2.8L16.3 9.5" /></svg>;
export const SourceIcon = () => <svg {...base}><path d="M14 4h6v6M20 4l-8.5 8.5" /><path d="M18 14v4.5a1.5 1.5 0 0 1-1.5 1.5h-11A1.5 1.5 0 0 1 4 18.5v-11A1.5 1.5 0 0 1 5.5 6H10" /></svg>;
export const AiIcon = () => <svg {...base}><path d="M12 3.5 13.9 9l5.6 1.9-5.6 1.9L12 18.5l-1.9-5.7L4.5 10.9 10.1 9 12 3.5Z" /><path d="M19 3v3M17.5 4.5h3M5 17v3M3.5 18.5h3" opacity=".6" /></svg>;
export const CompareRowsIcon = () => <svg {...base}><path d="M4 7h16M4 12h16M4 17h16" /><path d="M9 4v16M15 4v16" opacity=".5" /></svg>;
