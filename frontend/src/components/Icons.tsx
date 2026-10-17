import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement>;

function base(props: IconProps) {
  return {
    width: 20,
    height: 20,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.8,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true,
    focusable: false,
    ...props,
  };
}

export const UploadIcon = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="M12 15V4m0 0L7.5 8.5M12 4l4.5 4.5" />
    <path d="M4 15v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3" />
  </svg>
);

export const FileIcon = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" />
    <path d="M14 3v5h5M9 13h6M9 17h4" />
  </svg>
);

export const ShieldIcon = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="M12 3 5 6v5c0 4.5 3 8.3 7 10 4-1.7 7-5.5 7-10V6z" />
    <path d="m9 12 2 2 4-4" />
  </svg>
);

export const CheckIcon = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="m5 12.5 4.5 4.5L19 7.5" />
  </svg>
);

export const AlertIcon = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="M12 4 2.8 19.5h18.4z" />
    <path d="M12 10v4.5M12 17.2v.3" />
  </svg>
);

export const InfoIcon = (p: IconProps) => (
  <svg {...base(p)}>
    <circle cx="12" cy="12" r="9" />
    <path d="M12 11v5M12 7.8v.3" />
  </svg>
);

export const EyeIcon = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z" />
    <circle cx="12" cy="12" r="2.8" />
  </svg>
);

export const EyeOffIcon = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="M4 4l16 16" />
    <path d="M9.9 6A9.8 9.8 0 0 1 12 5.5C18 5.5 21.5 12 21.5 12a17 17 0 0 1-3 3.7M6.3 7.7A16.6 16.6 0 0 0 2.5 12S6 18.5 12 18.5a9 9 0 0 0 4-.9" />
    <path d="M10 10.2a2.8 2.8 0 0 0 3.9 3.9" />
  </svg>
);

export const DownloadIcon = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="M12 4v11m0 0 4.5-4.5M12 15l-4.5-4.5" />
    <path d="M4 17v1a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-1" />
  </svg>
);

export const RestartIcon = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="M4 12a8 8 0 1 0 2.4-5.7L4 8.5" />
    <path d="M4 4v4.5h4.5" />
  </svg>
);

export const ChevronLeftIcon = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="m14.5 6-6 6 6 6" />
  </svg>
);

export const ChevronRightIcon = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="m9.5 6 6 6-6 6" />
  </svg>
);

export const LockIcon = (p: IconProps) => (
  <svg {...base(p)}>
    <rect x="5" y="10.5" width="14" height="10" rx="2" />
    <path d="M8.5 10.5V8a3.5 3.5 0 0 1 7 0v2.5" />
  </svg>
);

export const SparklesIcon = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="M12 3.5 13.6 8a2 2 0 0 0 1.3 1.3l4.6 1.6-4.6 1.6a2 2 0 0 0-1.3 1.3L12 18.5l-1.6-4.6a2 2 0 0 0-1.3-1.3L4.5 11l4.6-1.6A2 2 0 0 0 10.4 8z" />
    <path d="M19 3v3M17.5 4.5h3M5 17.5v3M3.5 19h3" />
  </svg>
);

export const RulesIcon = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="M8 6h12M8 12h12M8 18h12" />
    <path d="m3.5 6 1 1 2-2M3.5 12l1 1 2-2M3.5 18l1 1 2-2" />
  </svg>
);

export const ScanTextIcon = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="M4 8V6a2 2 0 0 1 2-2h2M16 4h2a2 2 0 0 1 2 2v2M20 16v2a2 2 0 0 1-2 2h-2M8 20H6a2 2 0 0 1-2-2v-2" />
    <path d="M8 9.5h8M8 12.5h8M8 15.5h5" />
  </svg>
);

export const ServerIcon = (p: IconProps) => (
  <svg {...base(p)}>
    <rect x="4" y="4" width="16" height="7" rx="1.5" />
    <rect x="4" y="13" width="16" height="7" rx="1.5" />
    <path d="M8 7.5h.01M8 16.5h.01" />
  </svg>
);

export const XIcon = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="M6 6l12 12M18 6 6 18" />
  </svg>
);

export const ArrowRightIcon = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="M5 12h14m0 0-5-5m5 5-5 5" />
  </svg>
);

export const GithubIcon = (p: IconProps) => (
  <svg {...base({ ...p, fill: "currentColor", stroke: "none" })}>
    <path d="M12 2.5a9.5 9.5 0 0 0-3 18.5c.48.09.65-.2.65-.46v-1.6c-2.64.58-3.2-1.27-3.2-1.27-.43-1.1-1.06-1.4-1.06-1.4-.86-.59.07-.58.07-.58.95.07 1.45.98 1.45.98.85 1.45 2.22 1.03 2.76.79.09-.62.33-1.03.6-1.27-2.1-.24-4.32-1.05-4.32-4.68 0-1.03.37-1.88.98-2.54-.1-.24-.42-1.2.09-2.5 0 0 .8-.26 2.6.97a9 9 0 0 1 4.74 0c1.8-1.23 2.6-.97 2.6-.97.51 1.3.19 2.26.09 2.5.61.66.98 1.51.98 2.54 0 3.64-2.22 4.44-4.34 4.67.34.3.64.88.64 1.77v2.63c0 .26.17.56.66.46A9.5 9.5 0 0 0 12 2.5z" />
  </svg>
);

export const ClockIcon = (p: IconProps) => (
  <svg {...base(p)}>
    <circle cx="12" cy="12" r="8.5" />
    <path d="M12 7.5V12l3 2" />
  </svg>
);
