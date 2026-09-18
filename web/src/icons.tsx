import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement> & { size?: number };
function Icon({ size = 18, children, ...props }: IconProps) { return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>{children}</svg>; }
export function AlertCircle(props: IconProps) { return <Icon {...props}><circle cx="12" cy="12" r="9" /><line x1="12" y1="8" x2="12" y2="12" /><line x1="12" y1="16" x2="12.01" y2="16" /></Icon>; }
export function Check(props: IconProps) { return <Icon {...props}><polyline points="20 6 9 17 4 12" /></Icon>; }
export function ChevronRight(props: IconProps) { return <Icon {...props}><polyline points="9 18 15 12 9 6" /></Icon>; }
export function FileCode2(props: IconProps) { return <Icon {...props}><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><polyline points="14 2 14 8 20 8" /><polyline points="10 13 8 15 10 17" /><polyline points="14 13 16 15 14 17" /></Icon>; }
export function GitPullRequest(props: IconProps) { return <Icon {...props}><circle cx="18" cy="6" r="3" /><circle cx="6" cy="18" r="3" /><path d="M6 15V6a3 3 0 0 1 3-3h3" /><path d="M18 9v3a3 3 0 0 1-3 3h-3" /></Icon>; }
export function LoaderCircle(props: IconProps) { return <Icon {...props}><path d="M21 12a9 9 0 1 1-6.2-8.56" /></Icon>; }
export function RefreshCw(props: IconProps) { return <Icon {...props}><polyline points="23 4 23 10 17 10" /><polyline points="1 20 1 14 7 14" /><path d="M3.5 9a9 9 0 0 1 14.3-3.4L23 10M1 14l5.2 4.4A9 9 0 0 0 20.5 15" /></Icon>; }
export function RotateCcw(props: IconProps) { return <Icon {...props}><polyline points="1 4 1 10 7 10" /><path d="M3.5 15a9 9 0 1 0 .1-6.5L1 10" /></Icon>; }
export function X(props: IconProps) { return <Icon {...props}><line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" /></Icon>; }
